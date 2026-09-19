"""R423 — the need-proportional answer contract.

MEASURED PROBLEM (R422, ``docs/measurements/r422/CHECKPOINT.md``)
----------------------------------------------------------------
The hard-mode answer does not modulate with the question. Against R390 live hard
(same 110 questions, same gold, same generator — opus-5 over the wrapper):

* mean graded answer 1139 -> 2138 chars, ``ans_conciseness`` 62.02 -> 44.19;
* ``corr(gold criteria count, reference length) = +0.55`` (202 chars/criterion)
  while ``corr(gold criteria count, OUR answer length) = +0.11``;
* the 57 rows needing 2-3 limbs score 42.0 % while the 5 six-limb rows score
  54.9 % — i.e. the axis is worst exactly where most of the board sits.

The prompt scaffolding is injected just as flatly: ``REGENOLD_CLOSED_SET_SKELETON``
fires on **110/110** rows for a mean **5,125** chars, including **5,862** chars on
the four 1-criteria rows whose answers average 1,122. And the driver is proven to
be the scaffold's *instruction*, not its size: turning the five post-R390
additions OFF makes the Stage-2 payload **larger** (44,997 vs 38,467 chars) and the
answer *longer*.

WHAT THIS MODULE IS
-------------------
One deterministic estimate of how much statute a question actually engages, and
two renderings of it:

1. :func:`answer_need` — the estimate (fully offline, stdlib + the repo's own
   statutory hierarchy; no LLM, no route, no network).
2. :func:`shape_directive` — the prompt clause that makes the target length
   proportional to that estimate instead of a fixed shape.
3. :func:`engaged_coords` — the set the closed-set skeleton should show in full.
   Members outside it are still delivered as *coordinates* (so nothing is hidden
   and no citable head is added) but are labelled context, not required content.

The engagement rule is deliberately REUSED, not reinvented: it is the R410
question-side detector in :mod:`app.engines.answer_completeness` (a group is
engaged when the QUESTION names its parent coordinate or carries a distinctive
chapeau bigram), which was itself measured on the frozen R407 ledger to cut false
positives 7/71 -> 0/71. Sharing it is what keeps this contract from re-introducing
the R409 §6.8 gold-drop mechanism (demanding the full lettered list of a provision
the answer merely cites).

AGENTS.md INVARIANT #5 — this is a PROMPT-side lever. It changes the answer and,
through the prose->refs passes, the wire citations. Its gate is a paired run on
the official hard split with the ``gold_dropped_head`` check, never an argument
from construction.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.engines.answer_completeness import (
    _MIN_GROUP_CHILDREN,
    _ask_text,
    _coord_str,
    _dedupe,
    _groups,
    _paths_in,
    _prefix_closure,
    _question_engages,
    _word_bigrams,
    named_heads,
)

_ENV = "REGENOLD_NEED_PROPORTIONAL_CONTRACT"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: Target-length calibration. MEASURED, and the first version of it was WRONG in
#: a way worth recording (``docs/measurements/r423/need_proportional_probe.py``):
#:
#: * PREDICTING the per-row reference length does not work. A ridge fit of the
#:   ask's own features (length, list/exception/conditions shape, asked heads,
#:   cited heads, sub-point grain) reaches r=0.37 IN SAMPLE and r=0.10-0.12
#:   leave-one-out over the 110 gold rows. corr(items, criteria) is 0.06. So this
#:   module must NOT claim to predict the reference; a per-item slope calibrated
#:   as if it did (280 + 100*items) put the target at 380-1400 chars with no
#:   measured justification for either end.
#: * The axis is dominated by LEVEL, not by per-row shape. ``Ans. Conciseness``
#:   is ``min(1, ref_len/candidate)`` per row, so the projection over the gold's
#:   own references is 0.649 at a flat 1000 chars, 0.912 at 649 (the reference
#:   mean) and 0.960 at 550 — against 0.4419 for the real R419 answers (2138
#:   chars), which recomputes EXACTLY from disk and is the number to beat.
#:
#: What ``items`` is therefore FOR: a monotone FLOOR that scales with what the ask
#: engages, so the contract never demands less than the engaged content needs —
#: the correctness risk that every shortening lever in this repo has paid for
#: (R415: the shorter 53 kB system prompt cost 7.7 pp Ans. Strict). The level is
#: anchored just under the reference mean; 75 chars/item matches the R409 repair
#: budget's own per-gap allowance (``answer_completeness._REPAIR_PER_GAP_CHARS``).
_TARGET_BASE_CHARS = 300
_TARGET_PER_ITEM_CHARS = 75
_TARGET_MIN_CHARS = 360
_TARGET_MAX_CHARS = 1000
_CHARS_PER_WORD = 5.4
_MAX_ITEMS = 12


def need_proportional_contract_enabled() -> bool:
    """``REGENOLD_NEED_PROPORTIONAL_CONTRACT`` — default OFF (opt-in lever).

    Default OFF is the house rule for a lever that changes generation shape: it
    ships behind a paired gate (AGENTS.md hard rule #6), and its OFF arm must be
    byte-identical to the current prompt. Allow-list form, so a blank or malformed
    value keeps the shipped behaviour.
    """
    try:
        return (os.environ.get(_ENV) or "").strip().lower() in _TRUTHY
    except Exception:  # noqa: BLE001 — a flag read must never break the route
        return False


@dataclass(frozen=True)
class AnswerNeed:
    """How much statute one question engages, and the length that implies."""

    asked: tuple[str, ...]
    engaged: tuple[str, ...]
    items: int
    target_chars: int
    target_words: int
    asks_list: bool
    asks_exception: bool
    asks_conditions: bool
    is_yes_no: bool

    @property
    def scope(self) -> str:
        """``lookup`` / ``list`` / ``synthesis`` — the shape of the ask."""
        if self.engaged or self.asks_list:
            return "list"
        if self.items > 2 or self.asks_exception or self.asks_conditions:
            return "synthesis"
        return "lookup"

    def as_dict(self) -> dict[str, object]:
        return {
            "asked": list(self.asked),
            "engaged": list(self.engaged),
            "items": self.items,
            "scope": self.scope,
            "target_chars": self.target_chars,
            "target_words": self.target_words,
            "asks_list": self.asks_list,
            "asks_exception": self.asks_exception,
            "asks_conditions": self.asks_conditions,
            "is_yes_no": self.is_yes_no,
        }


def _deepest(coords: set[str]) -> list[str]:
    """Drop any coordinate that is a prefix of another, in document order.

    ``{Article 13.3, Article 13.3.a}`` means the ask names 13.3 and its lettered
    limbs are the items; counting both would double the target length.
    """
    out = [
        c
        for c in coords
        if not any(o != c and o.startswith(c + ".") for o in coords)
    ]

    def _key(coord: str) -> tuple:
        head, _, tail = coord.partition(".")
        rank = int(head.rsplit(" ", 1)[-1]) if head.lower().startswith("article") else 0
        return (rank, head, tuple(_seg_key(seg) for seg in tail.split(".") if seg))

    return sorted(out, key=_key)


def _seg_key(seg: str) -> tuple[int, int, str]:
    """Numeric-aware sort key: ``2 < 10``, letters after numbers, in order."""
    return (0, int(seg), "") if seg.isdigit() else (1, 0, seg)


def engaged_coords(question: str, references: str = "") -> tuple[str, ...]:
    """Coordinates of the closed-set members this QUESTION engages, deepest first.

    Heads are taken from the ask AND from the evidence block: the evidence is
    where the candidate provisions live, and the engagement test — not the
    citation set — is what decides. Returns ``()`` when nothing is engaged, which
    is the common case for a lookup, and the caller then renders the shipped
    block unchanged.

    Fail-open on any exception: an estimator that raises must never take down
    Stage-2, and an empty result is the shipped behaviour.
    """
    try:
        ask = _ask_text(question)
        if not ask.strip():
            return ()
        ask_paths = _paths_in(ask)
        ask_coords = {_coord_str(p) for p in ask_paths} | _prefix_closure(ask_paths)
        q_bigrams = _word_bigrams(ask)
        heads = _dedupe([*named_heads(ask), *named_heads(references)])
        if not heads:
            return ()
        from app.data.provision_hierarchy import closed_set_members  # noqa: PLC0415

        engaged: list[str] = []
        for head in heads:
            try:
                members = closed_set_members(head)
            except Exception:  # noqa: BLE001 — one unresolvable head is not fatal
                continue
            for parent, children in _groups(members):
                if len(children) < _MIN_GROUP_CHILDREN:
                    continue
                if not _question_engages(parent, head, children, ask_coords, q_bigrams):
                    continue
                engaged.extend(coord for coord, _text in children)
        return tuple(_deepest(set(engaged)))
    except Exception:  # noqa: BLE001 — see docstring
        return ()


def answer_need(question: str, references: str = "") -> AnswerNeed:
    """The need estimate: what is asked, what it engages, and the length implied.

    ``items`` is the number of statutory things the answer must state:

    * the deepest distinct coordinates the ask names (``Article 13.3`` is one
      item; ``Articles 13.3 and 27`` is two);
    * the engaged closed-set members, when the ask engages a list;
    * one for an exception/derogation ask and one for a conditions ask, because
      a limb has to be stated on its own.

    Deliberately NOT counted: anything the ask does not engage. That is the
    whole difference from the shipped contract, whose enumeration directive and
    exhaustive skeletons are independent of the ask.
    """
    try:
        from app.engines.answer_completeness import (
            _asks_conditions,
            is_exception_question,
            is_list_question,
            is_yes_no_question,
        )

        ask = _ask_text(question)
        paths = _paths_in(ask)
        ask_coords = {_coord_str(p) for p in paths} | _prefix_closure(paths)
        engaged = engaged_coords(question, references)
        pool = ask_coords | set(engaged)
        deepest_asked = _deepest(pool)
        # A ref or member reached only through engagement is not separately
        # "asked": count the engaged items once, plus any asked coordinate the
        # engagement did not already cover.
        items = len([c for c in deepest_asked if c in ask_coords]) or 1
        if engaged:
            items = max(items, len([c for c in deepest_asked if c in set(engaged)]))
        asks_exception = is_exception_question(question)
        asks_conditions = _asks_conditions(question)
        if asks_exception:
            items += 1
        if asks_conditions:
            items += 1
        items = max(1, min(_MAX_ITEMS, items))
        target = min(
            _TARGET_MAX_CHARS,
            max(_TARGET_MIN_CHARS, _TARGET_BASE_CHARS + _TARGET_PER_ITEM_CHARS * items),
        )
        return AnswerNeed(
            asked=tuple(_deepest(ask_coords)),
            engaged=tuple(engaged),
            items=items,
            target_chars=target,
            target_words=max(40, round(target / _CHARS_PER_WORD)),
            asks_list=is_list_question(question),
            asks_exception=asks_exception,
            asks_conditions=asks_conditions,
            is_yes_no=is_yes_no_question(question),
        )
    except Exception:  # noqa: BLE001 — the estimate is advisory; never fatal
        return AnswerNeed(
            asked=(), engaged=(), items=1, target_chars=_TARGET_MIN_CHARS,
            target_words=max(40, round(_TARGET_MIN_CHARS / _CHARS_PER_WORD)),
            asks_list=False, asks_exception=False, asks_conditions=False,
            is_yes_no=False,
        )


def shape_directive(need: AnswerNeed) -> str:
    """The need-proportional clause appended to the Stage-2 answer contract.

    Kept short on purpose. Every prior attempt to steer length with a large block
    (``REGENOLD_PROMPT_V3``, the 53 kB full system prompt) was measured to trade
    one axis for another; this one states a number derived from the ask and
    scopes the enumeration surface to the same estimate.
    """
    items = ", ".join(need.engaged) if need.engaged else ", ".join(need.asked)
    items = items or "the single provision the ask names"
    lead = (
        "one sentence giving the bare verdict first, then"
        if need.is_yes_no
        else "one sentence giving the direct answer, then"
    )
    lines = [
        "ANSWER SHAPE (proportional to THIS ask):",
        f"* The ask engages {need.items} statutory item(s): {items}.",
        f"* Target about {need.target_words} words ({need.target_chars} characters): "
        f"{lead} one short sentence per engaged item above.",
        "* The COMPLETE STRUCTURE lists in the evidence block describe whole "
        "provisions. Members outside the engaged list are context for wording; "
        "do not enumerate them, and do not add adjacent duties that were not asked.",
        "* Length is scored against a concise reference answer, so stating an "
        "unasked limb lowers the score exactly as omitting an asked one does.",
        "* If a limb above has no supporting text in the evidence, say so in one "
        "sentence instead of padding.",
    ]
    return "\n".join(lines)


def need_proportional_block(question: str, references: str = "") -> str:
    """The clause for this question, or ``""`` when the lever is OFF / disabled."""
    if not need_proportional_contract_enabled():
        return ""
    return shape_directive(answer_need(question, references))
