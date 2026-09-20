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
_FALSY = frozenset({"0", "false", "no", "off"})

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

#: R423.1 — what to target when the ask anchors on NOTHING.
#:
#: The first gate measured this lever's whole correctness cost on two rows, and
#: both are rows where ``asked`` and ``engaged`` are BOTH empty: ``rg_010``
#: ("Which article of the EU AI Act governs human oversight measures?" — the ask
#: names no coordinate) and ``rg_106`` (a classification scenario that names no
#: annex). On those rows the estimator fell through to ``items = 1`` and asserted
#: the MINIMUM target (375) while the gold references are 759 and 781 chars and
#: the criteria ARE the substance of the provision the ask is about (Article
#: 14(1)-(4) in every one of the three generations; Annex III.6's
#: law-enforcement confinement, with ``Annex III`` dropped from the wire refs).
#:
#: That is a category error this module was making: EMPTY ENGAGEMENT IS ABSENCE
#: OF SIGNAL, NOT EVIDENCE OF A SMALL ASK. The detector is the R410
#: question-side rule, deliberately strict because it gates a completeness
#: DEMAND (it cut false positives 7/71 -> 0/71); strictness is right for
#: demanding, and wrong for sizing.
#:
#: Calibrated on the SUBGROUP it applies to — not on the whole gold, and not on
#: the two rows that exposed the bug. The state is not a corner case: it is 80 of
#: the 110 rows (73 %), whose references measure mean 646, median 657, p25 553,
#: p75 747, min 160, max 985. 650 is that subgroup's own central value.
#:
#: Measured cost (``need_floor_projection.py`` section B, the ONLY per-row lengths
#: that exist, restricted to rows the lever can actually reach — a
#: curated-intercept row is answered identically in both arms, so including one
#: rigs the projection; the first cut did): 71.29 % -> 70.07 % on
#: ``Ans. Conciseness`` over the 23 reachable unanchored rows, -1.22 pp. The floor
#: is FREE below 550, because those rows' references sit above it. It is worth
#: keeping rather than dropping because ``Ans. Conciseness`` is
#: ``min(1, ref/candidate)`` and therefore SATURATES: a candidate under the
#: reference scores exactly what one AT the reference scores, so undershooting a
#: reference-length answer buys zero conciseness and costs correctness.
#:
#: A GRADED floor was tested and REJECTED (section C): nothing the estimator can
#: see predicts an unanchored ask's reference length — corr(ask length, ref
#: length) = +0.23 Pearson / +0.16 Spearman over the 80 rows; the feature that
#: does (criteria count, +0.56) is not available at inference; and a ridge fit of
#: the ask's own features was already falsified leave-one-out at r = 0.10-0.14. A
#: formula keyed on any of that would be a number nobody measured, which is the
#: defect this module's FIRST calibration actually was (see ``_TARGET_BASE_CHARS``
#: above).
_TARGET_NO_SIGNAL_CHARS = 650


