# R386 — the 27-test contract migration worklist

Deriving this list costs a full ~20-minute two-arm suite run, so it is captured
rather than left to be rediscovered.

Produced by running the suite with `REGENOLD_REF_GRAIN_DEEPEN=1` and subtracting
the 3 pre-existing baseline failures (`test_kb_consistency`,
`test_r63c_stub_selection`, and
`test_r365_citable_base_guard::test_default_wire_is_byte_identical_to_pre_r365`)
plus the 2 tests in `test_r386_ref_grain_deepen.py` that pin the default itself.

Every entry is a **grain-form assertion**: it compares full reference strings
where the HEAD is what the test means. None is a real violation — the deepener's
head-set invariance is proven four ways (by construction, n=129, n=99, live
23/23).

⚠ `AGENTS.md`: *"NEVER alter or suppress failing unit tests or drop test
assertions to force a pass."* Migrating a contract the code deliberately and
measurably changed is legitimate; weakening one to go green is not. Every
NEGATIVE assertion (`x not in refs`) must stay exactly as strict — a deepened
reference must not be allowed to satisfy an exclusion the test exists to enforce.

## The 27

1. `tests/test_general_classification_verdict.py::TestRouteEndToEnd::test_wire_answer_and_refs`
2. `tests/test_intent_pruning_integration.py::test_classifier_returning_none_is_no_op`
3. `tests/test_intent_pruning_integration.py::test_low_confidence_intent_is_no_op`
4. `tests/test_intent_pruning_integration.py::test_penalty_inquiry_narrows_to_art_99`
5. `tests/test_r112_route_fixes.py::TestAssistantAnchorInheritanceValidation::test_legitimate_assistant_cited_article_43_still_inherits`
6. `tests/test_r115_followups.py::TestR115CuratedRefsProtected::test_minimal_risk_contrast_refs_survive`
7. `tests/test_r115_followups.py::TestR115CuratedRefsProtected::test_minimal_risk_paraphrase_also_protected`
8. `tests/test_r115_followups.py::TestR115SectorsFilterRepair::test_paraphrase_which_use_cases`
9. `tests/test_r115_followups.py::TestR115SectorsFilterRepair::test_q04_ships_both_routes`
10. `tests/test_r115_followups.py::TestR115SubpointBudgetRescue::test_q11_default_wire_collapses_the_enumeration_dump`
11. `tests/test_r133_prose_subpoints.py::test_route_keeps_head_when_question_does_not_name_the_subpoint`
12. `tests/test_r133_prose_subpoints.py::test_route_ships_prose_subpoint_when_question_names_it`
13. `tests/test_r260_risk_framework_refs.py::test_risk_framework_ships_full_tier_set[Explain the risk tiers of the EU AI Act.]`
14. `tests/test_r260_risk_framework_refs.py::test_risk_framework_ships_full_tier_set[List the risk categories under the AI Act.]`
15. `tests/test_r268_board65_4.py::TestBoard65_4Wire::test_references_carry_article_65_4`
16. `tests/test_r274_curated_ref_protect.py::TestR274RetentionRefs::test_retention_refs_exact`
17. `tests/test_r365_citable_base_guard.py::TestRouteWireEffect::test_off_explicitly_is_byte_identical_to_pre_r365`
18. `tests/test_r365_citable_base_guard.py::TestRouteWireEffect::test_on_removes_the_ungrounded_reference_from_the_wire`
19. `tests/test_r365_recall_supplements.py::test_engine_half_is_not_output_neutral_it_is_head_neutral`
20. `tests/test_r365_recall_supplements.py::test_wire_guard_only_emits_declared_heads`
21. `tests/test_r365_recall_supplements.py::test_wire_guard_recovers_the_measured_heads`
22. `tests/test_r95_noise_suppress.py::test_route_chatbot_disclosure_surfaces_art50`
23. `tests/test_regenold_scope.py::TestR68MatrixDumpContainment::test_ce_marking_qa_contained_to_specific_article`
24. `tests/test_regenold_scope.py::TestR68MatrixDumpContainment::test_post_market_monitoring_qa_contained`
25. `tests/test_retrieval_upgrades.py::TestBM25FallbackWireContract::test_records_retention_question_finds_art_19`
26. `tests/test_retrieval_upgrades.py::TestRoleObligationWireContract::test_deployer_annex_iii_hr_gives_matrix_answer`
27. `tests/test_topic_filter.py::test_in_scope_question_unaffected`
