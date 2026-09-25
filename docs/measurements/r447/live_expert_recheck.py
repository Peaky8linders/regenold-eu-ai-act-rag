"""Live expert-review re-check: the 28 expert-review single-turn questions.

First written for R446 (its script lived in a worktree that was deleted, and
R447 recovered it from the session transcript); committed here so the next
round does not have to. Posts each question as a single user turn to the
DEPLOYED production ask endpoint (sequentially -- the wrapper is a single
shared local process), then judges every criterion with the judge PROMPT and
PARSER the R436 expert-review artifact used (reused verbatim from
``docs/measurements/r409/run_antifragile_frontier_judge.py`` /
``docs/measurements/r411/rejudge_current_answers.py``) over AWS Bedrock
``qwen.qwen3-235b-a22b-2507-v1:0`` -- the R436 judge identity -- with 3
independent repeats and a per-criterion majority vote.

Rows come from ``docs/measurements/r436/expert-review-bedrock-qwen235.json``.
Output: ``docs/measurements/r447/live/expert_live.json`` (+ a progress log).

Usage (from the repo root, with ``.env`` holding the API key and AWS creds):
    .venv/Scripts/python.exe docs/measurements/r447/live_expert_recheck.py [--ids a,b] [--out=path]
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# The Bedrock judge needs .env-derived credentials in os.environ. Importing
# app.config triggers the app's own dotenv load --
# do NOT set REGENOLD_SKIP_DOTENV here.
from dotenv import dotenv_values  # noqa: E402

import app.config  # noqa: E402,F401
from app.data.provision_text import get_provision_text  # noqa: E402
from evals.bench._http_retry import post_json_with_retry  # noqa: E402
from evals.official.rubric import (  # noqa: E402
    normalise_ref,
    ref_head,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)
from evals.regenold.run_official_batch import _provenance  # noqa: E402

SCRATCH_LIVE = REPO / "docs" / "measurements" / "r447" / "live"
SCRATCH_LIVE.mkdir(parents=True, exist_ok=True)
EXPERT_PATH = REPO / "docs" / "measurements" / "r436" / "expert-review-bedrock-qwen235.json"
OUT_PATH = SCRATCH_LIVE / "expert_live.json"
LOG_PATH = SCRATCH_LIVE / "expert_live.log"

ASK_URL = (
    "https://regenold-eu-ai-act-rag-production.up.railway.app"
    "/api/v1/regenold/eu-ai-act/ask"
)
JUDGE_MODEL = "qwen.qwen3-235b-a22b-2507-v1:0"
JUDGE_TEMPERATURE = 0.1
JUDGE_REPEATS = 3
TIMEOUT_S = 180.0

_ENV = dotenv_values(REPO / ".env")


def _api_key() -> str:
    key = os.environ.get("P2P_REGENOLD_API_KEY") or _ENV.get("P2P_REGENOLD_API_KEY") or ""
    if not key:
        raise RuntimeError("P2P_REGENOLD_API_KEY not found in .env")
    return key


def _log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# ── verbatim provision text for the judge prompt (mirrors
#    docs/measurements/r409/run_antifragile_frontier_judge.py) ─────────────

EXTRA_PROVISIONS = {
    "Recital 27": (
        "Recital 27: In order to promote and ensure the development of trustworthy AI, "
        "the Union's approach should be grounded in the ethical principles for trustworthy AI "
        "presented in the High-Level Expert Group's 2019 Ethics guidelines for trustworthy AI. "
        "These non-binding ethical principles include: human agency and oversight; technical "
        "robustness and safety; privacy and data governance; transparency; diversity, "
        "non-discrimination and fairness; societal and environmental well-being; and accountability. "
        "These principles should be translated into concrete requirements for AI systems. "
        "However, this Regulation should apply without prejudice to the legally binding requirements "
        "of Union law."
    ),
    "Regulation (EU) 2017/745 Annex VIII Rule 11": (
        "MDR Annex VIII Rule 11: Software intended to provide information which is used to take "
        "decisions with diagnosis or therapeutic purposes is classified as class IIa, except if such "
        "decisions have an impact that may cause death or an irreversible deterioration of a person's "
        "state of health, in which case it is in class III; or a serious deterioration of a person's "
        "state of health or a surgical intervention, in which case it is classified as class IIb."
    ),
    "Regulation (EU) 2017/745 Article 52": (
        "MDR Article 52: Conformity assessment procedures. Prior to placing a device on the market, "
        "manufacturers shall undertake an assessment of the conformity of that device... For class IIa, "
        "class IIb and class III devices, a notified body shall be involved."
    ),
}


def get_verbatim_provisions(refs: list[str], budget: int = 10000) -> str:
    wanted: list[str] = []
    for r in refs or []:
        n = normalise_ref(r) or r
        if n not in wanted:
            wanted.append(n)
    chunks, used = [], 0
    for w in wanted:
        if w in EXTRA_PROVISIONS:
            t = EXTRA_PROVISIONS[w]
        else:
            t = get_provision_text(w)
            if not t:
                h = ref_head(w)
                if h and h != w:
                    t = get_provision_text(h)
        if not t:
            continue
        room = max(0, budget - used)
        if room < 200:
            break
        body = t if len(t) <= room else t[:room] + " [...]"
        chunks.append(f"--- {w} ---\n{body}")
        used += len(body)
    return "\n\n".join(chunks) if chunks else "(no verbatim text supplied)"


# Verbatim from docs/measurements/r409/run_antifragile_frontier_judge.py
JUDGE_PROMPT_TEMPLATE = """You are the LLM-as-a-judge for an EU AI Act question-answering benchmark (Regulation (EU) 2024/1689).

