"""R388 - the LLM-as-a-judge half of the official-rubric reconstruction.

Two judgements, matching the report's methodology section:

* ``Ans. Correctness`` -- per-criterion PASS/FAIL against the candidate answer.
  "an LLM-as-a-judge is used to evaluate whether the answer satisfies each
  criterion".
* ``Regulatory Tone``  -- "fraction of responses judged both appropriate and
  clear".

Both are judged THREE times per question at temperature 0.1 and resolved by
majority, because the report states exactly that ("Ans. Correctness and
Regulatory Tone are judged three times per question") and prints the min-max
spread across the three repetitions.  :func:`judge_rows` returns that spread so
our reports can print it the same way.

How strict is the real judge?  The appendix shows it, and it is strict about
SUBSTANCE, not citation.  On Q17 it failed a criterion because the answer
"refers generally to conditions in Article 7(1) but does not state the
specific condition"; on Q45 it failed every criterion because the answer named
Article 13 without enumerating anything.  Pointing at the right provision is
NOT satisfying a criterion.  The prompt below says so in those words, and
:mod:`evals.official.calibration` checks the judge reproduces the fifteen
PASS/FAIL verdicts the appendix prints.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
sys.path.insert(0, str(REPO))

from app.data.provision_text import get_provision_text  # noqa: E402
from evals.official.rubric import normalise_ref, ref_head  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
except ImportError:
    pass

_base = (os.getenv("OPENAI_API_BASE") or "http://127.0.0.1:8000/v1").rstrip("/")
if not _base.endswith("/v1") and not _base.endswith("/chat/completions"):
    _base = _base + "/v1"
_default_url = _base if _base.endswith("/chat/completions") else f"{_base}/chat/completions"
URL = os.getenv("R388_WRAPPER_URL") or _default_url
MODEL = os.getenv("R388_JUDGE_MODEL", "claude-sonnet-5")
if "openrouter.ai" in URL and "/" not in MODEL:
    MODEL = f"anthropic/{MODEL}"

REPEATS = int(os.getenv("R388_JUDGE_REPEATS", "3"))
TEMPERATURE = float(os.getenv("R388_JUDGE_TEMPERATURE", "0.1"))

_token = (
    os.getenv("R388_JUDGE_API_KEY")
    or (os.getenv("OPENROUTER_API_KEY") if "openrouter.ai" in URL else None)
    or os.getenv("OPENAI_API_KEY", "dummy")
)
_HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {_token}",
}
if os.getenv("CF_ACCESS_CLIENT_ID"):
    if "127.0.0.1" not in URL and "localhost" not in URL and "openrouter.ai" not in URL:
        _HDRS["CF-Access-Client-Id"] = os.environ["CF_ACCESS_CLIENT_ID"]
        _HDRS["CF-Access-Client-Secret"] = os.environ.get("CF_ACCESS_CLIENT_SECRET", "")


def configure_judge(
    *,
    provider: str | None = None,
    model: str | None = None,
    grouped: bool | None = None,
) -> None:
    """Apply an explicit judge transport/model for the current scoring run.

    ``score_arm`` imports this module before parsing its CLI, so relying on
    module-import-time environment reads made a command-line model override
    impossible.  Keep the environment in sync as well: worker threads and
    diagnostics read the provider from there on every call.  ``grouped=None``
    leaves ``R388_JUDGE_GROUPED`` as the environment has it.
    """
    global MODEL
    if provider:
        os.environ["R388_JUDGE_PROVIDER"] = provider.strip().lower()
    if model:
        MODEL = model.strip()
        os.environ["R388_JUDGE_MODEL"] = MODEL
    if grouped is not None:
        os.environ["R388_JUDGE_GROUPED"] = "1" if grouped else "0"


def _grouped_enabled() -> bool:
    """R408 — judge correctness and tone of one answer in ONE call (default ON).

    Deny-list truthiness, like the repo's other default-ON gates: only an
    explicit 0 / false / no / off selects the legacy split calls.
    """
    return os.getenv("R388_JUDGE_GROUPED", "1").strip().lower() not in ("0", "false", "no", "off")


def judge_identity() -> str:
    """Stable identity for cache separation and score provenance.

    Grouped verdicts carry a ``:grouped`` segment, so they are never served from
    or written into a split-call cache entry; the split identity is byte-
    identical to the pre-R408 string, so existing caches still hit.  The segment
    sits before ``:r=`` because ``score_arm`` rebuilds the repeat suffix with
    ``rsplit(":r=", 1)``.
    """
    provider = os.getenv("R388_JUDGE_PROVIDER", "wrapper").strip().lower() or "wrapper"
    mode = ":grouped" if _grouped_enabled() else ""
    return f"{provider}:{MODEL}:t={TEMPERATURE}{mode}:r={REPEATS}"


def _parse_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val == 1
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "pass")
    return False


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)
_remark_state = threading.local()


def _call(prompt: str, *, max_tokens: int = 2000, timeout: float = 300.0, retries: int = 3) -> str:
    provider_name = os.getenv("R388_JUDGE_PROVIDER", "").strip().lower()
    if provider_name == "bedrock" or URL.strip().lower() == "bedrock":
        from app.llm.bedrock_client import BedrockRequest, get_bedrock_provider
        provider = get_bedrock_provider()
        # Use the requested model exactly.  The former Claude-name special case
        # silently relabelled a Qwen 235B judgement as Claude, making model A/Bs
        # and audit provenance false.  Callers that need Qwen must request it.
        model_name = MODEL
        req = BedrockRequest(
            user=prompt,
            model=model_name,
            max_tokens=max_tokens,
            temperature=TEMPERATURE,
            timeout_seconds=timeout,
        )
        last: Exception | None = None
        for _ in range(retries):
            try:
                res = provider.complete(req)
                # BedrockProvider is fail-soft: API failures are returned in
                # ``res.error`` rather than raised.  Treat them as failed
                # attempts so the judge transport guard can reject the run.
                if res.error or not res.text:
                    last = RuntimeError(res.error or "empty Bedrock judge response")
                    continue
                return res.text
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise RuntimeError(f"judge call via bedrock failed after {retries} attempts: {last}")

    body = json.dumps(
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": TEMPERATURE,
        }
    ).encode()
    last: Exception | None = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers=_HDRS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode())
            return d["choices"][0]["message"]["content"] or ""
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"judge call failed after {retries} attempts: {last}")


def _parse(text: str):
    t = _FENCE.sub("", text or "").strip()
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = t.find(opener), t.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(t[i : j + 1])
            except Exception:  # noqa: BLE001
                continue
    return None


CORRECTNESS_PROMPT = """You are the LLM-as-a-judge for an EU AI Act question-answering benchmark (Regulation (EU) 2024/1689).

