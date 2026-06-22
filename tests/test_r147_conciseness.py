"""R147 — Stage-2 conciseness: run-on clause-density discipline.

The R146 live judge measured conciseness as the weakest axis (0.625, the
floor). The failure mode is no longer the R145 pseudo-headers (already
killed) but **run-on clause-density**: 8 of 9 conciseness fails were a
single dense comma/"and"-joined paragraph the LLM judge decomposes into
6-7 clauses ("single run-on sentence exceeds 4-sentence limit", "one
run-on paragraph parsed as ~6-7 clauses").

The robust lever is generation-side — the Stage-2 prompt. A deterministic
post-pass re-sentencer was analysed and REJECTED (the judge counts
clause/thought count, not punctuation; re-punctuating cannot reduce
thought-count without either dropping content — the R126/R140 trap — or
producing ungrammatical subjectless fragments that fail the tone axis;
it also conflicts with rule 12b's packed-list requirement). R147 ships
the prompt change only.

These tests pin the prompt text so a future edit that drops the
run-on discipline is loud, not silent. The change is Stage-2-prompt-only,
so the deterministic davidath bench (provider=cli, no Stage-2) is
byte-identical by construction — verified separately by the bench gate.
"""

from __future__ import annotations

from app.data import graph_rag_prompts as g


SYS = g.ANSWER_GENERATE_SYSTEM


class TestR147RunOnDiscipline:
    def test_length_discipline_caps_at_four_sentences(self) -> None:
        assert "AT MOST four sentences" in SYS
        # The rationale must explain the judge's clause-decomposition so a
        # future editor understands why brevity is enforced here.
        assert "decomposes a dense paragraph into one clause per distinct point" in SYS

    def test_length_discipline_groups_not_drops(self) -> None:
        # Brevity must be achieved by GROUPING, never by omission — the
        # R126/R140 trap guard.
        assert "GROUP related obligations into ONE sentence" in SYS
        assert "NEVER by dropping a required provision" in SYS

    def test_completeness_still_wins(self) -> None:
        # Rule 12b (closed-set completeness) + rule 7 (every sub-question)
        # must be explicitly preserved against the new brevity rule.
        assert "completeness of the asked-for closed set (rule 12b)" in SYS
        assert "every distinct sub-question (rule 7) still takes priority" in SYS

    def test_run_on_contrastive_example_present(self) -> None:
        assert "BAD (run-on clause-density" in SYS
        assert "GOOD (verdict-first, obligations grouped into one point" in SYS
        # The GOOD example demonstrates the grouped "Articles 9 to 15" pattern.
        assert "the full high-risk obligation set of Articles 9 to 15" in SYS

    def test_new_prompt_text_has_no_dash_separators(self) -> None:
        # Rule 15 / R108: the prompt must not MODEL em/en dashes to the
        # model. The R147 additions must be dash-free (the R108 finding:
        # the prompt modelling dashes made Sonnet copy them).
        for line in SYS.splitlines():
            if "AT MOST four sentences" in line or "run-on clause-density" in line:
                assert "—" not in line, "em-dash modelled in prompt"
                assert "–" not in line, "en-dash modelled in prompt"

    def test_good_example_is_four_sentences(self) -> None:
        # Extract the GOOD run-on example's answer and confirm it is <= 4
        # period-terminated sentences (it demonstrates the rule it teaches).
        marker = 'A: "High-risk. An emergency patient-triage system'
        idx = SYS.find(marker)
        assert idx != -1, "GOOD run-on example answer not found"
        # The answer runs to the next blank line / closing quote.
        tail = SYS[idx + len('A: "'):]
        answer = tail.split('"\n', 1)[0]
        # Count sentence-terminating periods (the answer has no abbreviations).
        sentence_count = answer.count(". ") + (1 if answer.rstrip().endswith(".") else 0)
        assert sentence_count <= 4, f"GOOD example has {sentence_count} sentences"


class TestR147NoResentencer:
    """The deterministic re-sentencer was deliberately NOT shipped.

    Pin that no such transform leaked into the answer normaliser — if a
    future round adds one it must be a conscious decision with its own
    live ab_judge gate, not an accidental import.
    """

    def test_no_resentence_transform_exported(self) -> None:
        from app.integrations.regenold import answer_normaliser as an

        exported = set(getattr(an, "__all__", []))
        assert "resentence_runons" not in exported
        assert not hasattr(an, "resentence_runons")