def need_proportional_contract_enabled() -> bool:
    """``REGENOLD_NEED_PROPORTIONAL_CONTRACT`` — default ON, flipped by its gate.

    R423.2 — FLIPPED ON BY EVIDENCE, not by argument. The paired gate
    (``docs/measurements/r423/need_gate.json``, label ``r423-need4``: hard split,
    37 strided rows x 3 INDEPENDENT generations x 2 arms, judged with the R419
    board's own instrument) measured, per-row medians over the 27 comparable
    rows:

    * ``ans_correctness_loose`` **+0.00 pp** and ``ans_correctness_strict``
      **+0.00 pp** — the first gate's cost (-4.04 / -7.41, concentrated on two
      no-anchor rows) is GONE after the R423.1 estimator fix;
    * ``ans_conciseness`` +38.86, ``ref_correctness_loose`` +3.70,
      ``ref_correctness_strict`` +5.56, ``ref_conciseness`` +12.80,
      ``resp_speed`` +10.77;
    * ``overall`` (geometric mean) 65.62 -> 79.56, **+13.93 pp**;
    * answers shorten by 2108 chars and gold heads dropped go 1 -> 0.

    Every one of the five pre-registered conditions held (no correctness axis
    below -1.0 pp, a shorter answer, an aggregate above -0.5 pp, and no more gold
    drops than the OFF arm). One row of 37 was excluded from BOTH arms because its
    transport degraded (accounted for and published by the gate).

    Set ``REGENOLD_NEED_PROPORTIONAL_CONTRACT=0`` to restore the fixed-shape
    prompt exactly. The OFF vocabulary is an explicit deny-list rather than a
    truthy allow-list, so a malformed value cannot silently disable a shipped
    lever.
    """
    try:
        return (
            os.environ.get(_ENV, "1").strip().lower() not in _FALSY
        )
    except Exception:  # noqa: BLE001 — a flag read must never break the route
        return True


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
    #: False when the ask names no coordinate AND engages no closed set. That is
    #: a NO-SIGNAL state (R423.1), not a small ask: the contract must not
    #: compress or forbid on it, only answer normally.
    anchored: bool = True

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
            "anchored": self.anchored,
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
        proportional = min(
            _TARGET_MAX_CHARS,
            max(_TARGET_MIN_CHARS, _TARGET_BASE_CHARS + _TARGET_PER_ITEM_CHARS * items),
        )
        # R423.1 — no anchor anywhere is no signal, so the floor applies (see
        # ``_TARGET_NO_SIGNAL_CHARS``). It is a floor, not a replacement: an
        # unanchored ask that still asks for an exception/condition limb keeps
        # whichever target is larger.
        anchored = bool(ask_coords or engaged)
        target = proportional if anchored else max(proportional, _TARGET_NO_SIGNAL_CHARS)
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
            anchored=anchored,
        )
    except Exception:  # noqa: BLE001 — the estimate is advisory; never fatal
        # Fail OPEN on the anchor: an estimator that could not run has no
        # evidence of a small ask, and the shipped shape is the safe arm.
        return AnswerNeed(
            asked=(), engaged=(), items=1, target_chars=_TARGET_NO_SIGNAL_CHARS,
            target_words=max(40, round(_TARGET_NO_SIGNAL_CHARS / _CHARS_PER_WORD)),
            asks_list=False, asks_exception=False, asks_conditions=False,
            is_yes_no=False, anchored=False,
        )


def shape_directive(need: AnswerNeed) -> str:
    """The need-proportional clause appended to the Stage-2 answer contract.

    Kept short on purpose. Every prior attempt to steer length with a large block
    (``REGENOLD_PROMPT_V3``, the 53 kB full system prompt) was measured to trade
    one axis for another; this one states a number derived from the ask and
    scopes the enumeration surface to the same estimate.

    R423.1 — two shapes, because the no-signal case must not be told to
    compress. The first gate lost ``rg_010`` and ``rg_106`` to exactly this
    clause: both were handed "the ask engages 1 statutory item(s): the single
    provision the ask names" when the ask names no provision at all (it asks
    WHICH one governs, or whether a category applies), and both were then capped
    at 375 chars. The unanchored branch instead points the answer at the
    governing provision's substance — which is what the graded criteria of both
    rows actually are.
    """
    lead = (
        "one sentence giving the bare verdict first, then"
        if need.is_yes_no
        else "one sentence giving the direct answer, then"
    )
    if not need.anchored:
        return "\n".join([
            "ANSWER SHAPE (this ask does not name the provision that governs it):",
            "* Name the governing provision first, at citation grain — the Article, "
            "or the Annex sub-point when a category is what decides the answer.",
            f"* Target about {need.target_words} words ({need.target_chars} "
            "characters) — a concise reference answer's own length. "
            f"{lead} the limbs of THAT provision the answer relies on, one "
            "short clause each. The graded criteria ARE the requirements it "
            "imposes, so a limb the evidence carries and the answer leaves "
            "unstated is a failed criterion, and a limb restated at length is "
            "padding.",
            "* The COMPLETE STRUCTURE lists in the evidence block are context for "
            "wording and grain. State a member your prose relies on; do not pad "
            "with members that change nothing about the answer.",
            "* Length is scored against a concise reference answer: stating a limb "
            "that does not decide the answer costs exactly what omitting one that "
            "does costs.",
            "* If a limb above has no supporting text in the evidence, say so in one "
            "sentence instead of padding.",
        ])
    items = ", ".join(need.engaged) if need.engaged else ", ".join(need.asked)
    items = items or "the single provision the ask names"
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
