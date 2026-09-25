"""The blueprint's synthesis contract must reach the actual Stage-2 dispatch."""
import pytest

from app.data import graph_rag_prompts as prompts
from app.engines import _graph_rag_impl as impl
from app.engines.prompt_budget import _shrink_user_for_groq


def test_default_on_and_cache_identity(monkeypatch):
    """R400 - flipped ON. It replaces the competing USER-channel stack that
    R380 measured as the root cause of the conciseness gap, and Ans.
    Conciseness carries the highest marginal geometric-mean leverage of the
    eight axes in hard mode (0.203 pp per pp)."""
    from app.routes.regenold import _engine_cache_key
    monkeypatch.delenv("REGENOLD_EVIDENCE_CONTRACT", raising=False)
    assert prompts.evidence_contract_enabled()
    before = _engine_cache_key("What must a deployer do?", None)
    monkeypatch.setenv("REGENOLD_EVIDENCE_CONTRACT", "0")
    assert not prompts.evidence_contract_enabled()
    assert _engine_cache_key("What must a deployer do?", None) != before


@pytest.mark.parametrize("unexpected", ["", "garbage", "enabled"])
def test_a_blank_or_unexpected_value_keeps_the_on_behaviour(monkeypatch, unexpected):
    """Deny-list semantics for a default-ON gate - the R379 P2-7 defect, where
    an allow-list default-ON gate silently reverted production while the cache
    key still recorded the variable, so an A/B compared V1 to V1."""
    monkeypatch.setenv("REGENOLD_EVIDENCE_CONTRACT", unexpected)
    assert prompts.evidence_contract_enabled()


@pytest.mark.parametrize("compact", ["0", "1"])
def test_real_dispatch_preserves_evidence_and_coordinate_map(monkeypatch, compact):
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    monkeypatch.setenv("REGENOLD_PROMPT_COMPACT", compact)
    monkeypatch.setenv("REGENOLD_COORD_MAP_PROMPT", "1")
    monkeypatch.setenv("REGENOLD_FUSION_STAGE2", "0")
    # R448 — this test pins the R399 evidence contract against the legacy stack.
    # The concise LENGTH LIMIT block is a separate lever with its own tests
    # (tests/test_r448_concise_contract.py), so it is held OFF here.
    monkeypatch.setenv("REGENOLD_CONCISE_CONTRACT", "0")
    evidence = (
        "VERBATIM PROVISION TEXT: [Article 13] REQUIRED MEMBERS: (a) provider; (b) purpose.\n"
        "KNOWLEDGE GRAPH (NON-CITABLE): Recital 47 interprets the rule."
    )
    monkeypatch.setattr(impl, "_build_context_references_block", lambda *a, **kw: evidence)
    captured = []
    monkeypatch.setattr(impl, "_openai_wrapper_complete_for_graph_rag", lambda **kw: captured.append(kw))
    question = "What must Article 13 instructions contain? I don't think this is correct."
    for flag in ("0", "1"):
        monkeypatch.setenv("REGENOLD_EVIDENCE_CONTRACT", flag)
        impl._claude_max_enhance_answer(
            question=question, kg_answer="HEURISTIC DRAFT SENTINEL",
            context=impl.GraphContext(question=question),
        )
    assert len(captured) == 2, "both arms must reach actual Stage-2 dispatch"
    baseline, changed = (row["user"] for row in captured)
    assert "ANSWER CONTRACT (evidence)" not in baseline
    assert evidence in changed, "do not trim statute members or graph context"
    assert "VALID COORDINATES" in changed
    assert "HEURISTIC DRAFT SENTINEL" not in changed
    assert "ANSWER CONTRACT (compact)" not in changed
    assert "bare challenge adds no new topic" in changed
    assert len(changed) < len(baseline)
    # R399 — TRIPWIRE for the wholesale-replacement trap, third instance.
    # The assignment above discards whatever the compact branch appended, and
    # the pushback clause is the only instruction telling the model to hold a
    # correct answer when the evaluator disputes it. Hard mode is half the
    # official score. MEASURED before the repair: 'CHALLENGE' present in the
    # dispatched bytes at compact=0 AND compact=1 with the contract OFF, and
    # ABSENT in both arms with it ON. The contract's own "bare challenge"
    # sentence asserted above is NOT the same instruction and does not
    # substitute for it.
    assert "CHALLENGE" in baseline, "fixture must be a real pushback turn"
    assert "CHALLENGE" in changed, "the contract dropped the R391 pushback clause"


