"""Offline A/B of the NLI citation verifier over RECORDED live answers.

WHY THIS EXISTS
---------------
The question is: *is a neural NLI citation verifier worth a torch dependency on
Railway, for reference precision?*

Deploying torch to answer that would be backwards. Every input the verifier
needs is already recorded: ``evals/bench/results/easyhard-r282-fullprod-clean.json``
holds 132 rows of live production output with ``pred_answer`` + ``pred_refs`` +
``gold_refs``. The verifier is a pure post-processing filter over exactly those
three fields, so it can be replayed OFFLINE and re-scored against gold —
deterministically, at n=132, with no deploy and no live wrapper calls.

This mirrors the established pattern: R281's ``adaptive_ref_clamp`` sim and
R282's over-cite positional-clamp sim (which is how we learned that clamp drops
gold Article 43 before shipping it).

RELATIONSHIP TO ``evals/bench/ref_precision_sim.py``
---------------------------------------------------
That module is the R281 simulator for a PURE transform (a clamp: refs in, refs
out, no model). This one is its sibling for a SCORER-driven transform, and adds
the three things a scorer needs: a persistent (claim, premise) score cache so
threshold sweeps are free, premise chunking for the cross-encoder window, and
claim-formulation variants. Both score through ``evals.bench.metrics`` and both
treat ``ref_loose`` (recall) as the R142.1 guard. Use that one for clamps, this
one for anything with a model in the loop.

WHAT IT MEASURES
----------------
The three gold-scored reference axes, via the SAME ``evals.bench.metrics``
functions the real gate uses, so numbers are directly comparable to
``easyhard_ab`` output:

  * ``ref_loose``  = recall of gold heads          <- THE GUARD RAIL
  * ``ref_strict`` = F1 of pred vs gold head set   <- the thing we want to lift
  * ``ref_conc``   = count-ratio vs gold cardinality

Plus ``gold_drops``: the number of rows where the filter removed the LAST
reference covering a gold head. Per project doctrine (R142.1) that is the
catastrophic failure mode — a positional clamp that did it lost a live pairwise
judge 11-0 (p=0.001). Any arm with material gold_drops is rejected on the spot
regardless of its F1 gain.

HONESTY / SCOPE
---------------
* The metrics HEAD-COLLAPSE sub-points (``evals.bench.metrics.article_heads``:
  "Article 5.1" -> "Article 5"). So dropping a sub-point whose head survives is
  score-neutral, and only dropping the last ref for a head can cost recall. The
  sim measures gold_drops at head level for that reason.
* This replays a filter over FIXED answers. It cannot capture second-order
  effects (a deployed filter does not change the answer prose). That is
  correct here: the verifier runs after the answer is final.
* ``LexicalEntailmentScorer`` is included as a ZERO-LATENCY CONTROL ARM. If it
  matches neural NLI, the honest answer to "is torch worth it" is *no*.

USAGE
-----
    # score once into the cache (slow), then sweep thresholds for free
    .venv/Scripts/python.exe -m evals.harness.nli_refprecision_sim \\
        --scorer nli --model cross-encoder/nli-deberta-v3-base \\
        --formulation mentions --label r288-nli-base

    # zero-cost control arm
    .venv/Scripts/python.exe -m evals.harness.nli_refprecision_sim \\
        --scorer lexical --formulation mentions --label r288-lexical
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics as st
import time
from pathlib import Path
from typing import Any, Callable

from evals.bench import metrics as bench_metrics

_HERE = Path(__file__).resolve()
_RESULTS = _HERE.parents[1] / "bench" / "results"
_CACHE_DIR = _RESULTS / "_nli_score_cache"

DEFAULT_SIDECAR = _RESULTS / "easyhard-r282-fullprod-clean.json"

# A cross-encoder truncates at 512 tokens. Article 5 is 11,080 chars (~2,800
# tokens), so feeding a whole provision as the premise silently discards ~75%
# of it. Chunk to ~1,200 chars (~300 tokens) so the claim still fits alongside,
# and take the MAX over chunks: "is this citation supported ANYWHERE in the
# provision" is the question, not "does the provision's first paragraph
# support it".
PREMISE_CHUNK_CHARS = 1200
MAX_PREMISE_CHUNKS = 8


# ── inputs ───────────────────────────────────────────────────────────────


def load_rows(sidecar: Path) -> list[dict[str, Any]]:
    """Recorded live rows: id/pred_answer/pred_refs/gold_refs/is_multiturn."""
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    rows = data.get("baseline_rows") or data.get("rows") or []
    out = []
    for r in rows:
        if r.get("http_status") not in (200, None):
            continue
        if not r.get("pred_answer") or not r.get("pred_refs"):
            continue
        out.append(r)
    return out


def load_questions() -> dict[str, str]:
    """id -> live question text, for the question-named gold protection."""
    try:
        from evals.harness.probe_set import load_probe_set

        return {p.id: p.live_question for p in load_probe_set()}
    except Exception:  # noqa: BLE001 — sim still works without named-protection
        return {}


def _split_sentences(text: str) -> list[str]:
    try:
        from app.engines.sentence_index import split_legal_sentences

        parts = [s.strip() for s in split_legal_sentences(text) if s and s.strip()]
        if parts:
            return parts
    except Exception:  # noqa: BLE001
        pass
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def _chunk_premise(text: str) -> list[str]:
    """Sentence-aligned chunks that fit a cross-encoder window."""
    if not text:
        return []
    sents = _split_sentences(text) or [text]
    chunks: list[str] = []
    cur = ""
    for s in sents:
        if len(cur) + len(s) + 1 <= PREMISE_CHUNK_CHARS:
            cur = f"{cur} {s}".strip()
        else:
            if cur:
                chunks.append(cur)
            cur = s[:PREMISE_CHUNK_CHARS] if len(s) > PREMISE_CHUNK_CHARS else s
    if cur:
        chunks.append(cur)
    return chunks[:MAX_PREMISE_CHUNKS]


_REF_NUM_RE = re.compile(r"(?:Article|Annex)\s+([0-9]+|[IVXLC]+)", re.IGNORECASE)


def _ref_mentioned_in(sentence: str, ref: str) -> bool:
    """Does this sentence textually cite this reference's head?"""
    m = _REF_NUM_RE.search(ref)
    if not m:
        return False
    num = m.group(1)
    kind = "Annex" if ref.strip().lower().startswith("annex") else "Article"
    pat = re.compile(
        rf"\b(?:{kind}|{'Annexes' if kind == 'Annex' else 'Articles|Art\\.?'})\s*"
        rf"[^.;:]{{0,40}}?\b{re.escape(num)}\b",
        re.IGNORECASE,
    )
    return bool(pat.search(sentence))