You are given a QUESTION, a set of CORRECTNESS CRITERIA, and a CANDIDATE ANSWER. Make TWO INDEPENDENT judgements of that one answer and return both in a single JSON object.

JUDGEMENT 1 - ANSWER CORRECTNESS. For EACH criterion, decide whether the candidate answer satisfies it.

HOW TO JUDGE:
- A criterion is satisfied only when the candidate answer STATES THE SUBSTANCE of it. Naming or citing the provision that contains the fact is NOT enough.
- The answer may use different words. Judge meaning, not phrasing.
- A criterion that is a bare verdict ("Yes" / "No") is satisfied only when the answer's actual position matches it. An answer that leads with the opposite verdict and later concedes the point does NOT satisfy it - the verdict must be the answer's unambiguous position.
- Extra correct material in the answer neither satisfies nor breaks a criterion. Judge each criterion on its own.
- An answer that declines to answer, or says the material available does not permit an answer, satisfies NOTHING.
- Do not reward an answer for being long. Do not punish it for being short.

JUDGEMENT 2 - REGULATORY TONE. Judge whether the response is BOTH appropriate AND clear for a professional regulatory-advice setting.
APPROPRIATE means: professional and measured; does not lecture, moralise, or editorialise; does not address the reader informally; does not talk about itself, its retrieval, its knowledge base, its "supplied materials", or its own limitations; does not hedge into uselessness.
CLEAR means: readable, well-ordered prose that a compliance professional could act on; not a wall of fragments; not internally contradictory.
Correctness is NOT a tone concern. A wrong answer in impeccable regulatory prose passes judgement 2.

VERBATIM STATUTORY TEXT:
{provisions}

QUESTION:
{question}

CRITERIA:
{criteria}

CANDIDATE ANSWER:
{answer}

