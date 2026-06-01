"""Per-intent answer-length templates (R38 / Issue A2).

The Regenold rubric scores answer conciseness (length vs gold). Gold
distributions (per agent C research, davidath baseline + Regenold rules
PDF):
* DEFINITION -> 1 sentence, ~140 chars, 1 ref
* BOOLEAN / classification -> 2 sentences, ~260 chars, 2-3 refs
* DESCRIPTION / scenario -> 3-4 sentences, ~500 chars, 5-8 refs
* refusal -> 1 sentence, 0 refs

Template strategy:
1. If answer already fits (within length cap AND sentence budget) ->
   return verbatim.
2. Else extractive trim: pick top-N sentences by question-overlap score
   (re-use sentence_index helpers).
3. Append primary cite anchor if no cite present in trimmed text.
4. Fall-through on unknown qtype: return answer unchanged.

Note: ``INTENT_LENGTH_CAP`` is defined here at module level for R38 Phase 1.
It may be relocated to ``app/integrations/regenold/models.py`` in a later
refactor; downstream callers should keep importing it from this module.
"""
from __future__ import annotations

import re

from app.integrations.regenold.models import MAX_ANSWER_SENTENCES

# R38 Issue A2: per-intent answer length cap (characters). Combined with
# MAX_ANSWER_SENTENCES, drives the answer-template substitution. Gold
# distributions: definitional ~140c, classification ~260c, scenario ~500c.
INTENT_LENGTH_CAP: dict[str, int] = {
    # NOTE: keys MUST be lowercase to match
    # ``app.engines.sentence_index.classify_question`` output (uppercase
    # keys = inert dict — Round-39 eng-review F1).
    "definition": 160,
    "boolean":    280,
    "duration":   140,
    "date":       140,
    "numeric":    160,
    "list":       360,
    "method":     300,
    "role":       300,
    "purpose":    300,
    "description": 500,
}


_SENT_SPLIT_RE = re.compile(r"(?<=[\.\!\?])\s+(?=[A-Z(])")
_CITE_RE = re.compile(r"(?:Article|Annex)\s+\S+", re.I)


def _split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = _SENT_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _budget_sentences(qtype: str) -> int:
    # NOTE: keys MUST be lowercase to match ``classify_question`` output.
    table = {
        "definition": 1,
        "duration":   1,
        "date":       1,
        "numeric":    1,
        "boolean":    2,
        "role":       2,
        "purpose":    2,
        "method":     2,
        "list":       3,
        "description": MAX_ANSWER_SENTENCES,  # 3
    }
    return table.get(qtype, MAX_ANSWER_SENTENCES)


def _has_cite(text: str) -> bool:
    return _CITE_RE.search(text or "") is not None


def apply_template(
    qtype: str,
    answer: str,
    primary_cite: str | None = None,
) -> str:
    """Apply per-intent template. Returns the (possibly trimmed) answer.

    Behavior:
    * Unknown qtype -> return answer unchanged.
    * Fits within length cap + sentence budget -> return verbatim.
    * Exceeds -> trim to N sentences (per ``_budget_sentences``) then to
      length cap (hard cut at last sentence boundary that fits).
    * Trimmed answer with no cite anchor -> append "(<primary_cite>)" if
      provided.
    """
    if not qtype or qtype not in INTENT_LENGTH_CAP:
        return answer
    if not answer:
        return ""
    sentences = _split_sentences(answer)
    if not sentences:
        return answer
    cap_chars = INTENT_LENGTH_CAP[qtype]
    cap_sents = _budget_sentences(qtype)
    # When the answer already contains a cite anchor, treat
    # "(Article N)" trailing in parens as adornment rather than its own
    # sentence — _split_sentences sees ``(`` as a sentence-start, but
    # an already-cited short answer should not be trimmed.
    has_inline_cite = _has_cite(answer)
    effective_sents = (
        len(sentences) - 1
        if has_inline_cite and sentences and sentences[-1].startswith("(")
        else len(sentences)
    )
    if len(answer) <= cap_chars and effective_sents <= cap_sents:
        # Verbatim path -- but still append a missing cite when one is given.
        if not has_inline_cite and primary_cite:
            suffix = f" ({primary_cite})"
            return answer.rstrip(".") + "." + suffix
        return answer
    # Trim sentences
    kept = sentences[:cap_sents]
    out = " ".join(kept).strip()
    # Char-cap: peel sentences from the end until fits
    while len(out) > cap_chars and len(kept) > 1:
        kept = kept[:-1]
        out = " ".join(kept).strip()
    # Append cite if missing — embed BEFORE the trailing punctuation so
    # _split_sentences doesn't count "(Article N)" as a new sentence
    # (the `(` is in its sentence-start lookahead).
    if not _has_cite(out) and primary_cite:
        suffix = f" ({primary_cite})"
        if len(out) + len(suffix) <= cap_chars + 40:
            # Strip terminal punctuation, insert cite, restore the dot.
            stripped = out.rstrip()
            if stripped and stripped[-1] in ".!?":
                out = stripped[:-1] + suffix + stripped[-1]
            else:
                out = stripped + suffix
        else:
            out = out + suffix
    return out
