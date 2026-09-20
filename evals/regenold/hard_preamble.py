"""The PRE-FIXED synthetic 9-turn conversation the official hard modality feeds.

WHY THIS MODULE EXISTS
----------------------
The official challenge description defines the hard modality as::

    The hard case works by feeding, for each question, a pre-fixed synthetic
    9-turn conversation — so that the actual question being evaluated appears in
    the 10th turn.

``evals/regenold/run_official_batch._run_hard`` did NOT do that. It maintained a
*rolling* conversation of our own prior questions and answers, so:

* row 1 was asked with NO prior context and row 5 with four exchanges of it, so
  no two rows were asked under the same modality;
* because ``_history_turn_count`` is derived from the request, the leading rows
  read 0 and 1 and were dispatched the FULL Stage-2 system prompt while every
  later row got the 61-char persona (measured: ``docs/measurements/r423/
  graded_scope_probe.py``) — a per-row modality leak inside one arm;
* the context was our own prose rather than the fixed regulatory dialogue the
  grader uses, so the graded task was not the one being measured.

THE DEPTH IS MEASURED, NOT GUESSED
----------------------------------
The evaluator's own export for the graded 2026-07-07 run
(``REGENOLD_JULY_7_EVALUATOR_BATCH.md``) records ``history_turns_used`` per
request, and it is **constant at 18 for all 111 hard turn-1 rows** — a property a
rolling conversation cannot have (a rolling window grows across a session,
2, 4, 6 …). Turn 2 is constant at 20 = 18 + our answer + the pushback turn. So
the fixture is 18 prior messages for every question.

18 messages is 9 (user, assistant) exchanges, which is exactly the "9-turn
conversation" of the description with the target question landing on the 10th
turn. The two pieces of evidence agree, and the module keeps the depth in
:data:`HARD_PREAMBLE_EXCHANGES` so a future round at a different depth is one
edit rather than a rewrite.

RECONSTRUCTION CAVEAT (read before quoting a number from this fixture)
---------------------------------------------------------------------
We do NOT hold the evaluator's verbatim background dialogue — only its LENGTH
and its described PURPOSE ("background dialogue on related EU AI Act themes …
priming the semantic boundaries, operative articles, and definitions, e.g.
distinguishing providers from deployers, high-risk systems under Annex III, and
conformity assessment pathways", see
``docs/reports/EU-AI-Act-Q&A-Challenge-Report-Official-Format.md`` §254). So this
fixture is a **reconstruction of the shape and the purpose**, not a copy of the
grader's text. It is deterministic and byte-identical for every row and every
arm, which is what makes a board measured on it comparable; it is not evidence
about what the grader's dialogue said.

WHERE THE STATUTORY NUMBERS GO — a deliberate rule
--------------------------------------------------
Every explicit Article / Annex NUMBER lives in an **assistant** turn. That is not
cosmetic: ``app/routes/regenold._extract_conversation_anchors`` scans prior
**user** turns and prepends up to six article numbers to the live question, so
numbers sitting in a user turn would inject the same fixed article list into the
scope and retrieval of all 110 rows. That extractor is OUR machinery, not part of
the official instrument, and a global anchor constant would confound the very
delta this fixture exists to measure. The dialogue still primes the model with
the operative provisions — through the assistant turns, which land in the
flattened conversation block exactly as the grader's dialogue would — while the
route's anchor line stays empty, so the measured movement is attributable to the
conversation SHAPE. ``tests/test_r424_hard_preamble.py`` pins this by running the
real extractor over the fixture's user turns and asserting an empty anchor line.

For the same reason the user turns avoid the role words (``provider``,
``deployer``, …) and the risk-tier words (``high-risk``, ``prohibited``, …) that
:func:`_extract_conversation_anchors` keys on; they are phrased the way a
compliance lead actually speaks ("the customer who uses it", "the stricter
category"). Both word sets are asserted absent by that test, so the rule cannot
rot silently.

Usage::

    from evals.regenold.hard_preamble import (
        build_prefixed_messages,
        build_prefixed_pushback_messages,
        hard_preamble_mode,
    )

    mode = hard_preamble_mode()          # "fixed" (default) or "rolling"
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Final

#: The environment key that selects the hard-mode request shape. Read by the
#: HARNESS (it decides which messages are posted), not by the app — so it is
#: routed through the runner's existing ``--baseline-env`` / ``--branch-env``
#: arm plumbing, which is the same mechanism every other paired gate uses.
HARD_PREAMBLE_ENV: Final = "REGENOLD_HARD_PREAMBLE"

#: ``rolling`` — the pre-R424 behaviour: a rolling window of our own prior Q&A,
#: starting empty, trimmed to ``HARD_CONTEXT_EXCHANGES``. Every board on record
#: before R424 was measured this way, so it is kept as an explicit opt-in for
#: reproducing those boards.
#: ``fixed`` — the official shape and, since R424, the DEFAULT: the same
#: 9-exchange dialogue before EVERY row. The paired gate
#: (``docs/measurements/r424/hard_preamble_gate.py``, label ``r424-preamble``)
#: cleared all four pre-registered conditions on 28 comparable rows x 3
#: generations x 2 arms — ans_loose / ans_strict / tone all +0.00 pp, official
#: overall 78.44 -> 78.56 (+0.11 pp), gold heads dropped 1 vs 1 — so the request
#: shape stops being a function of a row's position in a run.
MODE_ROLLING: Final = "rolling"
MODE_FIXED: Final = "fixed"
MODES: Final = (MODE_ROLLING, MODE_FIXED)
#: The shape used when the arm declares none.
DEFAULT_MODE: Final = MODE_FIXED

#: Prior (user, assistant) exchanges in the fixture. See the depth derivation in
#: the module docstring: 18 prior messages, constant across all 111 graded
#: turn-1 rows, = 9 exchanges, with the target question on the 10th turn.
HARD_PREAMBLE_EXCHANGES: Final = 9
#: ``HARD_PREAMBLE_EXCHANGES * 2`` — the message count the route's
#: ``history_turn_count`` reads for a turn-1 ask.
HARD_PREAMBLE_MESSAGES: Final = HARD_PREAMBLE_EXCHANGES * 2

#: The dialogue itself: 9 ``(user, assistant)`` exchanges on the framework's
#: boundaries. Same for every question by construction — nothing here depends on
#: the row, the arm, or the run.
HARD_PREAMBLE: Final[tuple[tuple[str, str], ...]] = (
    (
        "Our company develops and sells AI software in the Union. Before we open a "
        "compliance workstream, can you give me the overall shape of the AI Act and "
        "how it is organised?",
        "It is a risk-based framework. Chapter I holds the general provisions, "
        "including the Article 3 definitions of the roles that carry duties — "
        "provider, deployer, importer, distributor, authorised representative and "
        "the product manufacturer. Chapter II lists the practices that are banned "
        "outright; Chapter III governs high-risk systems, with the duty set for the "
        "party that develops them in Section 2 and the duty set for the party using "
        "them in Section 3; Chapter IV carries the transparency duties for certain "
        "other systems; Chapter V regulates general-purpose AI models on their own "
        "footing; and Chapters VII and IX set up the AI Office, the national "
        "authorities and post-market surveillance.",
    ),
    (
        "We are the one that develops the software and puts it on the market under "
        "our own name. The customer is the one who actually uses it in their "
        "operations. Does that split change which duties attach?",
        "Yes — it is the first thing to pin down. The developing party is normally "
        "the provider: Article 3(3) covers anyone who develops a system and places "
        "it on the market or puts it into service under its own name or trademark. "
        "The using party is the deployer under Article 3(4) unless it also becomes "
        "a provider. The duties then follow the role, not the product: the core "
        "development-side duties sit in Article 16, the use-side duties in Article "
        "26. A deployer can become a provider — Article 25 — by putting its own "
        "name on the system or by substantially modifying it.",
    ),
    (
        "How do we work out which category each of our products falls into?",
        "By elimination, in order. First, Article 5: some practices are simply "
        "banned, whatever the sector. Second, Article 6: high-risk, either because "
        "the system is a safety component of a product covered by the Annex I "
        "harmonisation legislation, or because its use case appears in the Annex "
        "III list. Article 6(3) is a narrow escape hatch — a listed system that "
        "genuinely does not pose a significant risk can stay outside high-risk, but "
        "that assessment has to be documented and the system registered. Third, "
        "Article 50 transparency duties, which bite on things like direct "
        "interaction with people, synthetic content, deepfakes, and emotion "
        "recognition or biometric categorisation. What is left is the residual "
        "minimal-risk tier. General-purpose models are handled separately.",
    ),
    (
        "If a product does land in the stricter category, which duties actually "
        "fall on us as the developer?",
        "A long and interlocking set. Article 17 quality management system; Article "
        "9 risk management across the lifecycle; Article 10 data governance; "
        "Article 11 with Annex IV for the technical documentation; Article 12 "
        "logging; Article 13 instructions for use; Article 14 human oversight; "
        "Article 15 accuracy, robustness and cybersecurity. Then the market entry "
        "step: conformity assessment under Article 43, either by internal control "
        "in Annex VI or with a notified body in Annex VII, followed by the EU "
        "declaration of conformity (Article 47), CE marking (Article 48), and "
        "registration in the database under Article 49 with Article 71. After that "
        "comes post-market monitoring under Article 72 and serious-incident "
        "reporting under Article 73.",
    ),
    (
        "And when one of our customers simply uses a system we built, what is left "
        "for them to do?",
        "Article 26 is their core duty set: use the system in line with the "
        "instructions for use, keep the human oversight the provider designed, "
        "assign oversight to competent people, take the input-data seriously, keep "
        "the logs, and inform workers and their representatives where the system is "
        "used at work. They also have to cooperate with us and give us what we need "
        "for monitoring and incident reporting. Two further duties can attach "
        "depending on who they are: a fundamental-rights impact assessment under "
        "Article 27 for public bodies and for private parties providing public "
        "services or running creditworthiness and insurance-risk assessments, and "
        "the right to an explanation of individual decision-making in Article 86.",
    ),
    (
        "What obligations are not driven by that classification — the ones that "
        "apply more broadly?",
        "Several. Article 50 transparency duties apply regardless of tier: telling "
        "people they are interacting with an AI system, machine-readable marking of "
        "synthetic content, labelling deepfakes, and informing people subject to "
        "emotion recognition or biometric categorisation. Article 4 requires "
        "sufficient AI literacy in staff dealing with these systems. Registration "
        "in the Article 71 database, the Article 22 authorised-representative rule "
        "for third-country parties, and the general-purpose model chapter can each "
        "apply on top, independently of whether the system is high-risk.",
    ),
    (
        "You mentioned a separate regime for the underlying models. How does that "
        "one differ from the one for the software on top?",
        "Chapter V regulates the models themselves, separately from the software "
        "built on them. Article 53 puts four duties on every party that puts such a "
        "model on the market: technical documentation, information for downstream "
        "parties, a copyright policy, and a publicly available summary of the "
        "training content. Article 54 adds an authorised-representative duty for "
        "third-country parties, and Article 55 adds real weight for models with "
        "systemic risk — model evaluation, adversarial testing, incident reporting "
        "and cybersecurity. Article 56 lets codes of practice carry the detail. "
        "Building on such a model does not discharge our own duties for the system "
        "we place on the market.",
    ),
    (
        "And the timing — what applies when?",
        "Article 113 stages it. The Regulation entered into force on 1 August 2024. "
        "The Article 5 prohibitions and the Article 4 AI literacy duty applied from "
        "2 February 2025. The model chapter, the governance chapter and the penalty "
        "regime applied from 2 August 2025. The Chapter III high-risk duties, "
        "including the Annex III use cases, apply from 2 August 2026, and the Annex "
        "I embedded-product systems follow on 2 August 2027. Article 111 keeps "
        "systems already on the market before 2 August 2026 under the earlier regime "
        "where they are high-risk only under Article 6(1), until 2 August 2030.",
    ),
    (
        "Understood. Before my next question, is there anything about how those "
        "pieces interact that I should keep in mind?",
        "Three boundaries are worth holding. Classification is not static: a change "
        "of intended purpose, or a substantial modification, can move a system "
        "between categories or turn a distributor into a provider. The category "
        "decides which duties apply and who carries them, so it is worth "
        "re-checking rather than assuming. And the layers accumulate — the bans, "
        "the strict-category duties, the transparency duties and the model duties "
        "can all apply to the same product at once, each with its own actor and its "
        "own timing.",
    ),
)


def preamble_messages() -> list[dict[str, str]]:
    """The fixture as a request prefix: 18 messages, user first, alternating.

    A fresh list of fresh dicts on every call, so a caller that appends to the
    result cannot mutate the fixture for the next row or the other arm.
    """
    out: list[dict[str, str]] = []
    for user, assistant in HARD_PREAMBLE:
        out.append({"role": "user", "content": user})
        out.append({"role": "assistant", "content": assistant})
    return out


def preamble_digest() -> str:
    """Stable digest of the fixture's bytes — the request shape, in one string.

    Recorded per arm by the runner so the void guard can prove the two arms'
    request shapes actually differed (see ``gate_validity.lever_changes_request``)
    instead of inferring it from a flag's spelling.
    """
    blob = json.dumps(preamble_messages(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_prefixed_messages(question: str) -> list[dict[str, str]]:
    """Official hard turn 1: the fixed dialogue, then the question as turn 10."""
    return [*preamble_messages(), {"role": "user", "content": question}]


def build_prefixed_pushback_messages(
    question: str, first_answer: str, pushback: str
) -> list[dict[str, str]]:
    """Official hard turn 2: the same dialogue, our answer, the pushback.

    Byte-identical prefix to :func:`build_prefixed_messages` plus our own turn-1
    answer and the judge's verbatim pushback — so the two graded asks differ only
    in what the harness itself appended.
    """
    return [
        *preamble_messages(),
        {"role": "user", "content": question},
        {"role": "assistant", "content": first_answer},
        {"role": "user", "content": pushback},
    ]


def hard_preamble_mode(env: dict[str, str] | None = None) -> str:
    """Resolve the hard-mode request shape from the environment.

    An unrecognised value RAISES rather than falling back to the default. A
    typo'd flag that silently ran the old shape is the R422 failure mode — a run
    that measured something other than what its label says — and the harness has
    already paid for that mistake once.
    """
    raw = (env if env is not None else os.environ).get(HARD_PREAMBLE_ENV, "")
    value = str(raw or "").strip().lower()
    if not value:
        return DEFAULT_MODE
    if value not in MODES:
        raise ValueError(
            f"{HARD_PREAMBLE_ENV}={raw!r} is not one of {MODES}; "
            "refusing to guess which request shape to run"
        )
    return value