You are given a QUESTION, a set of CORRECTNESS CRITERIA, and a CANDIDATE ANSWER. For EACH criterion, decide whether the candidate answer satisfies it.

HOW TO JUDGE - this is the part that matters:
- A criterion is satisfied only when the candidate answer STATES THE SUBSTANCE of it. Naming or citing the provision that contains the fact is NOT enough. "The conditions are set out in Article 7(1)" does NOT satisfy a criterion that names one of those conditions.
- The answer may use different words. Judge meaning, not phrasing.
- A criterion that is a bare verdict ("Yes" / "No") is satisfied only when the answer's actual position matches it. An answer that leads with the opposite verdict and later concedes the point does NOT satisfy it - the verdict must be the answer's unambiguous position.
- Extra correct material in the answer neither satisfies nor breaks a criterion. Judge each criterion on its own.
- An answer that declines to answer, or says the material available does not permit an answer, satisfies NOTHING.
- Do not reward an answer for being long. Do not punish it for being short.

VERBATIM STATUTORY TEXT (ground truth - use it to resolve any dispute about what the Act says):
{provisions}

QUESTION:
{question}

CRITERIA:
{criteria}

CANDIDATE ANSWER:
{answer}

Return ONLY this JSON object, no markdown fence, no prose. One entry per criterion, in order:
{{"verdicts": [{{"n": 1, "satisfied": true, "why": "one short sentence"}}]}}"""


TONE_PROMPT = """You are the LLM-as-a-judge for the REGULATORY TONE axis of an EU AI Act question-answering benchmark.