Return ONLY this JSON object, no markdown fence, no prose. "verdicts" has one entry per criterion, in order:
{{"verdicts": [{{"n": 1, "satisfied": true, "why": "one short sentence"}}], "tone": {{"appropriate": true, "clear": true, "why": "one short sentence"}}}}"""


def _build_prompt(question: str, criteria: list[str], answer: str, expected_refs: list[str]) -> str:
    provisions = get_verbatim_provisions(expected_refs)
    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(criteria, 1))
    ans = (answer or "").strip() or "(the system returned no answer)"
    return (
        JUDGE_PROMPT_TEMPLATE.replace("{provisions}", provisions)
        .replace("{question}", question)
        .replace("{criteria}", numbered)
        .replace("{answer}", f"<candidate_answer>\n{ans}\n</candidate_answer>")
    )


def _parse_verdict(raw_text: str) -> dict:
    """Verbatim parser from docs/measurements/r411/rejudge_current_answers.py."""
    clean = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    values: list[object] = []
    decoder = json.JSONDecoder()
    try:
        parsed = json.loads(clean)
        values.append(parsed)
    except json.JSONDecodeError:
        for i, char in enumerate(clean):
            if char not in "{[":
                continue
            try:
                value, _end = decoder.raw_decode(clean[i:])
            except json.JSONDecodeError:
                continue
            values.append(value)
    objects = [value for value in values if isinstance(value, dict)]
    parsed = {}
    for value in objects:
        parsed.update(value)
    verdicts = parsed.get("verdicts", [])
    tone = parsed.get("tone", {}) or {}
    return {
        "criteria_results": [bool(v.get("satisfied")) for v in verdicts],
        "criteria_why": [v.get("why", "") for v in verdicts],
        "tone_pass": bool(tone.get("appropriate")) and bool(tone.get("clear")),
        "tone_why": tone.get("why", ""),
        "raw_response": raw_text,
    }


_BEDROCK_PROVIDER = None


def _judge_bedrock_once(prompt: str, retries: int = 3) -> dict:
    global _BEDROCK_PROVIDER
    for k in ("AWS_BEARER_TOKEN_BEDROCK", "BEDROCK_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        v = _ENV.get(k)
        if v:
            os.environ.setdefault(k, v)

    from app.llm.bedrock_client import BedrockProvider, BedrockRequest, resolve_bedrock_model

    if _BEDROCK_PROVIDER is None:
        _BEDROCK_PROVIDER = BedrockProvider()

    resolved = resolve_bedrock_model(JUDGE_MODEL) or JUDGE_MODEL
    last = None
    for attempt in range(retries):
        resp = _BEDROCK_PROVIDER.complete(
            BedrockRequest(
                user=prompt,
                model=resolved,
                max_tokens=2000,
                temperature=JUDGE_TEMPERATURE,
                timeout_seconds=180.0,
            )
        )
        if resp.error:
            last = resp.error
            time.sleep(1.5 * (attempt + 1))
            continue
        try:
            out = _parse_verdict(resp.text or "")
            out["resolved_model"] = resolved
            return out
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"bedrock judge failed ({resolved}): {last}")


def _majority_judge(question: str, criteria: list[str], answer: str, expected_refs: list[str]) -> dict:
    prompt = _build_prompt(question, criteria, answer, expected_refs)
    draws = []
    with ThreadPoolExecutor(max_workers=JUDGE_REPEATS) as pool:
        futures = [pool.submit(_judge_bedrock_once, prompt) for _ in range(JUDGE_REPEATS)]
        for f in futures:
            try:
                draws.append(f.result())
            except Exception as exc:  # noqa: BLE001
                draws.append({"error": str(exc)})
    ok_draws = [d for d in draws if "error" not in d]
    n = len(criteria)
    majority_results: list[bool] = []
    majority_why: list[str] = []
    for i in range(n):
        votes = [d["criteria_results"][i] for d in ok_draws if i < len(d.get("criteria_results", []))]
        true_n = sum(1 for v in votes if v)
        decided = true_n * 2 > len(votes) if votes else False
        majority_results.append(decided)
        whys = [
            d["criteria_why"][i]
            for d in ok_draws
            if i < len(d.get("criteria_results", [])) and i < len(d.get("criteria_why", []))
            and d["criteria_results"][i] == decided
        ]
        majority_why.append(whys[0] if whys else "")
    tone_votes = [d["tone_pass"] for d in ok_draws]
    tone_pass = (sum(1 for v in tone_votes if v) * 2 > len(tone_votes)) if tone_votes else False
    tone_whys = [d.get("tone_why", "") for d in ok_draws if d.get("tone_pass") == tone_pass]
    return {
        "criteria_results": majority_results,
        "criteria_why": majority_why,
        "tone_pass": tone_pass,
        "tone_why": tone_whys[0] if tone_whys else "",
        "n_draws_ok": len(ok_draws),
        "n_draws_total": len(draws),
        "vote_detail": [d.get("criteria_results") for d in ok_draws],
        "draw_errors": [d["error"] for d in draws if "error" in d],
    }


DEGRADED_LEGS = {"fallback", "deterministic"}

HEALTHZ_URL = "https://regenold-eu-ai-act-rag-production.up.railway.app/healthz"

#: R446 coordinator hotfix note (mid-task): a redeploy is pending that turns
#: off an Annex I citation pass which can emit a wrong Annex I point. Every
#: row therefore records the `/healthz` commit in effect immediately before
#: its request (`build`), plus whether its live refs/answer name an Annex I
#: sub-point, so a row served by the pre-hotfix build with Annex-I exposure
#: can be identified for a targeted re-run once the new SHA is known.
_ANNEX_I_LEAF_RE = re.compile(r"^Annex I\.\d")
_ANNEX_I_POINT_IN_TEXT_RE = re.compile(r"\bAnnex I\b\s*(?:point\s*)?[\(.]?\s*\d", re.IGNORECASE)


def _current_build() -> str:
    try:
        with urllib.request.urlopen(HEALTHZ_URL, timeout=15.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return str(data.get("commit") or "?")
    except Exception as exc:  # noqa: BLE001 — a healthz blip must not kill the row
        return f"?(error:{exc})"


def _annex_i_exposure(answer: str, refs: list[str]) -> dict[str, Any]:
    ref_leaf = [r for r in refs if isinstance(r, str) and _ANNEX_I_LEAF_RE.match(r.strip())]
    ref_head_bare = [r for r in refs if isinstance(r, str) and r.strip() == "Annex I"]
    answer_point = bool(_ANNEX_I_POINT_IN_TEXT_RE.search(answer or ""))
    return {
        "ref_annex_i_leaf": ref_leaf,
        "ref_annex_i_bare_head": ref_head_bare,
        "answer_names_annex_i_point": answer_point,
        "flag_for_rerun": bool(ref_leaf) or answer_point,
    }


def _post_question(question: str) -> dict[str, Any]:
    url = ASK_URL
    url = f"{url}{'&' if '?' in url else '?'}include_reasoning=true"
    messages = [{"role": "user", "content": question}]
    build = _current_build()
    t0 = time.time()
    body, latency_ms, status, err, attempts, retried_errors = post_json_with_retry(
        url, messages, _api_key(), TIMEOUT_S
    )
    wall_s = time.time() - t0
    answer = str((body or {}).get("answer") or "")
    refs = list((body or {}).get("references") or [])
    prov = _provenance(body)
    return {
        "answer": answer,
        "references": refs,
        "latency_ms": latency_ms,
        "wall_s": round(wall_s, 3),
        "http_status": status,
        "error": err,
        "attempts": attempts,
        "provenance": prov,
        "build": build,
        "annex_i_exposure": _annex_i_exposure(answer, refs),
    }


def main() -> int:
    global OUT_PATH
    only_ids: set[str] | None = None
    args = sys.argv[1:]
    i_arg = 0
    while i_arg < len(args):
        a = args[i_arg]
        if a == "--ids" and i_arg + 1 < len(args):
            only_ids = {x.strip() for x in args[i_arg + 1].split(",") if x.strip()}
            i_arg += 2
        elif a.startswith("--out="):
            OUT_PATH = Path(a.split("=", 1)[1])
            i_arg += 1
        else:
            i_arg += 1

    rows = [
        {"id": r["id"], "question": r["question"], "criteria": r["criteria"],
         "expected_refs": r.get("expected_refs") or []}
        for r in json.loads(EXPERT_PATH.read_text(encoding="utf-8"))["rows"]
    ]
    if only_ids:
        all_ids = {r["id"] for r in rows}
        missing = only_ids - all_ids
        if missing:
            raise SystemExit(f"unknown ids: {sorted(missing)}")
        rows = [r for r in rows if r["id"] in only_ids]
    _log(f"loaded {len(rows)} expert-review rows" + (f" (filtered to {sorted(only_ids)})" if only_ids else ""))

    results: list[dict[str, Any]] = []
    for i, row in enumerate(rows, 1):
        rid = row["id"]
        _log(f"[{i:2d}/{len(rows)}] POST {rid} ...")
        live = _post_question(row["question"])
        served_by = (live["provenance"] or {}).get("stage2_served_by", "")
        retried = False
        if served_by in DEGRADED_LEGS or live["error"]:
            _log(
                f"  {rid}: served_by={served_by!r} error={live['error']!r} -> retrying once"
            )
            time.sleep(2.0)
            live2 = _post_question(row["question"])
            retried = True
            served_by2 = (live2["provenance"] or {}).get("stage2_served_by", "")
            still_degraded = served_by2 in DEGRADED_LEGS or bool(live2["error"])
            live = {**live2, "first_attempt": live, "still_degraded_after_retry": still_degraded}
        else:
            live["still_degraded_after_retry"] = False
        served_by_final = (live.get("provenance") or {}).get("stage2_served_by", "")
        model_final = (live.get("provenance") or {}).get("stage2_model", "")
        annex_flag = (live.get("annex_i_exposure") or {}).get("flag_for_rerun")
        _log(
            f"  {rid}: {live['wall_s']:.1f}s refs={len(live['references'])} "
            f"chars={len(live['answer'])} served_by={served_by_final!r} model={model_final!r} "
            f"retried={retried} build={live.get('build')!r} annex_i_flag={annex_flag}"
        )
        results.append({"id": rid, "row": row, "live": live, "retried": retried})
        # checkpoint after every row
        OUT_PATH.write_text(
            json.dumps({"generation": results}, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    _log("generation complete; starting Bedrock judging (3 repeats/row, majority vote)")

    for i, item in enumerate(results, 1):
        row = item["row"]
        live = item["live"]
        rid = row["id"]
        _log(f"[{i:2d}/{len(results)}] JUDGE {rid} ...")
        try:
            judged = _majority_judge(row["question"], row["criteria"], live["answer"], row["expected_refs"])
        except Exception as exc:  # noqa: BLE001
            judged = {"error": str(exc)}
        item["judge"] = judged
        pred_refs = live["references"]
        exp = row["expected_refs"]
        item["ref_metrics"] = {
            "ref_loose": reference_correctness_loose(pred_refs, exp),
            "ref_strict": reference_correctness_strict(pred_refs, exp),
            "ref_conc": reference_conciseness(pred_refs, exp),
        }
        crit = judged.get("criteria_results") or []
        item["loose"] = (sum(1 for c in crit if c) / len(crit)) if crit else None
        item["strict"] = bool(crit) and all(crit)
        item["pass_count"] = sum(1 for c in crit if c)
        item["n_criteria"] = len(crit)
        _log(
            f"  {rid}: {item['pass_count']}/{item['n_criteria']} criteria  "
            f"tone={judged.get('tone_pass')}  draws_ok={judged.get('n_draws_ok')}/{judged.get('n_draws_total')}"
        )
        OUT_PATH.write_text(
            json.dumps({"generation": results}, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    n = len(results)
    strict_n = sum(1 for r in results if r.get("strict"))
    loose_vals = [r["loose"] for r in results if r.get("loose") is not None]
    tone_n = sum(1 for r in results if (r.get("judge") or {}).get("tone_pass"))
    _log("=" * 80)
    _log(f"DONE  rows={n}  strict={strict_n}/{n}  loose_mean={sum(loose_vals)/len(loose_vals):.4f}  tone={tone_n}/{n}")

    # R446 coordinator hotfix note — surface every row that was served by the
    # pre-hotfix build AND shows Annex I sub-point exposure, so it can be
    # targeted for a re-run once the new SHA is announced.
    flagged = [
        r["id"] for r in results
        if (r["live"].get("annex_i_exposure") or {}).get("flag_for_rerun")
    ]
    if flagged:
        _log(f"ANNEX I RE-RUN CANDIDATES ({len(flagged)}): {', '.join(flagged)}")
    else:
        _log("ANNEX I RE-RUN CANDIDATES: none")

    _log(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
