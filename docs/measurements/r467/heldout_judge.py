"""R467 — grade held-out answers against the review-derived reference positions.

Each answer in a run file (``heldout_rerun.py`` output) is graded by an
independent model over the local Claude Max wrapper (``claude-sonnet-5``; the
production answers come from Claude Opus 5.5 or from pre-drafted statutory text)
against the reference position for its family. The reference positions are the
ones the R465 pairwise A/B used (``scratch/r465_ab_corpus.json``), each derived
from the October 2026 review's corrected answer or correct position. The wrapper
drops the system slot, so the whole instruction travels in the user message.

Verdicts: ``correct`` (no legal error, nothing material the question needs is
missing), ``partly`` (no legal error, a material omission), ``incorrect`` (at
least one legal error, including facts the question does not state presented as
given). Sequential, one call per answer, temperature 0.

Usage (repo root, wrapper on 127.0.0.1:8000):
    .venv/Scripts/python.exe docs/measurements/r467/heldout_judge.py RUN.json OUT.json

When OUT.json already exists, its judgements are kept for rows whose answer is
unchanged, and only the rows without a verdict (a wrapper error or an unparsed
reply) are judged again.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WRAPPER = "http://127.0.0.1:8000/v1/chat/completions"
MODEL = "claude-sonnet-5"

PROMPT = """You are grading an answer about the EU AI Act, Regulation (EU) 2024/1689 as adopted on 13 June 2024. Ignore later amendments.

QUESTION:
{question}

REFERENCE POSITION (written by a legal expert for this family of questions; it may cover more than this question asks):
{reference}

ANSWER UNDER REVIEW:
{answer}

Grade only what the QUESTION asks, using the reference position and the Act. Verdicts:
- "correct": no legal error, and nothing material that the question needs is missing.
- "partly": no legal error, but a material omission (a condition, exception, limb or actor the question needs).
- "incorrect": at least one legal error. Presenting a fact the question does not state (for example the asker's role, or a device class) as given counts as an error, as does a wrong provision or a wrong conclusion.

Reply with JSON only, no other text:
{{"verdict": "correct|partly|incorrect", "errors": ["..."], "omissions": ["..."], "reason": "one sentence"}}"""


def _references() -> dict[str, str]:
    refs: dict[str, str] = {}
    for row in json.loads((REPO / "scratch" / "r465_ab_corpus.json").read_text(encoding="utf-8")):
        refs.setdefault(row["family"], row["reference"])
    return refs


def _judge(question: str, reference: str, answer: str) -> dict:
    body = json.dumps({
        "model": MODEL,
        "temperature": 0,
        "max_tokens": 700,
        "messages": [{"role": "user", "content": PROMPT.format(
            question=question, reference=reference, answer=answer)}],
    }).encode("utf-8")
    req = urllib.request.Request(WRAPPER, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["choices"][0]["message"]["content"]
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {"verdict": "unparsed", "raw": text[:500]}
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return {"verdict": "unparsed", "raw": text[:500]}
    parsed["model"] = data.get("model", MODEL)
    return parsed


_VERDICTS = {"correct", "partly", "incorrect"}


def _previous(path: Path) -> dict[str, dict]:
    """Judgements already on disk, keyed by row id, for answers that have a verdict."""
    if not path.exists():
        return {}
    kept = {}
    for item in json.loads(path.read_text(encoding="utf-8"))["rows"]:
        if item.get("judgement", {}).get("verdict") in _VERDICTS:
            kept[item["id"]] = item
    return kept


def main() -> int:
    run = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    refs = _references()
    previous = _previous(Path(sys.argv[2]))
    out = {"run": sys.argv[1], "commit": run.get("commit"), "judge_model": MODEL, "rows": []}
    for row in run["rows"]:
        if "error" in row:
            out["rows"].append({**row, "judgement": {"verdict": "no_answer"}})
            continue
        done = previous.get(row["id"])
        if done is not None and done.get("answer") == row["answer"]:
            out["rows"].append({**row, "judgement": done["judgement"]})
            continue
        t0 = time.time()
        try:
            judgement = _judge(row["question"], refs[row["family"]], row["answer"])
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
            judgement = {"verdict": "judge_error", "error": repr(exc)[:200]}
        judgement["seconds"] = round(time.time() - t0, 1)
        out["rows"].append({**row, "judgement": judgement})
        print(f"{row['id']}: {judgement.get('verdict')} ({judgement['seconds']}s)", flush=True)
    counts: dict[str, int] = {}
    for item in out["rows"]:
        verdict = item["judgement"]["verdict"]
        counts[verdict] = counts.get(verdict, 0) + 1
    out["counts"] = counts
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