Judge whether the response is BOTH appropriate AND clear for a professional regulatory-advice setting with respect to the guidelines and few-shot examples below.

APPROPRIATE means: professional and measured; does not lecture, moralise, or editorialise; does not address the reader informally; does not talk about itself, its retrieval, its knowledge base, its "supplied materials", or its own limitations; does not hedge into uselessness.
CLEAR means: readable, well-ordered prose that a compliance professional could act on; not a wall of fragments; not internally contradictory.

Correctness is NOT your concern. A wrong answer in impeccable regulatory prose passes this axis.

FEW-SHOT EXAMPLES:

Example 1 (PASS):
Question: What is a high-risk AI system under Article 6?
Response: Under Article 6(2), AI systems referred to in Annex III are considered high-risk, unless they do not pose a significant risk of harm to the health, safety or fundamental rights of natural persons pursuant to the derogation conditions in Article 6(3). Additionally, systems that are safety components of products covered by Union harmonisation legislation listed in Annex I requiring third-party conformity assessment are high-risk under Article 6(1).
Verdict: {{"appropriate": true, "clear": true, "why": "Professional, neutral third-person register with clear structure."}}

Example 2 (FAIL - inappropriate self-referential / meta-commentary):
Question: Does our emotion recognition system in the office violate the EU AI Act?
Response: Based on my knowledge base and the materials provided to me, I believe that your system is prohibited. However, as an AI I cannot give legal advice and my graph does not contain the latest case law.
Verdict: {{"appropriate": false, "clear": true, "why": "Refers to itself, its knowledge base, and gives conversational disclaimer hedging."}}

Example 3 (FAIL - unclear / fragmented):
Question: What obligations apply to deployers under Article 26?
Response: Deployers must take measures. Technical documentation. Article 14 human oversight. Also logs if they control them. Not clear if applies.
Verdict: {{"appropriate": true, "clear": false, "why": "Fragmented, incomplete sentences lacking coherent grammatical structure."}}

QUESTION:
{question}

RESPONSE:
{answer}

