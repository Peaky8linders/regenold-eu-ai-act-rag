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
import re
from dataclasses import dataclass

from app.data.graph_rag_prompts import UNSETTLED_POINT_RULE
from app.engines.answer_completeness import (
    _MIN_GROUP_CHILDREN,
    _ask_text,
    _coord_str,
    _dedupe,
    _groups,
    _paths_in,
    _prefix_closure,
    _question_engages,
    _sentences,
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

#: R438.1 — the UNSETTLED-POINT bullet, rendered from the ONE shared rule string.
#:
#: It used to read "If a limb above has no supporting text in the evidence, say
#: so in one sentence instead of padding." -- an instruction to describe the
#: MODEL'S OWN INPUTS, which is the one form the delivered contract forbids (see
#: :data:`app.data.graph_rag_prompts.UNSETTLED_POINT_RULE`). The cost was
#: measured on the wrapper arm: the answers that failed R435's Ref. Strict and
#: Tone axes did it with exactly that sentence ("...have no supporting text in
#: the evidence supplied"), which is a self-referential-commentary failure, not a
#: citation error.
#:
#: Substance is unchanged -- say what did not settle, once, instead of padding --
#: and only the FORM moves to the legal one. Rendered from the same constant the
#: coverage clause and the evidence contract use, so the three cannot drift into
#: opposite instructions again.
_UNSETTLED_BULLET = (
    "* If the supplied text does not settle a limb above, " + UNSETTLED_POINT_RULE
    + ", and keep it to one sentence instead of padding."
)


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
        # A named HEAD is not proof that every paragraph is requested: a head's
        # own paragraphs are separate provisions (the rule
        # ``answer_completeness._member_gaps`` already applies). R439 stopped
        # "does Article 26 require logging?" engaging all twelve Article 26
        # paragraphs, which had raised the target to the 1000-character ceiling.
        #
        # R442 — R439 applied that rule to EVERY parent, so it also withheld the
        # list of a named PARAGRAPH whose content IS the enumeration: "When does
        # the Article 6(3) derogation apply?" lost 6(3)(a)-(d) and "What does
        # Article 9(2) require?" lost 9(2)(a)-(d), and the ANSWER SHAPE clause
        # then tells Stage-2 not to enumerate what is outside the engaged set.
        # The rule is scoped back to heads. MEASURED on the route's real inputs
        # for the official 110: identical to R439 on every row (none has that
        # shape), so this restores the R423.2-gated behaviour where R439 had
        # silently removed it and changes nothing the benchmark rows exercise.
        from app.engines.answer_completeness import is_list_question  # noqa: PLC0415

        asks_for_set = is_list_question(ask)
        for head in heads:
            try:
                members = closed_set_members(head)
            except Exception:  # noqa: BLE001 — one unresolvable head is not fatal
                continue
            for parent, children in _groups(members):
                if len(children) < _MIN_GROUP_CHILDREN:
                    continue
                explicit_child = any(
                    coord in ask_coords or any(
                        path.startswith(coord + ".") for path in ask_coords
                    )
                    for coord, _text in children
                )
                if (
                    "." not in parent
                    and parent in ask_coords
                    and not (asks_for_set or explicit_child)
                ):
                    continue
                if not _question_engages(parent, head, children, ask_coords, q_bigrams):
                    continue
                engaged.extend(coord for coord, _text in children)
        return tuple(_deepest(set(engaged)))
    except Exception:  # noqa: BLE001 — see docstring
        return ()


#: R447 — the R442 whole-head floor, gated, and withheld from yes/no asks.
#:
#: R442 applied the no-signal floor whenever the ask named a bare listed head
#: and nothing was engaged, with no flag. The R446 review measured the cost on
#: verdict questions: "Does Article 26 require deployers to keep logs?" and
#: "Under Article 50, must a chatbot disclose ...?" both moved 375 -> 650
#: target chars. A yes/no ask IS a scope signal (a verdict and its reason), so
#: the floor is withheld there; an open ask about a head keeps it, because its
#: size is the head's own content (rg_105, "What is Annex X about?").
#:
#: A first cut instead required a head-as-subject regex. The R447 review
#: measured it losing the floor on ordinary phrasings ("What is Annex X of the
#: AI Act about?", "What's Annex X about?", "Tell me about Annex X.", "What is
#: in Annex IV?") and gaining it on "Articles 4 and 3 percent", so it was
#: replaced by this rule, which keeps R442's own head detection.
#:
#: The yes/no test reads the FIRST interrogative, so an open request in another
#: sentence ("Explain Article 50. Does it apply to chatbots?") still counts as
#: an ask about the whole head (``_OPEN_REQUEST_RE``, review of R447).
#: ``REGENOLD_WHOLE_HEAD_FLOOR=0`` removes the floor (the R439 behaviour).
_WHOLE_HEAD_FLOOR_ENV = "REGENOLD_WHOLE_HEAD_FLOOR"
_OPEN_REQUEST_RE = re.compile(
    r"^\W*(?:what|which|how|why|explain|describe|summari[sz]e|outline|list|compare"
    r"|tell\s+me|give\s+me|walk\s+me\s+through|set\s+out)\b",
    re.IGNORECASE,
)


def _narrow_verdict_ask(question: str, ask: str) -> bool:
    """A yes/no ask with no open request in any of its sentences."""
    from app.engines.answer_completeness import is_yes_no_question  # noqa: PLC0415

    return is_yes_no_question(question) and not any(
        _OPEN_REQUEST_RE.match(sentence) for sentence in _sentences(ask)
    )


def whole_head_floor_enabled() -> bool:
    """``REGENOLD_WHOLE_HEAD_FLOOR`` — default ON (deny-list), as R442 shipped it."""
    try:
        return (
            os.environ.get(_WHOLE_HEAD_FLOOR_ENV, "1").strip().lower() not in _FALSY
        )
    except Exception:  # noqa: BLE001 — a flag read must never break the route
        return True


def _names_whole_listed_head(ask_coords: set[str]) -> bool:
    """Does the ask name a bare HEAD whose own paragraphs form a closed set?"""
    from app.data.provision_hierarchy import closed_set_members  # noqa: PLC0415

    for coord in _deepest(ask_coords):
        if "." in coord:
            continue
        try:
            groups = _groups(closed_set_members(coord))
        except Exception:  # noqa: BLE001 — unresolvable head: no floor from it
            continue
        if any(
            parent == coord and len(children) >= _MIN_GROUP_CHILDREN
            for parent, children in groups
        ):
            return True
    return False


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
        # R442 — an ask about a WHOLE head whose paragraphs the head rule in
        # ``engaged_coords`` withheld carries no scope signal either: "What is
        # Annex X about? What is it used for?" fell from 825 to 375 chars
        # (1 item) against a 625-char reference answer once R439 stopped Annex
        # X's points engaging — the R423.1 length-starvation shape. Same floor.
        # R447 — not on a narrow yes/no ask, and behind a flag; see
        # ``_WHOLE_HEAD_FLOOR_ENV``.
        is_yes_no = is_yes_no_question(question)
        whole_head = (
            not engaged
            and whole_head_floor_enabled()
            and _names_whole_listed_head(ask_coords)
            and not (is_yes_no and _narrow_verdict_ask(question, ask))
        )
        target = (
            proportional
            if anchored and not whole_head
            else max(proportional, _TARGET_NO_SIGNAL_CHARS)
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
            is_yes_no=is_yes_no,
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
            _UNSETTLED_BULLET,
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
        _UNSETTLED_BULLET,
    ]
    return "\n".join(lines)


#: R448 — the concise contract. Opus 5.5 (Stage-2 since 2026-09-24) treats the
#: ANSWER SHAPE "Target about N words" as a suggestion: on the six official
#: appendix questions it wrote 1,040-2,180 chars against 533-985-char reference
#: answers (answer conciseness ~48). This block turns the SAME per-question
#: estimate into a ceiling and bans the unasked material the live answers carry.
#: It changes no estimate, only how the estimate is stated.
_CONCISE_ENV = "REGENOLD_CONCISE_CONTRACT"

#: The direct-question ceiling never exceeds about 700 chars. A question that
#: NAMES a listed head (Annex III, Article 6(2)) engages the whole list, so the
#: need estimate can rise to 900-975 chars on rg_018 / rg_096 while their
#: reference answers are 533 and 596 chars. Opus 5.5 also landed 1.2-1.8x over
#: stated targets (R448 diagnosis), which is why v3 separately reserves up to
#: 180 words for a described multi-branch scenario.
_CONCISE_MAX_WORDS = 130


def concise_contract_enabled() -> bool:
    """``REGENOLD_CONCISE_CONTRACT`` — default ON (deny-list): a blank or
    unexpected value keeps the ON behaviour. ``=0`` renders nothing, so the
    Stage-2 user message is byte-identical to the pre-R448 text."""
    return (
        os.environ.get(_CONCISE_ENV, "1").strip().lower() not in _FALSY
    )


#: R448 v3 — a fact-pattern (scenario) ask gets a larger ceiling. The first
#: production re-check lost one criterion on each of three scenario rows
#: (part2_q07 notified-body competence under Art. 31, part2_q08's clinical-
#: parameter branch, part2_q11's Art. 50(3) exclusion) at ~700 chars: a
#: classification scenario has to walk several branches, and 130 words was too
#: tight for them. Short direct asks keep the 130-word ceiling.
_CONCISE_SCENARIO_MAX_WORDS = 180
#: A described deployment: someone uses / deploys / builds / monitors / sorts
#: with an AI system. R461 — three statutory NOUN PHRASES read as a deployment
#: and are carved out, because a direct ask about them is not a fact pattern
#: and does not need the 180-word ceiling:
#:
#: * a verb form directly followed by "of" is a nominalisation, not an action
#:   ("the use of an AI system", "the high-risk uses of AI", "monitoring of AI
#:   systems"); "use case(s)" is the statutory term the original comment
#:   promised to exclude;
#: * monitor / analyse / sort / screen immediately followed by a noun head is a
#:   compound noun ("the post-market monitoring system", "a screening tool"),
#:   so those four verbs need a word between them and ``system|tool|...``. A bare
#:   ``AI`` after them is still an object ("screening AI").
#:
#: Generic-subject verb forms ("a deployer that uses an AI system must ...") are
#: NOT separable from a described deployment by pattern and stay a documented
#: limit; telling them apart needs an actor-subject rule.
_SCENARIO_OBJECT = r"(?:AI|system|systems|tool|software|model)\b"
_SCENARIO_RE = re.compile(
    r"\b(?:"
    r"(?:use|uses|using|deploy(?:s|ed|ing)?|build(?:s|ing)?|develop(?:s|ed|ing)?)"
    r"\s+(?!(?:of|cases?)\b)(?:[\w-]+\s+){0,3}?" + _SCENARIO_OBJECT +
    r"|"
    r"(?:monitor(?:s|ed|ing)?|analy[sz](?:e|es|ed|ing)|sort(?:s|ed|ing)?|"
    r"screen(?:s|ed|ing)?)"
    r"\s+(?!of\b)(?:AI\b|(?:[\w-]+\s+){1,3}?" + _SCENARIO_OBJECT + r")"
    r")",
    re.IGNORECASE,
)


def is_scenario_question(question: str) -> bool:
    """A fact-pattern ask: a described AI deployment in a 15+ word LIVE ask.

    Judged on :func:`_ask_text`, the live turn (and, after a "Let's try again:"
    re-ask, its asked part), exactly as :func:`answer_need` reads the question.
    Prior turns of a flattened "Conversation so far:" block do not describe THIS
    ask: the hard-mode preamble alone hits the pattern six times, so judging the
    whole string lifted every follow-up to the 180-word / 6-sentence scenario
    ceiling. A single-turn string has no marker and is read unchanged.

    Deliberately NOT the route's ``graphrag_expand.should_expand_for_question``:
    that predicate gates multi-article REFERENCE expansion, is role-declaration
    only and conservative. This one sizes an answer ceiling and is looser. Merging
    them would move wire references.
    """
    q = _ask_text(question or "")
    return len(q.split()) >= 15 and bool(_SCENARIO_RE.search(q))


def concise_limits(need: AnswerNeed, question: str = "") -> tuple[int, int]:
    """(max words, max sentences) for :func:`concise_block`.

    The word ceiling IS the need estimate's own word target, capped at 130
    words; a fact-pattern ask may use up to 180 words and 6 sentences so every
    deciding branch fits. The sentence ceiling allows the lead, one sentence
    per engaged item and one for an exception or condition.
    """
    if is_scenario_question(question):
        # Keep the v3 scenario allowance a hard ceiling. The need estimate can
        # round 1,000 characters up to 185 words, but that must not exceed 180.
        return _CONCISE_SCENARIO_MAX_WORDS, 6
    sentences = min(5, max(3, need.items + 2))
    return min(need.target_words, _CONCISE_MAX_WORDS), sentences


#: The one rule of the LENGTH LIMIT block that mandates MORE provisions than the
#: R460 citation budget allows (four against two). It is a constant shared with
#: :func:`calibration_block`, which names it as its single exception, so the two
#: blocks cannot drift into asking for 4 provisions and capping at 2 (R461).
_BOTH_ROUTES_RULE = (
    "When the question asks which systems or sectors are high-risk, give both "
    "routes: Article 6(1) with Annex I and Article 6(2) with Annex III."
)


def concise_block(
    question: str,
    references: str = "",
    *,
    estimated_need: AnswerNeed | None = None,
) -> str:
    """The LENGTH LIMIT clause, or ``""`` when the lever is OFF.

    A caller that already estimated this question can pass that result so all
    answer-shape clauses use one identical scope and target.
    """
    if not concise_contract_enabled():
        return ""
    try:
        need = (
            estimated_need
            if estimated_need is not None
            else answer_need(question, references)
        )
    except Exception:  # noqa: BLE001 — a prompt add-on must never break Stage-2
        return ""
    words, sentences = concise_limits(need, question)
    lead = "the verdict" if need.is_yes_no else "the direct answer"
    return "\n".join([
        "LENGTH LIMIT (a ceiling for this reply, not a target):",
        f"* At most {words} words in at most {sentences} sentences, written as "
        "plain prose: no bullet points, numbered lists, labels or headings. "
        "This ceiling overrides any larger word target above. Stop as soon as "
        "the question is answered.",
        f"* The first sentence is {lead}.",
        "* State each asked item once as a short clause. For a requested "
        "statutory list, include every required member exactly once in one "
        "compact sentence of short noun phrases separated by commas; never "
        "substitute examples or a summary for the complete list.",
        "* Keep every route, branch, condition or exception that decides the "
        "answer, including a provision the facts make relevant and then rule "
        "out, in one short clause each. " + _BOTH_ROUTES_RULE,
        "* Leave out what does not decide the answer: background, purpose, "
        "procedures, dates, penalties, examples, practical advice, a re-listing "
        "of a whole list the question did not ask to list, and any closing "
        "summary.",
        "* Name only the provisions the answer relies on; every provision you "
        "name becomes a citation.",
        "* On a follow-up or a challenge, keep the earlier answer's points and "
        "length: correct only what is wrong and add nothing new.",
    ])


#: R460 — the calibration lever. Every prior length attempt in this engine was
#: MEASURED to under-deliver: the R448 notes record Opus 5.5 writing 1,040-2,180
#: chars against a per-question estimate that is itself accurate to a median of
#: -36 chars of the reference answer, and the live Cohere boards shipped 1.25x
#: the reference length with 2.0x its citations. The research consensus is that
#: this is a COMPLIANCE problem, not an estimation problem: numeric ceilings plus
#: a COUNTED self-check plus a shape example at the target size is what converts.
#: Default OFF: it changes the answer, so it needs its own gate.
_CALIBRATION_ENV = "REGENOLD_CONCISE_CALIBRATION"

#: The citation budget. The key's own count is ~1.26 refs/row on EVERY shape
#: (110 gold rows: description 1.25, boolean 1.32, list 1.08, definition 1.33),
#: and |expected| <= 2 covers 97% of rows, so 2 is the number that costs no
#: recall for a direct ask. A fact-pattern ask walks several branches and gets 3.
_CALIBRATION_CITATIONS = 2
_CALIBRATION_SCENARIO_CITATIONS = 3

#: R461 - the COUNT-ONLY variant. The R460 wrapper gate (``WRAPPER-CONFIRM.md``)
#: split the block above into two halves that behaved differently on the model
#: that ships: the counted citation budget reproduced on BOTH transports
#: (+5.52 pp ref_conciseness on the wrapper, +4.76 pp on Bedrock) while the length
#: battery (sentence ceiling, word ceiling, shape skeleton) helped on opus-4-6 and
#: made the answer LONGER on opus-5-5 (-4.49 pp ans_conciseness). So the budget is
#: re-gated ALONE, with no length clause of any kind, on the shipped transport.
#: R461 PROMOTION (2026-10-01) - default ON (deny-list), promoted on evidence, not
#: on argument. The paired hard gate on the SHIPPED transport
#: (``COUNT-ONLY-CONFIRM.md``), read under hard rule #8's fixed operating
#: definition (the rows the lever actually served): ref_conciseness 56.62 ->
#: 64.31 (+7.69, CI [+1.41, +15.05], McNemar 10/2 p=0.0386), ans_correctness
#: flat to +0.00, ans_conciseness +0.10 where the full block lost 4.49, answers
#: +6.6 chars where the full block added 64.0, overall +3.80 [+0.58, +9.01]
#: against a noise floor of -0.56 [-6.99, +5.79] on byte-identical prompts: five
#: of five pre-registered targets, and no gold head dropped on any row the block
#: served. ``REGENOLD_CONCISE_COUNT_ONLY=0`` restores the pre-lever bytes exactly
#: and is the rollback; the live evidence is ``docs/measurements/r461/PROMOTION.md``.
_COUNT_ONLY_ENV = "REGENOLD_CONCISE_COUNT_ONLY"

#: The clauses the full block and the count-only variant SHARE. Factored so the
#: difference between the two gated arms is exactly "which clauses are emitted"
#: and never an accidental re-wording of the same instruction. ``{budget}`` is
#: filled per question. Byte-identical to the R460 full block's own text, which
#: the R460 suite pins.
_COUNT_CLAUSE = (
    "* COUNT the provisions the draft NAMES: at most {budget} for this "
    "question. Above that, keep the ones its answer rests on and drop the "
    "clauses about the rest. A provision the facts engage and the answer rules "
    "out still counts."
)
_REFERENCES_CLAUSE = "References: at most {budget} provisions, in citation order."


def calibration_enabled() -> bool:
    """``REGENOLD_CONCISE_CALIBRATION`` - allow-list, default OFF."""
    return os.environ.get(_CALIBRATION_ENV, "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def count_only_enabled() -> bool:
    """``REGENOLD_CONCISE_COUNT_ONLY`` - default ON (deny-list), R461 promotion.

    Mirrors :func:`need_proportional_contract_enabled`: a blank or unexpected
    value keeps the ON behaviour, so a malformed value cannot silently disable a
    shipped lever, and only ``0``/``false``/``no``/``off`` render nothing - which
    leaves the Stage-2 user message byte-identical to the pre-lever text.

    Promoted on the round's own hard gate (see the constant above). The RESOLVED
    mode is keyed in ``_engine_cache_key``, so the flip invalidates the
    pre-promotion cache rather than serving its block-OFF answers.
    """
    try:
        return os.environ.get(_COUNT_ONLY_ENV, "1").strip().lower() not in _FALSY
    except Exception:  # noqa: BLE001 - a flag read must never break the route
        return True


def conciseness_mode() -> str:
    """Which calibration block renders: ``"off"``, ``"count"`` or ``"full"``.

    COUNT-ONLY WINS when both flags are set. The two blocks are alternatives, not
    layers - the full one is the arm whose paired verdict was negative on this
    transport - so a mis-set pair must not silently re-run the refuted arm. After
    the R461 promotion (count-only default ON) that precedence is what keeps the
    refuted arm off the wire: it is reachable only as the explicit pair
    ``REGENOLD_CONCISE_COUNT_ONLY=0 REGENOLD_CONCISE_CALIBRATION=1``, and it is
    keyed as ``concise=full``. This function is the cache key's own term for the
    promotion: the raw env spelling is empty both before and after the flip.
    """
    if count_only_enabled():
        return "count"
    if calibration_enabled():
        return "full"
    return "off"


def calibration_citation_budget(question: str = "") -> int:
    """How many provisions the answer may NAME (the Ref Conciseness count)."""
    return (
        _CALIBRATION_SCENARIO_CITATIONS
        if is_scenario_question(question or "")
        else _CALIBRATION_CITATIONS
    )


def calibration_block(
    question: str,
    references: str = "",
    *,
    estimated_need: AnswerNeed | None = None,
) -> str:
    """The COUNT-BEFORE-YOU-ANSWER block, or ``""`` when the lever is OFF.

    Dispatches on :func:`conciseness_mode`: ``"count"`` renders
    :func:`count_only_block` (the R461 variant - citation budget only), ``"full"``
    renders the R460 block below, ``"off"`` renders nothing.

    Deliberately SHORT. A large steering block has already traded one axis for
    another twice in this engine (the 53 kB system prompt; the R423.1 shape
    directive), so this states two counts, one skeleton and nothing else. It
    never contradicts :func:`concise_block`: the sentence ceiling comes from the
    same :func:`concise_limits` call, and the citation budget keeps the rule that
    a provision the facts engage and the answer rules out still counts.
    """
    mode = conciseness_mode()
    if mode == "count":
        return count_only_block(question)
    if mode == "off":
        return ""
    try:
        need = (
            estimated_need
            if estimated_need is not None
            else answer_need(question, references)
        )
        words, sentences = concise_limits(need, question)
        budget = calibration_citation_budget(question)
    except Exception:  # noqa: BLE001 - a prompt add-on must never break Stage-2
        return ""
    lead = "the verdict" if need.is_yes_no else "the direct answer"
    shape = [
        f"* Draft, then COUNT its sentences: keep {sentences} at most. Delete the "
        "sentence that decides least, not the last one you wrote.",
        _COUNT_CLAUSE.format(budget=budget),
        f"* Match this shape ({sentences} sentences, about {words} words, then the "
        "references):",
        f"    1. {lead}, naming the provision it rests on.",
        "    2. the limb of that provision the facts engage.",
        "    3. the condition, exception or branch that decides the answer.",
        f"    {_REFERENCES_CLAUSE.format(budget=budget)}",
    ]
    return "\n".join(["LENGTH AND CITATION COUNTS (count both before you answer):", *shape])


def count_only_block(question: str = "") -> str:
    """The CITATION-COUNT-only block, or ``""`` when the knob is OFF.

    R461. The half of the R460 calibration block that survived TWO transports: a
    numeric budget on the provisions the answer may NAME, the rule that a
    provision the facts engage and the answer rules out still counts, and the
    citation-order line - and nothing else.

    It deliberately calls NEITHER :func:`answer_need` NOR :func:`concise_limits`,
    so the length battery cannot leak back in and a broken length estimate cannot
    take the citation budget down with it. Same fail-soft rule as the full block:
    a prompt add-on must never break Stage-2.
    """
    if not count_only_enabled():
        return ""
    try:
        budget = calibration_citation_budget(question)
    except Exception:  # noqa: BLE001 - a prompt add-on must never break Stage-2
        return ""
    return "\n".join([
        "CITATION COUNT (count the provisions before you answer):",
        _COUNT_CLAUSE.format(budget=budget),
        f"* {_REFERENCES_CLAUSE.format(budget=budget)}",
    ])


def need_proportional_block(
    question: str,
    references: str = "",
    *,
    estimated_need: AnswerNeed | None = None,
) -> str:
    """The clause for this question, or ``""`` when the lever is OFF / disabled."""
    if not need_proportional_contract_enabled():
        return ""
    need = (
        estimated_need
        if estimated_need is not None
        else answer_need(question, references)
    )
    return shape_directive(need)