def test_transport_budget_keeps_the_authority_and_conciseness_contract():
    user = prompts.build_evidence_answer_user("What is required?", "evidence " * 3000)
    shrunk = _shrink_user_for_groq(user, budget=4000)
    assert len(shrunk) <= 4000
    assert prompts.EVIDENCE_ANSWER_CONTRACT in shrunk
    assert "ORIGINAL QUESTION: What is required?" in shrunk


def test_missing_evidence_is_not_a_legal_verdict():
    """An unsettled point is reported as law, never as a remark about inputs.

    R438.1 — the contract's second sentence used to trigger on the model's OWN
    state ("if the evidence is insufficient"), which is the form the coverage
    clause forbids and which R435's row-level audit caught the answers using
    ("...have no supporting text in the evidence supplied"). The instruction to
    state the narrow unresolved condition is KEPT; only its trigger and its form
    move to the one shared rule, ``UNSETTLED_POINT_RULE``.
    """
    user = prompts.build_evidence_answer_user(
        "Does it apply?", "No matching evidence.",
        rewritten_question="Does Article 26 apply to this operator?",
    )
    assert "REWRITTEN / SEARCH QUESTION: Does Article 26" in user
    assert "State the narrow unresolved" in user
    assert "Recitals interpret rules" in user
    assert prompts.UNSETTLED_POINT_RULE in prompts.EVIDENCE_ANSWER_CONTRACT
    assert "if the evidence is insufficient" not in prompts.EVIDENCE_ANSWER_CONTRACT


def test_the_legal_version_is_pinned_to_the_adopted_act():
    """The benchmark grades the Act AS ADOPTED, excluding the Omnibus
    amendments, so a model importing a current-law date answers a different
    statute than the one being scored. The version must be stated, and the
    contract must not assert any enforcement date of its own."""
    import re

    user = prompts.build_evidence_answer_user("Does it apply?", "evidence")
    assert "LEGAL VERSION: Regulation (EU) 2024/1689 as adopted" in user
    assert "Do not silently import later amendments" in prompts.EVIDENCE_ANSWER_CONTRACT
    # No hardcoded ENFORCEMENT DATE anywhere in the contract: a date written
    # into the prompt is an assertion of law on every call, and R396 shipped
    # four false ones that way. The "2024" of "Regulation (EU) 2024/1689" is
    # the instrument's number, not a date, and is required.
    body = prompts.EVIDENCE_ANSWER_CONTRACT.replace("2024/1689", "")
    assert not re.search(r"\b20\d{2}\b", body), "no bare year"
    assert not re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b",
        body,
    ), "no month name"


@pytest.mark.parametrize(
    ("question", "required", "forbidden"),
    [
        (
            "Can we use the AI system outside its intended use and do we keep logs under Article 26?",
            "Article 26(1)",
            "ARTICLE 50 BRANCH",
        ),
        (
            "I am a distributor and was not told whether the system is high-risk; what about an importer?",
            "Article 23(4)",
            "ARTICLE 50 BRANCH",
        ),
        (
            "Is an AI system used by a supermarket high-risk under Annex III point 6?",
            "AUTHORITY-NEXUS BRANCH",
            "ARTICLE 50 BRANCH",
        ),
        (
            "Does Article 50(4) require disclosure for an artistic deepfake?",
            "ARTICLE 50 BRANCH",
            "Article 26(1)",
        ),
        (
            "Does biometric verification solely confirm that a person is who they claim to be?",
            "BIOMETRIC BRANCH",
            "ARTICLE 50 BRANCH",
        ),
        (
            "Is software that is a safety component of a medical device high-risk under Annex I?",
            "ANNEX I / SAFETY-COMPONENT BRANCH",
            "ARTICLE 50 BRANCH",
        ),
        (
            "We want to use biometric verification solely to confirm that a specific person is who they claim to be; is it prohibited or high-risk?",
            "BIOMETRIC BRANCH",
            "ANNEX I / SAFETY-COMPONENT BRANCH",
        ),
        (
            "Are AI systems intended for emotion recognition from biometric data always prohibited?",
            "BIOMETRIC BRANCH",
            "DEPLOYER BRANCH",
        ),
        (
            "Is an AI system used as a safety component in a medical device high-risk?",
            "ANNEX I / SAFETY-COMPONENT BRANCH",
            "ARTICLE 50 BRANCH",
        ),
    ],
)
def test_evidence_contract_adds_only_the_engaged_branch_guard(
    question, required, forbidden, monkeypatch
):
    """The judge's branch failures must reach the live user channel without
    reintroducing the old all-topics prompt stack."""
    monkeypatch.setenv("REGENOLD_GROUNDED_BRANCH_GUARDS", "1")
    message = prompts.build_evidence_answer_user(question, "Article 26.1 Article 50.4")
    assert required in message
    assert forbidden not in message