Return ONLY this JSON object, no markdown fence, no prose:
{{"appropriate": true, "clear": true, "why": "one short sentence"}}"""


def _provisions_for(refs, budget: int = 8000) -> str:
    wanted: list[str] = []
    for r in refs or []:
        n = normalise_ref(r)
        if not n:
            continue
        if n not in wanted:
            wanted.append(n)
    chunks, used = [], 0
    for w in wanted:
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


def judge_correctness_once(row: dict) -> list[bool] | None:
    criteria = row.get("criteria") or []
    if not criteria:
        return []
    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(criteria, 1))
    provisions = _provisions_for(
        row.get("expected_refs") or row.get("_fallback_refs") or []
    )
    ans_text = (row.get("answer") or "").strip() or "(the system returned no answer)"
    prompt = (
        CORRECTNESS_PROMPT
        .replace("{provisions}", provisions)
        .replace("{question}", row.get("question") or "")
        .replace("{criteria}", numbered)
        .replace("{answer}", f"<candidate_answer>\n{ans_text}\n</candidate_answer>")
    )
    try:
        raw = _call(prompt)
    except Exception:
        return None
    d = _parse(raw)
    if not isinstance(d, dict):
        return None
    verdicts = d.get("verdicts")
    if not isinstance(verdicts, list):
        return None
    parsed, remarks = _verdicts_from(verdicts, len(criteria))
    if parsed is not None:
        _remark_state.correctness = remarks
    return parsed


def _verdicts_from(verdicts: list, n_criteria: int) -> tuple[list[bool] | None, list[str]]:
    """Per-criterion booleans and remarks out of a judge's ``verdicts`` list.

    Accepts 1-based ``n`` (the contract), 0-based ``n``, or an unnumbered list
    of exactly ``n_criteria`` entries; anything else is ``(None, [])``.
    """
    by_n = {}
    remarks_by_n: dict[int, str] = {}
    for v in verdicts:
        if isinstance(v, dict) and "n" in v:
            try:
                item_n = int(v["n"])
                by_n[item_n] = _parse_bool(v.get("satisfied"))
                remarks_by_n[item_n] = str(v.get("why") or "").strip()
            except Exception:
                continue
    if 0 in by_n and n_criteria not in by_n:
        by_n = {k + 1: v for k, v in by_n.items()}
        remarks_by_n = {k + 1: v for k, v in remarks_by_n.items()}
    if len(by_n) < n_criteria:
        flat = [_parse_bool(v.get("satisfied")) for v in verdicts if isinstance(v, dict)]
        if len(flat) != n_criteria:
            return None, []
        return flat, [str(v.get("why") or "").strip() for v in verdicts if isinstance(v, dict)]
    return (
        [by_n.get(i, False) for i in range(1, n_criteria + 1)],
        [remarks_by_n.get(i, "") for i in range(1, n_criteria + 1)],
    )


def _tone_from(d: dict) -> tuple[bool, str]:
    return (
        _parse_bool(d.get("appropriate")) and _parse_bool(d.get("clear")),
        str(d.get("why") or "").strip(),
    )


def judge_tone_once(row: dict) -> bool | None:
    ans_text = (row.get("answer") or "").strip() or "(the system returned no answer)"
    prompt = (
        TONE_PROMPT
        .replace("{question}", row.get("question") or "")
        .replace("{answer}", f"<candidate_response>\n{ans_text}\n</candidate_response>")
    )
    try:
        raw = _call(prompt, max_tokens=400)
    except Exception:
        return None
    d = _parse(raw)
    if not isinstance(d, dict):
        return None
    tone, _remark_state.tone = _tone_from(d)
    return tone


# R408 — both judgements read the SAME answer, so they share one call. The rule
# text of each half is CORRECTNESS_PROMPT / TONE_PROMPT verbatim, so grouping is
# the only thing that changes between the two modes.
GROUPED_PROMPT = """You are the LLM-as-a-judge for an EU AI Act question-answering benchmark (Regulation (EU) 2024/1689).

You are given a QUESTION, a set of CORRECTNESS CRITERIA, and a CANDIDATE ANSWER. Make TWO INDEPENDENT judgements of that one answer and return both in a single JSON object.

JUDGEMENT 1 - ANSWER CORRECTNESS. For EACH criterion, decide whether the candidate answer satisfies it.

HOW TO JUDGE - this is the part that matters:
- A criterion is satisfied only when the candidate answer STATES THE SUBSTANCE of it. Naming or citing the provision that contains the fact is NOT enough. "The conditions are set out in Article 7(1)" does NOT satisfy a criterion that names one of those conditions.
- The answer may use different words. Judge meaning, not phrasing.
- A criterion that is a bare verdict ("Yes" / "No") is satisfied only when the answer's actual position matches it. An answer that leads with the opposite verdict and later concedes the point does NOT satisfy it - the verdict must be the answer's unambiguous position.
- Extra correct material in the answer neither satisfies nor breaks a criterion. Judge each criterion on its own.
- An answer that declines to answer, or says the material available does not permit an answer, satisfies NOTHING.
- Do not reward an answer for being long. Do not punish it for being short.

JUDGEMENT 2 - REGULATORY TONE. Judge whether the response is BOTH appropriate AND clear for a professional regulatory-advice setting with respect to the guidelines and few-shot examples below.

APPROPRIATE means: professional and measured; does not lecture, moralise, or editorialise; does not address the reader informally; does not talk about itself, its retrieval, its knowledge base, its "supplied materials", or its own limitations; does not hedge into uselessness.
CLEAR means: readable, well-ordered prose that a compliance professional could act on; not a wall of fragments; not internally contradictory.

Correctness is NOT a tone concern. A wrong answer in impeccable regulatory prose passes judgement 2. Make judgement 2 without regard to your verdicts in judgement 1.