def build_claims(answer: str, ref: str, formulation: str) -> list[str]:
    """The claim(s) whose support by ``ref`` we are testing.

    * ``answer``    - the whole answer (what the shipped code does).
    * ``sentences`` - every answer sentence, max over them (ALCE-style: is ANY
                      claim in the answer supported by this provision?).
    * ``mentions``  - only the sentences that actually cite this ref, falling
                      back to all sentences when the prose names none. This is
                      the standard citation-attribution unit: a citation is
                      warranted iff the text it is attached to is supported.
    """
    if formulation == "answer":
        return [answer]
    sents = _split_sentences(answer)
    if not sents:
        return [answer]
    if formulation == "sentences":
        return sents
    if formulation == "mentions":
        hit = [s for s in sents if _ref_mentioned_in(s, ref)]
        return hit or sents
    raise ValueError(f"unknown formulation: {formulation}")


# ── scorers ──────────────────────────────────────────────────────────────


def _cache_path(model_tag: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", model_tag)
    return _CACHE_DIR / f"{safe}.json"


class CachedScorer:
    """Wraps a pair-scorer with a persistent (claim, premise) -> score cache.

    Scoring is the only expensive part; caching it makes every downstream
    threshold / policy sweep free, so the experiment is a sweep rather than a
    single guess.
    """

    def __init__(self, model_tag: str, score_pairs: Callable[[list[tuple[str, str]]], list[float]]):
        self.model_tag = model_tag
        self._score_pairs = score_pairs
        self._path = _cache_path(model_tag)
        self._cache: dict[str, float] = {}
        if self._path.exists():
            try:
                self._cache = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                self._cache = {}
        self.calls = 0

    @staticmethod
    def _key(claim: str, premise: str) -> str:
        h = hashlib.sha256()
        h.update(claim.encode("utf-8"))
        h.update(b"\x00")
        h.update(premise.encode("utf-8"))
        return h.hexdigest()[:32]

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        keys = [self._key(c, p) for c, p in pairs]
        todo = [(i, pairs[i]) for i, k in enumerate(keys) if k not in self._cache]
        if todo:
            fresh = self._score_pairs([p for _, p in todo])
            self.calls += len(todo)
            for (i, _), s in zip(todo, fresh):
                self._cache[keys[i]] = float(s)
        return [self._cache[k] for k in keys]

    def flush(self) -> None:
        try:
            self._path.write_text(json.dumps(self._cache), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass


def make_lexical_scorer() -> CachedScorer:
    """Zero-latency IDF-coverage control arm (already shipped in the repo)."""
    from app.data.eu_ai_act_corpus import ARTICLE_FULL_TEXT
    from app.engines.crag_nli_verifier import LexicalEntailmentScorer

    provisions = [{"text": t} for t in ARTICLE_FULL_TEXT.values()]
    scorer = LexicalEntailmentScorer(provisions)

    def _run(pairs: list[tuple[str, str]]) -> list[float]:
        return [scorer.score(c, p) for c, p in pairs]

    return CachedScorer("lexical-coverage", _run)


def make_nli_scorer(model_name: str, batch_size: int = 32) -> CachedScorer:
    """Neural NLI cross-encoder, entailment probability, in-process."""
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(model_name)
    entail_idx = _entail_index(model)
    print(f"  [nli] {model_name} entail_index={entail_idx} "
          f"labels={getattr(getattr(model, 'config', None), 'id2label', None)}")

    def _run(pairs: list[tuple[str, str]]) -> list[float]:
        import numpy as np

        # CrossEncoder pair order is (premise, hypothesis) for NLI models.
        enc = [[p, c] for c, p in pairs]
        raw = model.predict(enc, batch_size=batch_size, show_progress_bar=False)
        arr = np.asarray(raw, dtype="float64")
        if arr.ndim == 1:
            return [float(x) for x in arr]
        e = np.exp(arr - arr.max(axis=1, keepdims=True))
        probs = e / e.sum(axis=1, keepdims=True)
        return [float(x) for x in probs[:, entail_idx]]

    return CachedScorer(model_name, _run)


def _entail_index(model) -> int:
    cfg = getattr(model, "config", None)
    id2label = getattr(cfg, "id2label", None) if cfg is not None else None
    if isinstance(id2label, dict):
        for idx, label in id2label.items():
            if str(label).strip().lower() in {"entailment", "entails", "label_1"}:
                if str(label).strip().lower() != "label_1":
                    return int(idx)
    if isinstance(id2label, dict):
        for idx, label in id2label.items():
            if "entail" in str(label).lower():
                return int(idx)
    return 1


# ── the experiment ───────────────────────────────────────────────────────


def score_row(
    scorer: CachedScorer,
    answer: str,
    refs: list[str],
    formulation: str,
    provision_text: Callable[[str], str],
) -> dict[str, float]:
    """ref -> support score = max over (claims x premise chunks)."""
    pairs: list[tuple[str, str]] = []
    spans: list[tuple[str, int, int]] = []
    for ref in refs:
        text = provision_text(ref) or ""
        chunks = _chunk_premise(text)
        claims = build_claims(answer, ref, formulation)
        start = len(pairs)
        for c in claims:
            for ch in chunks:
                pairs.append((c, ch))
        spans.append((ref, start, len(pairs)))
    if not pairs:
        return {r: 1.0 for r in refs}
    scores = scorer.score(pairs)
    out: dict[str, float] = {}
    for ref, a, b in spans:
        out[ref] = max(scores[a:b]) if b > a else 1.0  # unresolvable text -> keep
    return out


def apply_policy(
    refs: list[str],
    scores: dict[str, float],
    *,
    mode: str,
    threshold: float,
    floor: int,
    protect: set[str],
) -> list[str]:
    """Turn support scores into a kept-reference list.

    ``mode='abs'`` keeps score >= threshold. ``mode='rel'`` keeps
    score >= threshold * max(score) — scale-free, so it survives the fact that
    a rerank relevance score and an NLI probability are different quantities.

    ``floor`` always keeps the top-N by score, and ``protect`` never drops a
    reference whose head the question explicitly named. Both are the R142.1
    gold-protection lessons carried over from ``adaptive_ref_clamp``.
    """
    if not refs:
        return refs
    if mode == "rel":
        top = max(scores.get(r, 0.0) for r in refs) or 0.0
        cut = threshold * top
    else:
        cut = threshold
    ranked = sorted(refs, key=lambda r: scores.get(r, 0.0), reverse=True)
    keep_floor = set(ranked[: max(0, floor)])
    kept = [
        r
        for r in refs
        if scores.get(r, 0.0) >= cut
        or r in keep_floor
        or (bench_metrics.article_head(r) or r) in protect
    ]
    return kept or refs


def _heads(refs: list[str]) -> set[str]:
    return bench_metrics.article_heads(refs)


_Q_ARTICLE_RE = re.compile(r"\bArticles?\s+(\d{1,3})", re.IGNORECASE)
_Q_ANNEX_RE = re.compile(r"\bAnnex(?:es)?\s+([IVXLC]+)\b", re.IGNORECASE)


def _question_named_heads(question: str) -> set[str]:
    """Heads the question itself named — never droppable (R281 protection)."""
    if not question:
        return set()
    refs = [f"Article {n}" for n in _Q_ARTICLE_RE.findall(question)]
    refs += [f"Annex {n.upper()}" for n in _Q_ANNEX_RE.findall(question)]
    return _heads(refs)


def evaluate(rows: list[dict[str, Any]], get_refs: Callable[[dict], list[str]]) -> dict[str, Any]:
    """Reproduce the easyhard_ab arm summary exactly, per split."""
    out: dict[str, Any] = {}
    for split, is_hard in (("easy", False), ("hard", True)):
        sub = [r for r in rows if bool(r.get("is_multiturn")) == is_hard]
        if not sub:
            continue
        loose, strict, conc, ratios = [], [], [], []
        for r in sub:
            pred = get_refs(r)
            gold = r.get("gold_refs") or []
            loose.append(bench_metrics.reference_correctness_loose(pred, gold))
            strict.append(bench_metrics.reference_correctness_strict(pred, gold))
            conc.append(bench_metrics.reference_conciseness(pred, gold))
            g = len(_heads(gold))
            if g:
                ratios.append(len(_heads(pred)) / g)
        out[split] = {
            "n": len(sub),
            "ref_loose": st.fmean(loose),
            "ref_strict": st.fmean(strict),
            "ref_conc": st.fmean(conc),
            "pred_gold_ratio": st.fmean(ratios) if ratios else 0.0,
        }
    return out


def gold_damage(rows: list[dict[str, Any]], get_refs: Callable[[dict], list[str]]) -> dict[str, Any]:
    """Rows where filtering removed the LAST reference covering a gold head."""
    hits = []
    for r in rows:
        gold = _heads(r.get("gold_refs") or [])
        if not gold:
            continue
        before = _heads(r.get("pred_refs") or []) & gold
        after = _heads(get_refs(r)) & gold
        lost = before - after
        if lost:
            hits.append({
                "id": r.get("id"),
                "split": "hard" if r.get("is_multiturn") else "easy",
                "lost": sorted(lost),
                "gold": sorted(gold),
                "pred_before": r.get("pred_refs"),
                "pred_after": get_refs(r),
            })
    return {"rows_damaged": len(hits), "detail": hits[:25]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sidecar", default=str(DEFAULT_SIDECAR))
    ap.add_argument("--scorer", choices=["nli", "lexical"], default="lexical")
    ap.add_argument("--model", default="cross-encoder/nli-deberta-v3-base")
    ap.add_argument("--formulation", choices=["answer", "sentences", "mentions"], default="mentions")
    ap.add_argument("--label", default="nli-sim")
    ap.add_argument("--modes", default="abs,rel")
    ap.add_argument("--thresholds", default="")
    ap.add_argument("--floors", default="1,2")
    ap.add_argument("--no-protect", action="store_true",
                    help="disable question-named gold protection (ablation)")
    args = ap.parse_args()

    os.environ.setdefault("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
    os.environ.setdefault("P2P_GRAPH_RAG_PROVIDER", "cli")

    from app.data.provision_text import get_provision_text

    rows = load_rows(Path(args.sidecar))
    questions = load_questions()
    print(f"rows: {len(rows)}  (easy={sum(1 for r in rows if not r['is_multiturn'])}, "
          f"hard={sum(1 for r in rows if r['is_multiturn'])})")

    baseline = evaluate(rows, lambda r: r["pred_refs"])
    print("\nBASELINE (recorded live prod)")
    for s, m in baseline.items():
        print(f"  {s:5s} n={m['n']:3d}  loose={m['ref_loose']:.4f}  strict={m['ref_strict']:.4f}  "
              f"conc={m['ref_conc']:.4f}  pred:gold={m['pred_gold_ratio']:.2f}")

    if args.scorer == "nli":
        scorer = make_nli_scorer(args.model)
        tag = args.model
    else:
        scorer = make_lexical_scorer()
        tag = "lexical-coverage"

    t0 = time.time()
    per_row: dict[str, dict[str, float]] = {}
    for i, r in enumerate(rows, 1):
        per_row[r["id"]] = score_row(
            scorer, r["pred_answer"], list(r["pred_refs"]), args.formulation, get_provision_text
        )
        if i % 20 == 0:
            scorer.flush()
            print(f"  scored {i}/{len(rows)} rows ({time.time() - t0:.0f}s, "
                  f"{scorer.calls} fresh pairs)")
    scorer.flush()
    elapsed = time.time() - t0
    # ms/pair is only meaningful for pairs actually computed this run; a fully
    # cached re-run would otherwise report a nonsense figure.
    ms_per_pair = (elapsed / scorer.calls * 1000) if scorer.calls else None
    print(f"\nscored {len(rows)} rows in {elapsed:.1f}s ({scorer.calls} fresh pairs, "
          + (f"{ms_per_pair:.1f} ms/pair)" if ms_per_pair is not None else "all cached)"))

    allv = [v for d in per_row.values() for v in d.values()]
    if allv:
        qs = [0.05, 0.25, 0.5, 0.75, 0.95]
        print("score distribution: " + "  ".join(
            f"p{int(q * 100)}={st.quantiles(allv, n=100)[int(q * 100) - 1]:.4f}"
            for q in qs if len(allv) > 2))

    if args.thresholds:
        thresholds = [float(x) for x in args.thresholds.split(",")]
    else:
        thresholds = [0.02, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70]

    protect_map: dict[str, set[str]] = {}
    if not args.no_protect:
        for r in rows:
            protect_map[r["id"]] = _question_named_heads(questions.get(r["id"], ""))

    results = []
    print(f"\nSWEEP  scorer={tag}  formulation={args.formulation}  "
          f"protect={'off' if args.no_protect else 'question-named'}")
    header = (f"{'mode':>4} {'thr':>5} {'flr':>3} | {'easy L':>7} {'easy F1':>7} {'easy C':>7} | "
              f"{'hard L':>7} {'hard F1':>7} {'hard C':>7} | {'goldrm':>6}")
    print(header)
    print("-" * len(header))
    for mode in [m.strip() for m in args.modes.split(",") if m.strip()]:
        for floor in [int(x) for x in args.floors.split(",")]:
            for thr in thresholds:
                def gr(r, _m=mode, _t=thr, _f=floor):
                    return apply_policy(
                        list(r["pred_refs"]), per_row[r["id"]],
                        mode=_m, threshold=_t, floor=_f,
                        protect=protect_map.get(r["id"], set()),
                    )
                ev = evaluate(rows, gr)
                dmg = gold_damage(rows, gr)
                e, h = ev.get("easy", {}), ev.get("hard", {})
                results.append({"mode": mode, "threshold": thr, "floor": floor,
                                "eval": ev, "gold_damage": dmg})
                print(f"{mode:>4} {thr:>5.2f} {floor:>3} | "
                      f"{e.get('ref_loose', 0):>7.4f} {e.get('ref_strict', 0):>7.4f} "
                      f"{e.get('ref_conc', 0):>7.4f} | "
                      f"{h.get('ref_loose', 0):>7.4f} {h.get('ref_strict', 0):>7.4f} "
                      f"{h.get('ref_conc', 0):>7.4f} | {dmg['rows_damaged']:>6d}")

    out_path = _RESULTS / f"nli-sim-{args.label}.json"
    out_path.write_text(json.dumps({
        "label": args.label, "scorer": tag, "formulation": args.formulation,
        "sidecar": str(args.sidecar), "n_rows": len(rows),
        "protect": not args.no_protect,
        "ms_per_pair": ms_per_pair,
        "fresh_pairs": scorer.calls,
        "baseline": baseline, "sweep": results,
        "per_row_scores": per_row,
    }, indent=1), encoding="utf-8")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