def test_branch_guard_is_grounded_and_concise():
    from app.data.graph_rag_prompts import _grounded_branch_guard

    guard = _grounded_branch_guard("Article 50(4) artistic deepfake")
    assert "display or enjoyment" in guard
    assert "law-enforcement" in guard
    assert "Article 50(5)" in guard
    assert len(guard) < 1100
    assert "knowledge graph" not in guard.lower()


def test_branch_guard_coverage_for_target_clusters():
    from app.data.graph_rag_prompts import _grounded_branch_guard

    questions = [
        "biometric verification solely to confirm that a specific person is who they claim to be",
        "emotion recognition in the workplace",
        "medical device safety component under Annex I",
        "treatment recommendation software and notified body assessment",
    ]
    guards = [_grounded_branch_guard(q) for q in questions]
    assert all(guards)
    assert any("BIOMETRIC BRANCH" in guard for guard in guards[:2])
    # R442 — the MEDICAL-DEVICE block duplicated this one (and fired on every
    # "annex i..." substring); it was merged into the Annex I block.
    assert all("ANNEX I / SAFETY-COMPONENT BRANCH" in guard for guard in guards[2:])
    assert not any("MEDICAL-DEVICE BRANCH" in guard for guard in guards)


def test_the_annex_one_guard_does_not_fire_on_other_annexes():
    """``"annex i" in question`` also matches Annex II, Annex III and Annex IV.

    A bare substring test would append the Annex I / safety-component branch to
    every Annex III classification question -- the coordinate-form defect the
    R438 taxonomy names one level down, where ``Annex I.a.11`` was flattened to
    ``Annex I.11``. The lookahead admits only the bare Roman numeral I.
    """
    from app.data.graph_rag_prompts import _grounded_branch_guard

    marker = "ANNEX I / SAFETY-COMPONENT BRANCH"
    for question in (
        "Is a system high-risk under Annex III point 6?",
        "Does Annex II apply to this system?",
        "What does Annex IV require?",
        "Is the system listed in Annex IX?",
        "The annex is silent on this, and the annex in question is long.",
    ):
        guard = _grounded_branch_guard(question)
        assert marker not in guard, question
        # R442 — the removed MEDICAL-DEVICE block fired on all four of these.
        assert "MEDICAL-DEVICE BRANCH" not in guard, question
    assert marker in _grounded_branch_guard(
        "A product listed in Annex I where an AI system is a safety component"
    )


def test_the_new_branches_state_the_statutory_routes():
    """The two added branches must carry the facts the judge remarks cluster on."""
    from app.data.graph_rag_prompts import _grounded_branch_guard

    biometric = _grounded_branch_guard("biometric verification question")
    assert "EXPRESSLY EXCLUDED" in biometric
    assert "Article 5(1)(h)" in biometric
    assert "Article 5(1)(g)" in biometric
    assert "Article 5(1)(f)" in biometric
    assert "Article 50(3)" in biometric

    annex_one = _grounded_branch_guard("a safety component of a medical device")
    assert "THIRD-PARTY" in annex_one
    assert "derogation from" in annex_one
    assert "PARAGRAPH 2" in annex_one


def test_evidence_contract_does_not_drop_existing_precision_clauses(monkeypatch):
    """The evidence-contract replacement must preserve the default-on clauses.

    Before this assertion, the engine appended reference minimality and
    sub-paragraph discipline to the old user message, then replaced that entire
    message with ``build_evidence_answer_user``. The flags were in the cache key
    but had no effect on the production path.
    """
    monkeypatch.delenv("REGENOLD_PROMPT_V2", raising=False)
    monkeypatch.setenv("REGENOLD_USER_REF_MINIMALITY", "1")
    monkeypatch.setenv("REGENOLD_SUBPARAGRAPH_ATTRIBUTION", "1")
    message = prompts.build_evidence_answer_user(
        "Does Article 50(4) require disclosure for a deepfake?",
        "Article 50.4\nArticle 50.5",
    )
    assert "REFERENCE MINIMALITY" in message
    assert "SUB-PARAGRAPH DISCIPLINE" in message
    assert "Article 50(4)" in message