TONE FEW-SHOT EXAMPLES:

Example 1 (PASS):
Question: What is a high-risk AI system under Article 6?
Response: Under Article 6(2), AI systems referred to in Annex III are considered high-risk, unless they do not pose a significant risk of harm to the health, safety or fundamental rights of natural persons pursuant to the derogation conditions in Article 6(3). Additionally, systems that are safety components of products covered by Union harmonisation legislation listed in Annex I requiring third-party conformity assessment are high-risk under Article 6(1).
Verdict: {{"appropriate": true, "clear": true, "why": "Professional, neutral third-person register with clear structure."}}

Example 2 (FAIL - inappropriate self-referential / meta-commentary):
Question: Does our emotion recognition system in the office violate the EU AI Act?
Response: Based on my knowledge base and the materials provided to me, I believe that your system is prohibited. However, as an AI I cannot give legal advice and my graph does not contain the latest case law.
Verdict: {{"appropriate": false, "clear": true, "why": "Refers to itself, its knowledge base, and gives conversational disclaimer hedging."}}

Example 3 (FAIL - unclear / fragmented):
Question: What obligations apply to deployers under Article 26?
Response: Deployers must take measures. Technical documentation. Article 14 human oversight. Also logs if they control them. Not clear if applies.
Verdict: {{"appropriate": true, "clear": false, "why": "Fragmented, incomplete sentences lacking coherent grammatical structure."}}

VERBATIM STATUTORY TEXT (ground truth for judgement 1 - use it to resolve any dispute about what the Act says):
{provisions}

QUESTION:
{question}

CRITERIA:
{criteria}

CANDIDATE ANSWER:
{answer}