def test_the_builder_takes_no_dead_parameters():
    """``query_profile`` was removed: its only caller passed
    ``locals().get("_profile", "")`` and ``_profile`` is assigned nowhere in
    ``_claude_max_enhance_answer``, so the line could never render live while a
    builder-level test kept passing. Pinned so it is not silently re-added."""
    import inspect

    params = set(inspect.signature(prompts.build_evidence_answer_user).parameters)
    assert params == {"question", "references", "rewritten_question", "system_description"}


# ─── R442 — the branch guard, re-audited by execution ─────────────────────────
_HARD_HISTORY = (
    "Conversation so far:\n"
    "user: Is biometric identification by the police in Annex III point 6?\n"
    "assistant: A deepfake needs Article 50 disclosure; Article 9 and Annex I "
    "and a medical device safety component and emotion recognition apply.\n\n"
    "Latest question:\n"
)


def test_branch_guard_reads_only_the_live_question():
    """R442 — hard mode handed the guard the flattened conversation, so the
    fixed preamble fired ALL eleven blocks on every R440 gate row."""
    from app.data.graph_rag_prompts import _grounded_branch_guard

    assert _grounded_branch_guard(_HARD_HISTORY + "What is Annex X about?") == ""
    guard = _grounded_branch_guard(_HARD_HISTORY + "Does Article 26 require logs?")
    blocks = [line.split(":")[0] for line in guard.strip().splitlines()[1:]]
    assert blocks == ["DEPLOYER BRANCH"], blocks


@pytest.mark.parametrize(
    ("question", "absent"),
    [
        ("Who may draw up codes of conduct under Article 95?", "ARTICLE 9 STRUCTURE"),
        ("Does Article 90 give the scientific panel a role?", "ARTICLE 9 STRUCTURE"),
        ("How is a life and health insurance policy priced?", "AUTHORITY-NEXUS BRANCH"),
        ("Is a supermarket loyalty app high-risk?", "AUTHORITY-NEXUS BRANCH"),
        ("What corrective action must the provider take under Article 20?", "ARTICLE 80 BRANCH"),
        ("Must a provider's system keep logs under Article 12?", "DEPLOYER BRANCH"),
    ],
)
def test_branch_guard_triggers_do_not_fire_on_neighbouring_provisions(question, absent):
    from app.data.graph_rag_prompts import _grounded_branch_guard

    assert absent not in _grounded_branch_guard(question), question


def test_branch_guard_positive_triggers_still_fire():
    from app.data.graph_rag_prompts import _grounded_branch_guard

    assert "ARTICLE 9 STRUCTURE" in _grounded_branch_guard("What does Article 9 require?")
    assert "ARTICLE 50 BRANCH" in _grounded_branch_guard("Must a deep-fake be labelled?")
    assert "AUTHORITY-NEXUS BRANCH" in _grounded_branch_guard("Is a police risk tool high-risk?")
    assert "ARTICLE 80 BRANCH" in _grounded_branch_guard("What happens under Article 80?")


def test_branch_guard_states_the_law_as_the_adopted_text_does():
    """R442 — every block checked against ``get_provision_text``."""
    from app.data.graph_rag_prompts import _grounded_branch_guard

    biometric = _grounded_branch_guard("biometric categorisation and emotion recognition")
    # One biometric block, not two blocks that disagreed about Art. 5(1)(g).
    assert biometric.count("BIOMETRIC BRANCH") == 1
    assert "closed-list prohibition for biometric categorisation by sensitive" not in biometric
    assert "sex life or sexual orientation is prohibited" in biometric

    art80 = _grounded_branch_guard("What does Article 80 require?")
    assert "without undue delay" in art80
    assert "may prescribe" in art80  # the period is optional, not mandatory

    deployer = _grounded_branch_guard("How long must logs be kept under Article 26?")
    assert "appropriate to the system's intended purpose" in deployer
    assert "at least six months" in deployer

    classification = _grounded_branch_guard("Is it high-risk under Annex III?")
    assert "one of the conditions in points (a) to (d)" in classification
    assert "Article 6(4)" in classification


def test_branch_guard_carries_no_gold_criterion_wording():
    """Two sentences echoed our reconstructed gold criteria, not the Act."""
    from app.data.graph_rag_prompts import _grounded_branch_guard

    everything = _grounded_branch_guard(
        "article 26 instructions for use deployer logs; police; annex iii point 6; "
        "biometric; annex i; article 9; article 80; article 50; importer"
    )
    assert "not excused merely because" not in everything
    assert "resemblance to investigation" not in everything