Return ONLY this JSON object, no markdown fence, no prose. "verdicts" has one entry per criterion, in order:
{{"verdicts": [{{"n": 1, "satisfied": true, "why": "one short sentence"}}], "tone": {{"appropriate": true, "clear": true, "why": "one short sentence"}}}}"""


def judge_grouped_once(row: dict) -> tuple[list[bool] | None, bool | None]:
    """R408 — ONE call returns both judgements of the same answer.

    Returns ``(criteria, tone)``. Either half is ``None`` when that half did not
    parse, so a reply that drops the tone object still scores its criteria and
    the caller can see the missing tone run. A row with no criteria needs no
    correctness judgement, so it costs exactly the legacy tone call.
    """
    criteria = row.get("criteria") or []
    if not criteria:
        return [], judge_tone_once(row)
    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(criteria, 1))
    provisions = _provisions_for(
        row.get("expected_refs") or row.get("_fallback_refs") or []
    )
    ans_text = (row.get("answer") or "").strip() or "(the system returned no answer)"
    prompt = (
        GROUPED_PROMPT
        .replace("{provisions}", provisions)
        .replace("{question}", row.get("question") or "")
        .replace("{criteria}", numbered)
        .replace("{answer}", f"<candidate_answer>\n{ans_text}\n</candidate_answer>")
    )
    try:
        raw = _call(prompt)
    except Exception:
        return None, None
    d = _parse(raw)
    if not isinstance(d, dict):
        return None, None
    corr: list[bool] | None = None
    if isinstance(d.get("verdicts"), list):
        corr, remarks = _verdicts_from(d["verdicts"], len(criteria))
        if corr is not None:
            _remark_state.correctness = remarks
    tone_obj = d.get("tone")
    if not isinstance(tone_obj, dict) and "appropriate" in d and "clear" in d:
        tone_obj = d
    tone: bool | None = None
    if isinstance(tone_obj, dict):
        tone, _remark_state.tone = _tone_from(tone_obj)
    return corr, tone


def _majority(runs: list, n_criteria: int) -> list[bool]:
    """Per-criterion majority across the repetitions; ties resolve to FAIL.

    Ties only arise when a repetition errored out and an even number survive.
    Resolving a tie to FAIL keeps the instrument from flattering the arm on
    exactly the rows the judge found hardest.
    """
    live = [r for r in runs if r is not None and len(r) == n_criteria]
    if not live:
        return [False] * n_criteria
    return [sum(1 for r in live if r[i]) * 2 > len(live) for i in range(n_criteria)]


def judge_row(row: dict, repeats: int = REPEATS) -> dict:
    """Judge one captured row; returns criteria booleans, tone, and spread.

    Grouped (the R408 default): each repetition is ONE call returning both
    judgements. Split: a correctness call and a tone call per repetition.
    """
    n = len(row.get("criteria") or [])
    corr_runs = []
    corr_remarks_runs: list[list[str]] = []
    tone_runs = []
    tone_remarks_runs: list[str] = []
    if _grouped_enabled():
        for _ in range(repeats):
            _remark_state.correctness = []
            _remark_state.tone = ""
            corr, tone = judge_grouped_once(row)
            corr_runs.append(corr)
            corr_remarks_runs.append(list(getattr(_remark_state, "correctness", [])))
            tone_runs.append(tone)
            tone_remarks_runs.append(str(getattr(_remark_state, "tone", "")))
    else:
        for _ in range(repeats):
            _remark_state.correctness = []
            corr_runs.append(judge_correctness_once(row))
            corr_remarks_runs.append(list(getattr(_remark_state, "correctness", [])))
        for _ in range(repeats):
            _remark_state.tone = ""
            tone_runs.append(judge_tone_once(row))
            tone_remarks_runs.append(str(getattr(_remark_state, "tone", "")))
    criteria = _majority(corr_runs, n)
    live_corr = [r for r in corr_runs if r is not None and len(r) == n]
    per_run_rate = [sum(1 for c in r if c) / n for r in live_corr] if (live_corr and n) else []
    live_tone = [t for t in tone_runs if t is not None]
    criterion_remarks: list[str] = []
    for idx, majority_value in enumerate(criteria):
        remark = ""
        for run, run_remarks in zip(corr_runs, corr_remarks_runs, strict=False):
            if (
                run is not None
                and len(run) == n
                and run[idx] == majority_value
                and idx < len(run_remarks)
                and run_remarks[idx]
            ):
                remark = run_remarks[idx]
                break
        criterion_remarks.append(remark)

    tone_ok = (
        (sum(1 for t in live_tone if t) * 2 > len(live_tone))
        if live_tone
        else False
    )
    tone_remark = ""
    for run_value, run_remark in zip(tone_runs, tone_remarks_runs, strict=False):
        if run_value is not None and run_value == tone_ok and run_remark:
            tone_remark = run_remark
            break
    return {
        "criteria": criteria,
        "criterion_remarks": criterion_remarks,
        "tone_ok": tone_ok,
        "tone_remark": tone_remark,
        "_judge_runs": len(live_corr),
        "_criteria_rate_min": round(min(per_run_rate), 4) if per_run_rate else None,
        "_criteria_rate_max": round(max(per_run_rate), 4) if per_run_rate else None,
        "_tone_runs": len(live_tone),
        "_corr_runs": corr_runs,
        "_tone_runs_raw": tone_runs,
        "_judge_errors": repeats - len(live_corr),
    }


def judge_rows(
    rows: list[dict],
    *,
    workers: int = 4,
    repeats: int = REPEATS,
    on_row: Any = None,
) -> list[dict]:
    """Judge many rows; returns each row augmented in place-order."""

    def _one(r):
        try:
            out = dict(r)
            out.update(judge_row(r, repeats=repeats))
        except Exception as exc:  # noqa: BLE001
            out = dict(r)
            out.update(
                {
                    "criteria": [False] * len(r.get("criteria") or []),
                    "tone_ok": False,
                    "_judge_runs": 0,
                    "_judge_errors": repeats,
                    "_judge_exception": str(exc),
                }
            )
        if on_row is not None:
            try:
                on_row(out)
            except Exception as exc:  # noqa: BLE001 — a checkpoint failure must not kill the run
                print(f"  checkpoint callback failed for {out.get('id')}: {exc}", flush=True)
        return out

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_one, rows))
