"""Implicit cross-reference graph extracted from KB obligation summaries.

Many obligation rows in :data:`app.data.kb.EC_CHECKER_OBLIGATION_MAP`
already name other articles in their prose:

    Art. 16: "Provider obligations for high-risk AI: ensure system meets
    Section-2 requirements, … operate a quality-management system
    (Art. 17), keep documentation (Arts. 11 + 18), keep logs (Art. 19),
    undertake conformity assessment (Art. 43), draw up declaration of
    conformity (Art. 47), affix CE marking (Art. 48), register in EU
    database (Art. 49), take corrective actions (Art. 20), and
    demonstrate compliance to authorities (Art. 21)."

That's ~10 cross-references in one summary that the retrieval layer
never surfaces. When a user asks "what does Art. 16 require?", the
system answers with Art. 16's summary — but doesn't pull the linked
obligations (Art. 11, Art. 17, Art. 18, …) into the citation set,
even though they're exactly the obligations the deployer needs to
know about.

This module regex-extracts those mentions once at import time, building
a deterministic adjacency map. The engine consults the map when
expanding the citation set for any matched entity, adding 1-degree
cross-refs with reduced weight so they appear in the references list
but don't dominate the answer text.

## Cost

* Build: one regex pass over ~110 summary strings — sub-5ms at import.
* Query: O(1) dict lookup per entity.
* Latency overhead: negligible, well within the 5.45ms p95 budget.

## What this is NOT

This is NOT a real ontological graph (no typed edges, no semantic
relationship labels). Every cross-reference is just "mentioned by" —
the route layer interprets the relationship from context. For typed
relationships (Practice → Article, ActorRole → obligations), see
:mod:`app.data.ontology`.
"""
from __future__ import annotations

import re
from functools import lru_cache

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.kb import EC_CHECKER_OBLIGATION_MAP

# Article and annex citation patterns. Matches the short ``Art.`` form
# (and the no-period ``Art`` form when followed by digits), and the
# Roman-numeral Annex form. Sub-paragraph chains like ``(1)(a)`` are
# stripped — we record the bare article number / annex roman as the
# cross-reference target.
_ART_RE = re.compile(r"\bArt\.?\s*(\d{1,3})\b", re.IGNORECASE)
_ANNEX_RE = re.compile(r"\bAnnex\s+([IVXLC]+)\b", re.IGNORECASE)


# ── Manually-curated cross-reference edges ─────────────────────────────
#
# The regex extractor above only catches Art./Annex mentions that appear
# verbatim in a summary string. Two important classes of edge get missed:
#
# 1. Annex ↔ Article edges where the Annex doesn't appear in any
#    obligation summary (e.g. Annex IV doesn't have its own row in
#    EC_CHECKER_OBLIGATION_MAP, so the regex never sees its source side).
# 2. Reverse edges that the author of the summary didn't write
#    explicitly. The regex graph is directed; we need both directions
#    to answer "what references Annex IV?".
#
# Each tuple is ``(source, target, reason)``. The ``reason`` is surfaced
# by :func:`cross_refs_with_reason` so answer composition can cite the
# semantic relationship rather than just both refs side by side.
#
# Endpoints are validated at import time by ``MANUAL_XREFS_LINTED``
# below — a typo here fails the module load, not the user query.
MANUAL_XREFS: tuple[tuple[str, str, str], ...] = (
    (
        "Annex IV",
        "Art. 11",
        "Annex IV enumerates the contents of the technical documentation "
        "required by Art. 11",
    ),
    (
        "Art. 11",
        "Annex IV",
        "Reverse: Art. 11 documentation contents are specified in Annex IV",
    ),
    (
        "Annex V",
        "Art. 47",
        "Annex V specifies the contents of the EU declaration of conformity "
        "required by Art. 47",
    ),
    ("Art. 47", "Annex V", "Reverse"),
    (
        "Annex VI",
        "Art. 43",
        "Annex VI is the conformity assessment procedure based on internal "
        "control referenced in Art. 43",
    ),
    (
        "Annex VII",
        "Art. 43",
        "Annex VII is the conformity assessment based on QMS + technical doc "
        "assessment referenced in Art. 43",
    ),
    ("Art. 43", "Annex VI", "Reverse"),
    ("Art. 43", "Annex VII", "Reverse"),
    (
        "Annex III",
        "Art. 6",
        "Annex III enumerates the high-risk use cases referenced in Art. 6(2)",
    ),
    ("Art. 6", "Annex III", "Reverse"),
    (
        "Annex I",
        "Art. 6",
        "Annex I lists Union harmonisation legislation whose safety "
        "components are high-risk under Art. 6(1)",
    ),
    ("Art. 6", "Annex I", "Reverse"),
    (
        "Annex II",
        "Art. 5",
        "Annex II is the list of offences relevant to the Art. 5(1)(h) RBI "
        "law-enforcement carve-out",
    ),
    ("Art. 5", "Annex II", "Reverse"),
    (
        "Annex XI",
        "Art. 53",
        "Annex XI is the technical documentation for GPAI providers required "
        "by Art. 53(1)(a)",
    ),
    (
        "Annex XII",
        "Art. 53",
        "Annex XII is the information required for downstream providers "
        "under Art. 53(1)(b)",
    ),
    (
        "Annex XIII",
        "Art. 51",
        "Annex XIII is the criteria for designating GPAI models with systemic "
        "risk under Art. 51",
    ),
    ("Art. 53", "Annex XI", "Reverse"),
    ("Art. 53", "Annex XII", "Reverse"),
    ("Art. 51", "Annex XIII", "Reverse"),
    # ── R57-C — Operator-obligation interconnects (graph audit P0) ───────
    #
    # The R57 graph audit (docs/reviews/R57-GRAPH-RETRIEVAL-AUDIT.md)
    # found 8 of 11 V2-weak-axis articles had zero outgoing edges in the
    # CORE graph that the route reads for 1-hop scenario expand + BM25
    # confidence boost. These 14 edges are the audit's P0 list — each
    # grounded in a specific EUR-Lex paragraph or sub-point, NOT
    # speculative. They land here (vs `_BACKFILL_XREFS`) so the route +
    # BM25 boost both pick them up, not just Neo4j 2-hop in production.
    # Clusters: role_ambiguity (5), gpai (5), conflict (4).
    #
    # role_ambiguity — hub-and-spoke between Art. 16/22/25/26
    (
        "Art. 16",
        "Art. 25",
        "R57-C — Art. 16 provider obligations transfer under Art. 25's "
        "value-chain rule (rebrand / substantial modification)",
    ),
    (
        "Art. 26",
        "Art. 16",
        "R57-C — Art. 26(1) deployer obligation depends on provider's Art. 16 "
        "chain — deployers execute against the provider's outputs",
    ),
    (
        "Art. 26",
        "Art. 25",
        "R57-C — Art. 26 deployer becomes new provider per Art. 25(1)(c) on "
        "substantial modification",
    ),
    (
        "Art. 22",
        "Art. 16",
        "R57-C — Art. 22(2) requires the authrep to verify Art. 16 provider "
        "obligations on behalf of the non-EU provider",
    ),
    (
        "Art. 22",
        "Art. 25",
        "R57-C — Art. 22 authrep sits inside the Art. 25 value-chain frame "
        "for non-EU providers",
    ),
    # gpai — Art. 51 / 53 / 55 / 56 / 101 enforcement chain
    (
        "Art. 53",
        "Art. 56",
        "R57-C — Art. 53(4) explicitly lets GPAI providers rely on Art. 56 "
        "codes of practice to demonstrate compliance",
    ),
    (
        "Art. 53",
        "Art. 101",
        "R57-C — Art. 101 fines enforce Chapter V (which includes Art. 53) — "
        "citing one without the other elides enforcement",
    ),
    (
        "Art. 51",
        "Art. 53",
        "R57-C — Art. 51 designation triggers the Art. 53 obligation chain",
    ),
    (
        "Art. 55",
        "Art. 53",
        "R57-C — Art. 55 systemic-risk obligations are additional to Art. 53 "
        "baseline — both apply",
    ),
    (
        "Art. 25",
        "Art. 53",
        "R57-C — Art. 25(4) one-third fine-tune rule routes downstream "
        "modifier into Art. 53 as new provider",
    ),
    # conflict — Art. 73 ↔ Art. 79 enforcement pipeline + Art. 6 ↔ Art. 5 risk pyramid
    (
        "Art. 73",
        "Art. 79",
        "R57-C — Art. 73(2) serious-incident reports trigger Art. 79 "
        "risk-procedure evaluation",
    ),
    (
        "Art. 79",
        "Art. 73",
        "R57-C — Reverse: Art. 79 procedure references the Art. 73 report "
        "as upstream signal",
    ),
    (
        "Art. 79",
        "Art. 26",
        "R57-C — Art. 79(1)(c) routes deployer-caused risk through Art. 26 "
        "obligations",
    ),
    (
        "Art. 6",
        "Art. 5",
        "R57-C — Risk-pyramid reconciliation: a system is either prohibited "
        "(Art. 5) or high-risk (Art. 6) — never both — edge surfaces the alternative",
    ),
    # ── R59 — Section-2 HRAIS obligation chain (CRITIC-2) ────────────────
    # Art. 6 classification triggers ALL of Section 2 (Arts. 9–18).
    # Adding Art. 6→9 core edge means 1-hop scenario expansion now surfaces
    # the risk-management-system article when Art. 6 is the initial hit.
    (
        "Art. 6",
        "Art. 9",
        "R59 — Art. 6 classification triggers Art. 9 risk-management-system obligation (Section 2 gateway)",
    ),
    (
        "Art. 9",
        "Art. 10",
        "R59 — Art. 9(1) requires risk management measures aligned with Art. 10 data governance",
    ),
    (
        "Art. 9",
        "Art. 13",
        "R59 — Art. 9 risk management outputs inform the Art. 13 transparency information chain",
    ),
    (
        "Art. 9",
        "Art. 14",
        "R59 — Art. 9(5) risk measures must include human-oversight mechanisms (Art. 14)",
    ),
    (
        "Art. 9",
        "Art. 15",
        "R59 — Art. 9(2)(b) requires robustness measures aligned with Art. 15 accuracy/robustness",
    ),
    (
        "Art. 10",
        "Art. 9",
        "R59 — Reverse: Art. 10 data-governance obligations feed into Art. 9 risk management",
    ),
)


# ── R47-A — prose-mined backfill (orphaned-article rescue) ─────────────
#
# The regex extractor in :func:`_build_regex_xref_graph` runs over the
# obligation summaries in ``EC_CHECKER_OBLIGATION_MAP`` — short hand-
# authored stubs. The full EUR-Lex prose in
# ``app.data.eu_ai_act_corpus.ARTICLE_FULL_TEXT`` carries far more
# cross-references that the summaries never repeated. Before this
# backfill, 32 of 113 articles had **zero** outgoing xref edges,
# blocking the 2-hop GraphRAG expander from firing on them.
#
# Each edge below was mined from ``ARTICLE_FULL_TEXT`` via
# ``scripts/analyze_xref_coverage.py`` and **manually filtered** to
# drop cross-Regulation noise (snippets like "Article 9 of Regulation
# (EU) 2016/679" are NOT internal AI Act references and would pollute
# the graph). Every edge below was verified as an *internal* AI Act
# citation in the prose — either explicitly tagged "of this Regulation"
# or unambiguous in context (e.g. neighbouring "deployers" /
# "Annex III" / "CE marking" / "sandbox" — all AI-Act-only terms).
#
# Endpoints are lint-validated by :func:`_lint_manual_xrefs` at import.
_BACKFILL_XREFS: tuple[tuple[str, str, str], ...] = (
    # Art. 2 (scope) — refers to Arts. 5, 6, 57, 112 and Annex I
    ("Art. 2", "Art. 5", "Art. 2(8) carves limited-risk + Art. 5 systems within scope"),
    ("Art. 2", "Art. 6", "Art. 2(2) narrows the regime for Annex-I products: only Art. 6(1) and selected articles apply"),
    ("Art. 2", "Art. 57", "Art. 2(2) lists Art. 57 (sandbox) among the applicable articles for Annex-I-Section-B products"),
    ("Art. 2", "Art. 112", "Art. 2(2) lists Art. 112 (review) among the applicable articles"),
    ("Art. 2", "Annex I", "Art. 2(2) gates scope on Union harmonisation legislation listed in Annex I"),
    # Art. 13 (transparency for high-risk) — totally orphaned before R47
    ("Art. 13", "Art. 9", "Art. 13(3)(b)(iii) cross-refers to the risk-management residual risks identified under Art. 9(2)"),
    ("Art. 13", "Art. 12", "Art. 13(3)(b)(vi) ties the logs documentation requirement to Art. 12"),
    ("Art. 13", "Art. 14", "Art. 13(3)(d) requires instructions for use to describe the Art. 14 human-oversight measures"),
    ("Art. 13", "Art. 15", "Art. 13(3)(b)(ii) requires reporting the accuracy/robustness/cybersecurity metrics defined in Art. 15"),
    # Art. 14 (human oversight) — orphaned before R47
    ("Art. 14", "Annex III", "Art. 14(5) applies a stricter oversight regime to Annex-III point-1(a) biometric identification systems"),
    # Art. 23 (importers) — orphaned before R47
    ("Art. 23", "Art. 11", "Art. 23(1)(b) requires importers to verify that the provider drew up Art. 11 technical documentation"),
    ("Art. 23", "Annex IV", "Art. 23(1)(b) requires importers to verify the Annex IV technical documentation"),
    ("Art. 23", "Art. 22", "Art. 23(1)(d) requires importers to verify the provider's Art. 22 authorised-representative appointment"),
    ("Art. 23", "Art. 43", "Art. 23(1)(a) requires importers to verify the Art. 43 conformity assessment was carried out"),
    ("Art. 23", "Art. 47", "Art. 23(1)(c) requires importers to verify the Art. 47 EU declaration of conformity"),
    ("Art. 23", "Art. 79", "Art. 23(2) triggers Art. 79(1) risk-notification when an importer detects non-compliance"),
    # Art. 24 (distributors) — orphaned before R47
    ("Art. 24", "Art. 16", "Art. 24(1) requires distributors to verify provider Art. 16 obligations (points b and c)"),
    ("Art. 24", "Art. 23", "Art. 24(1) requires distributors to verify importer Art. 23(3) obligations"),
    ("Art. 24", "Art. 47", "Art. 24(1) requires distributors to verify the Art. 47 EU declaration of conformity"),
    ("Art. 24", "Art. 79", "Art. 24(4) triggers Art. 79(1) risk-notification when a distributor detects non-compliance"),
    # Art. 26 (deployers) — orphaned and high-impact (V2 role_ambiguity blocker)
    ("Art. 26", "Art. 13", "Art. 26(1) requires deployers to use the Art. 13 information from the provider when complying"),
    ("Art. 26", "Art. 49", "Art. 26(8) requires public-authority deployers to discharge Art. 49 registration obligations"),
    ("Art. 26", "Art. 50", "Art. 26(11) preserves Art. 50 transparency obligations for deployers of Annex-III biometric systems"),
    ("Art. 26", "Art. 71", "Art. 26(8) prohibits use when the system is not registered in the Art. 71 EU database"),
    ("Art. 26", "Art. 72", "Art. 26(5) requires deployers to inform providers per Art. 72 post-market monitoring"),
    ("Art. 26", "Art. 73", "Art. 26(5) routes serious incidents via Art. 73 reporting if the provider is unreachable"),
    ("Art. 26", "Art. 79", "Art. 26(5) requires deployers to act under Art. 79(1) when their use creates a risk"),
    ("Art. 26", "Annex III", "Art. 26 obligations scale to Annex III high-risk use cases (e.g. Art. 26(11) biometric carve-out)"),
    # Art. 27 (FRIA) — connects to Art. 13 (also adds Art. 6 / Art. 46)
    ("Art. 27", "Art. 13", "Art. 27(1)(d) requires the FRIA to use the Art. 13 information provided by the provider"),
    ("Art. 27", "Art. 6", "Art. 27 applies to deployers of Annex-III high-risk systems identified per Art. 6(2)"),
    ("Art. 27", "Art. 46", "Art. 27(2) exempts FRIA in the Art. 46 derogated-conformity-assessment cases"),
    # Art. 31 (notified-body requirements) — connect to Art. 38 (notified bodies) and Art. 78
    ("Art. 31", "Art. 38", "Art. 31 ties notified-body requirements to Art. 38 cooperation activities"),
    ("Art. 31", "Art. 78", "Art. 31(7) imposes Art. 78 confidentiality on notified bodies"),
    # Art. 40 (harmonised standards) — orphaned
    ("Art. 40", "Annex I", "Art. 40 enables harmonised standards to cover Annex-I-Section-A products"),
    # Art. 41 (common specifications) — orphaned
    ("Art. 41", "Art. 67", "Art. 41 requires consulting the Art. 67 advisory forum before adopting common specifications"),
    ("Art. 41", "Art. 98", "Art. 41 routes adoption through the Art. 98(2) examination procedure"),
    # Art. 43 (conformity assessment) — already has Annex VI/VII; add internal links
    ("Art. 43", "Art. 40", "Art. 43 lets providers rely on Art. 40 harmonised standards to demonstrate Section-2 compliance"),
    ("Art. 43", "Art. 41", "Art. 43 lets providers rely on Art. 41 common specifications to demonstrate Section-2 compliance"),
    ("Art. 43", "Annex I", "Art. 43(3) routes Annex-I-Section-A products to product-legislation conformity procedures"),
    ("Art. 43", "Annex III", "Art. 43(1) routes Annex-III point-1 systems through QMS-based assessment"),
    ("Art. 43", "Annex IV", "Art. 43(4) ties substantial-modification scope to Annex IV point 2(f)"),
    # Art. 47 (EU declaration of conformity) — connect to Art. 97 (delegated-acts framework)
    ("Art. 47", "Art. 97", "Art. 47(5) empowers the Commission to amend Annex V via Art. 97 delegated acts"),
    # Art. 50 (transparency for limited-risk) — orphaned
    ("Art. 50", "Art. 56", "Art. 50(7) routes codes of practice through the Art. 56 procedure"),
    ("Art. 50", "Art. 98", "Art. 50(7) adopts implementing acts via the Art. 98(2) examination procedure"),
    # Art. 52 (GPAI systemic-risk classification) — orphaned
    ("Art. 52", "Art. 51", "Art. 52 procedures notify GPAI models that meet Art. 51(1)(a) systemic-risk thresholds"),
    ("Art. 52", "Annex XIII", "Art. 52 bases systemic-risk designation on the criteria set out in Annex XIII"),
    ("Art. 52", "Art. 97", "Art. 52(4) empowers Annex-XIII amendments via Art. 97 delegated acts"),
    # Art. 53 (GPAI provider obligations) — connect to Art. 56 + Art. 97
    ("Art. 53", "Art. 56", "Art. 53(4) lets GPAI providers rely on Art. 56 codes of practice for compliance"),
    ("Art. 53", "Art. 97", "Art. 53(5) empowers Annex-XI methodology amendments via Art. 97 delegated acts"),
    # Art. 54 (GPAI authorised representatives) — orphaned
    ("Art. 54", "Art. 53", "Art. 54(3) requires the AR to verify Art. 53 obligations have been fulfilled"),
    ("Art. 54", "Art. 55", "Art. 54(3) requires the AR to verify Art. 55 systemic-risk obligations where applicable"),
    ("Art. 54", "Annex XI", "Art. 54(3) requires the AR to keep a copy of the Annex XI technical documentation"),
    # Art. 55 (GPAI systemic-risk obligations) — orphaned
    ("Art. 55", "Art. 56", "Art. 55(2) lets systemic-risk GPAI providers rely on Art. 56 codes of practice"),
    ("Art. 55", "Art. 78", "Art. 55 information shared with the AI Office is protected by Art. 78 confidentiality"),
    # Art. 56 (codes of practice) — orphaned
    ("Art. 56", "Art. 53", "Art. 56 codes operationalise the Art. 53 GPAI-provider obligations"),
    ("Art. 56", "Art. 55", "Art. 56 codes operationalise the Art. 55 systemic-risk obligations"),
    ("Art. 56", "Art. 98", "Art. 56(6) approves codes via the Art. 98(2) examination procedure"),
    # Art. 57 (sandboxes) — orphaned
    ("Art. 57", "Art. 62", "Art. 57(9)(d) requires sandbox programmes to address Art. 62 SME measures"),
    ("Art. 57", "Art. 78", "Art. 57(8) protects sandbox findings under Art. 78 confidentiality"),
    # Art. 58 (sandbox implementing acts) — orphaned
    ("Art. 58", "Art. 95", "Art. 58(2)(e) covers the Art. 95 voluntary codes of conduct in sandboxes"),
    ("Art. 58", "Art. 98", "Art. 58 implementing acts follow the Art. 98(2) examination procedure"),
    # Art. 59 (sandbox data processing) — orphaned
    ("Art. 59", "Annex IV", "Art. 59(1)(i) ties sandbox documentation to the Annex IV record-keeping schema"),
    # Art. 60 (real-world testing) — refers to Art. 13
    ("Art. 60", "Art. 13", "Art. 60(4)(j) links real-world testing transparency to the Art. 13 provider information"),
    # Art. 62 (SME measures) — orphaned
    ("Art. 62", "Art. 43", "Art. 62(2) requires reduced Art. 43 conformity-assessment fees for SMEs"),
    # Art. 65 (Board) — orphaned
    ("Art. 65", "Art. 66", "Art. 65(2) constitutes the Board to deliver the Art. 66 tasks"),
    ("Art. 65", "Art. 67", "Art. 65(6) allows the Art. 67 advisory forum to attend sub-groups"),
    # Art. 66 (Board tasks) — orphaned
    ("Art. 66", "Art. 5", "Art. 66 includes advising on revisions of Art. 5 prohibited practices"),
    ("Art. 66", "Art. 7", "Art. 66 includes advising on Art. 7 Annex-III amendments"),
    ("Art. 66", "Art. 46", "Art. 66 covers the Art. 46 derogated-conformity-assessment procedures"),
    ("Art. 66", "Art. 71", "Art. 66 includes monitoring the Art. 71 EU database"),
    ("Art. 66", "Art. 73", "Art. 66 includes serious-incident reporting from Art. 73"),
    ("Art. 66", "Art. 112", "Art. 66 supports the Art. 112 Commission review cycle"),
    ("Art. 66", "Annex I", "Art. 66 collects expertise on Annex I product legislation"),
    ("Art. 66", "Annex III", "Art. 66 advises on Annex III high-risk-use-case amendments"),
    # Art. 69 (independent experts pool) — orphaned
    ("Art. 69", "Art. 68", "Art. 69 governs the Art. 68 scientific-panel composition"),
    ("Art. 69", "Art. 84", "Art. 69 supports the Art. 84 Union AI testing support structures"),
    # Art. 70 (national competent authorities) — orphaned
    ("Art. 70", "Art. 78", "Art. 70(5) binds national authorities to Art. 78 confidentiality"),
    # Art. 72 (post-market monitoring) — orphaned
    ("Art. 72", "Annex IV", "Art. 72(3) makes the post-market monitoring plan part of the Annex IV documentation"),
    ("Art. 72", "Annex I", "Art. 72(4) coordinates with Annex-I-Section-A monitoring obligations"),
    ("Art. 72", "Annex III", "Art. 72(5) carves Annex-III point-5 financial-institution systems"),
    ("Art. 72", "Art. 98", "Art. 72(3) adopts the monitoring template via the Art. 98(2) examination procedure"),
    # Art. 83 (non-compliance with CE / declaration / registration) — orphaned
    ("Art. 83", "Art. 47", "Art. 83(1)(c) addresses missing/incorrect Art. 47 EU declaration of conformity"),
    ("Art. 83", "Art. 48", "Art. 83(1)(a) addresses CE marking affixed in violation of Art. 48"),
    ("Art. 83", "Art. 71", "Art. 83(1)(e) addresses missing Art. 71 EU-database registration"),
    # Art. 101 (GPAI provider fines) — orphaned
    ("Art. 101", "Art. 56", "Art. 101(1) penalises commitments made under Art. 56 codes of practice"),
    ("Art. 101", "Art. 91", "Art. 101(1)(b) penalises non-compliance with Art. 91 information requests"),
    ("Art. 101", "Art. 92", "Art. 101(1)(d) penalises obstructing the Art. 92 evaluation procedure"),
    ("Art. 101", "Art. 93", "Art. 101(1)(c) penalises non-compliance with Art. 93 corrective measures"),
    ("Art. 101", "Art. 98", "Art. 101 decisions follow the Art. 98(2) examination procedure"),
    # Delegated-acts hub: every article that empowers delegated acts cross-refs Art. 97
    ("Art. 6", "Art. 97", "Art. 6(6)(7) empowers paragraph-3 amendments via Art. 97 delegated acts"),
    ("Art. 7", "Art. 97", "Art. 7(1) empowers Annex-III amendments via Art. 97 delegated acts"),
    ("Art. 11", "Art. 97", "Art. 11(3) empowers Annex-IV amendments via Art. 97 delegated acts"),
    ("Art. 43", "Art. 97", "Art. 43(5)(6) empowers Annex-VI/VII amendments via Art. 97 delegated acts"),
    ("Art. 51", "Art. 97", "Art. 51(3) empowers GPAI-threshold amendments via Art. 97 delegated acts"),
    # Reverse: Art. 97 -> the empowering articles (so a query about Art. 97 surfaces the delegated areas)
    ("Art. 97", "Art. 6", "Reverse — Art. 97 lists Art. 6 among empowered delegated-act domains"),
    ("Art. 97", "Art. 7", "Reverse — Art. 97 lists Art. 7 among empowered delegated-act domains"),
    ("Art. 97", "Art. 11", "Reverse — Art. 97 lists Art. 11 among empowered delegated-act domains"),
    ("Art. 97", "Art. 43", "Reverse — Art. 97 lists Art. 43 among empowered delegated-act domains"),
    ("Art. 97", "Art. 47", "Reverse — Art. 97 lists Art. 47 among empowered delegated-act domains"),
    ("Art. 97", "Art. 51", "Reverse — Art. 97 lists Art. 51 among empowered delegated-act domains"),
    ("Art. 97", "Art. 52", "Reverse — Art. 97 lists Art. 52 among empowered delegated-act domains"),
    ("Art. 97", "Art. 53", "Reverse — Art. 97 lists Art. 53 among empowered delegated-act domains"),
    # Implementing-act / fine reverse hubs (informational)
    ("Art. 91", "Art. 101", "Art. 91 enforcement requests are backed by Art. 101 fines"),
    ("Art. 92", "Art. 101", "Art. 92 evaluation access is backed by Art. 101 fines"),
    # Annex VIII (registration) reverse edge — exists; Annex VIII -> Art. 49 already covered by regex
    # Annex IV (technical documentation) — connect to Art. 13 / Art. 14 / Art. 72 (specified in body)
    ("Annex IV", "Art. 13", "Annex IV point 1(g) ties documentation contents to the Art. 13(3) instructions for use"),
    ("Annex IV", "Art. 14", "Annex IV point 2(e) ties documentation contents to the Art. 14 human-oversight measures"),
    ("Annex IV", "Art. 72", "Annex IV point 8 ties documentation contents to the Art. 72 post-market monitoring plan"),
    ("Annex VI", "Art. 72", "Annex VI assessment verifies the Art. 72 post-market monitoring system"),
)


def _lint_backfill_xrefs() -> tuple[tuple[str, str, str], ...]:
    """Validate every endpoint in :data:`_BACKFILL_XREFS` at import time.

    Mirror of :func:`_lint_manual_xrefs` for the R47 prose-mined edges.
    A typo in the curated list fails module load, not user queries.
    """
    for source, target, reason in _BACKFILL_XREFS:
        assert source in ARTICLE_EXISTENCE, (
            f"_BACKFILL_XREFS source {source!r} not in ARTICLE_EXISTENCE "
            f"(edge: {source!r} → {target!r})"
        )
        assert target in ARTICLE_EXISTENCE, (
            f"_BACKFILL_XREFS target {target!r} not in ARTICLE_EXISTENCE "
            f"(edge: {source!r} → {target!r})"
        )
        assert source != target, (
            f"_BACKFILL_XREFS self-edge {source!r} → {target!r}"
        )
        assert reason, (
            f"_BACKFILL_XREFS edge {source!r} → {target!r} has empty reason"
        )
    return _BACKFILL_XREFS


#: The lint-validated R47 backfill — `(source, target, reason)`.
BACKFILL_XREFS_LINTED: tuple[tuple[str, str, str], ...] = _lint_backfill_xrefs()


def _lint_manual_xrefs() -> tuple[tuple[str, str, str], ...]:
    """Validate every endpoint in :data:`MANUAL_XREFS` at import time.

    A bad edge (typo in ``Art. 5OO`` or ``Annex XIV``) raises an
    ``AssertionError`` here rather than silently propagating into a
    user-facing citation set. This is the same fail-fast posture as the
    consistency lint in ``tests/test_kb_consistency.py``, run a layer
    earlier so the module simply will not load on a bad edit.

    Returns the (immutable) validated edge list. Stored as
    :data:`MANUAL_XREFS_LINTED` so consumers can prove the lint ran.
    """
    for source, target, reason in MANUAL_XREFS:
        assert source in ARTICLE_EXISTENCE, (
            f"MANUAL_XREFS source {source!r} not in ARTICLE_EXISTENCE "
            f"(edge: {source!r} → {target!r})"
        )
        assert target in ARTICLE_EXISTENCE, (
            f"MANUAL_XREFS target {target!r} not in ARTICLE_EXISTENCE "
            f"(edge: {source!r} → {target!r})"
        )
        assert source != target, (
            f"MANUAL_XREFS self-edge {source!r} → {target!r}"
        )
        assert reason, (
            f"MANUAL_XREFS edge {source!r} → {target!r} has empty reason"
        )
    return MANUAL_XREFS


#: The lint-validated copy of :data:`MANUAL_XREFS`. Import-time evaluation
#: means a bad edge prevents the module from loading at all.
MANUAL_XREFS_LINTED: tuple[tuple[str, str, str], ...] = _lint_manual_xrefs()


@lru_cache(maxsize=1)
def _build_regex_xref_graph() -> dict[str, tuple[str, ...]]:
    """Build the regex-extracted cross-reference adjacency map.

    Walks every obligation summary, extracts Art. N / Annex X mentions,
    validates each against :data:`ARTICLE_EXISTENCE`, and stores the
    deduplicated cross-reference list keyed by the source article.

    Self-references are dropped: an obligation that mentions its own
    article in its summary doesn't need a self-edge in the graph.

    This is the legacy graph — the public :func:`_build_xref_graph` and
    :func:`cross_refs` overlay :data:`MANUAL_XREFS` on top of it.
    """
    graph: dict[str, list[str]] = {}

    for source_ref, entry in EC_CHECKER_OBLIGATION_MAP.items():
        summary = entry.get("summary", "")
        if not summary:
            continue

        targets: list[str] = []
        seen: set[str] = {source_ref}

        for match in _ART_RE.finditer(summary):
            num = match.group(1)
            target = f"Art. {num}"
            # Validate existence so we don't surface a hallucinated
            # cross-ref (e.g. a typo in the summary like Art. 200).
            if target in ARTICLE_EXISTENCE and target not in seen:
                seen.add(target)
                targets.append(target)

        for match in _ANNEX_RE.finditer(summary):
            roman = match.group(1).upper()
            target = f"Annex {roman}"
            if target in ARTICLE_EXISTENCE and target not in seen:
                seen.add(target)
                targets.append(target)

        if targets:
            graph[source_ref] = targets

    return {k: tuple(v) for k, v in graph.items()}


@lru_cache(maxsize=1)
def _build_xref_graph_core() -> dict[str, tuple[str, ...]]:
    """Build the regex + manual (NO R47-A backfill) cross-reference graph.

    Used by the BM25 confidence boost (:func:`kb_search._xref_in_degree`)
    so the boost's in-degree counts stay anchored to the curated edge set
    that R28 tuned against. R47-A's 108 prose-mined edges still flow
    through :func:`_build_xref_graph` for retrieval / 2-hop expand, but
    they are EXCLUDED here so adding orphan-rescue edges can't promote
    hub articles into a different boost tier and crowd out the gold
    article on single-anchor QA queries.
    """
    regex_graph = _build_regex_xref_graph()
    graph: dict[str, list[str]] = {k: list(v) for k, v in regex_graph.items()}

    for source, target, _reason in MANUAL_XREFS:
        if source == target:
            continue
        bucket = graph.setdefault(source, [])
        if target not in bucket:
            bucket.append(target)

    return {k: tuple(v) for k, v in graph.items()}


@lru_cache(maxsize=1)
def _build_xref_graph() -> dict[str, tuple[str, ...]]:
    """Build the merged regex + manual + R47 backfill cross-reference graph.

    Merge order (stable, deterministic):

    1. Regex-extracted edges from obligation summaries (legacy, round-1).
    2. :data:`MANUAL_XREFS` — annex ↔ article curated edges.
    3. :data:`_BACKFILL_XREFS` — R47-A prose-mined edges from the full
       EUR-Lex article texts, rescuing 30+ orphan articles.

    Each later pass only appends edges not already present. This keeps
    :func:`cross_refs` strictly additive against the legacy graph: any
    citation set previously surfaced still surfaces, plus the new edges
    appended at the tail.

    NOTE: For the BM25 confidence boost, use :func:`_build_xref_graph_core`
    instead — that graph excludes the R47-A backfill so the boost's
    in-degree tiers don't drift as orphan-rescue edges land.
    """
    core_graph = _build_xref_graph_core()
    graph: dict[str, list[str]] = {k: list(v) for k, v in core_graph.items()}

    for source, target, _reason in _BACKFILL_XREFS:
        if source == target:
            continue
        bucket = graph.setdefault(source, [])
        if target not in bucket:
            bucket.append(target)

    return {k: tuple(v) for k, v in graph.items()}


@lru_cache(maxsize=1)
def _build_xref_reason_index() -> dict[tuple[str, str], str]:
    """Index ``(source, target) → reason`` for curated edges.

    Regex-extracted edges have no semantic reason (the surface text just
    mentioned the target), so they fall back to a generic
    ``"mentioned by"`` label in :func:`cross_refs_with_reason`. Curated
    edges win on collision — if a manual or backfill edge restates a
    regex one with a richer reason, the curated reason is what gets
    surfaced. Backfill (R47) reasons override manual reasons if both
    exist for the same pair, since backfill reasons cite the prose-level
    sub-paragraph.
    """
    index: dict[tuple[str, str], str] = {
        (source, target): reason for source, target, reason in MANUAL_XREFS
    }
    for source, target, reason in _BACKFILL_XREFS:
        index[(source, target)] = reason
    return index


def cross_refs(article_ref: str, *, limit: int = 5) -> tuple[str, ...]:
    """Return up to ``limit`` cross-referenced articles for ``article_ref``.

    Uses the CORE graph (regex + manual edges, NO R47-A backfill) so the
    route's 1-hop scenario-expand path doesn't pull in orphan-rescue
    edges that over-cite single-anchor QA. R47-A's backfill is seeded
    into Neo4j by ``scripts/seed_neo4j_kb.py`` so the production-only
    :mod:`app.engines.graph_expand_2hop` 2-hop traversal still gets the
    full orphan-rescue benefit when ``NEO4J_URI`` is wired.

    Returns an empty tuple if ``article_ref`` has no recorded
    cross-references OR isn't in :data:`EC_CHECKER_OBLIGATION_MAP`.

    ``limit`` caps the surfaced set so a hub article (like Art. 16 with
    ~10 cross-refs) doesn't dominate the citation list. Default 5 keeps
    the cap consistent with the route's ``MAX_REFERENCES``.
    """
    graph = _build_xref_graph_core()
    return graph.get(article_ref, ())[:limit]


def cross_refs_with_reason(
    article_ref: str, *, limit: int = 5
) -> tuple[tuple[str, str], ...]:
    """Return up to ``limit`` ``(target, reason)`` pairs for ``article_ref``.

    Uses the FULL graph (regex + manual + R47-A backfill) so the
    semantic reasons curated for backfill edges (e.g. "Art. 26 → Art. 13
    deployer reads provider's transparency schema") are surfaced.
    Forensic / audit / human-readable consumers want the rich reasons.
    Route's 1-hop scenario-expand uses :func:`cross_refs` (CORE graph)
    to keep single-anchor QA precision.

    Regex-extracted edges (where there is no curated reason) fall back
    to a generic ``"mentioned in obligation summary"`` label.
    """
    full_graph = _build_xref_graph()
    targets = full_graph.get(article_ref, ())[:limit]
    reasons = _build_xref_reason_index()
    out: list[tuple[str, str]] = []
    for target in targets:
        reason = reasons.get(
            (article_ref, target),
            "mentioned in obligation summary",
        )
        out.append((target, reason))
    return tuple(out)


def all_edges() -> tuple[tuple[str, str], ...]:
    """Return every (source, target) cross-reference edge.

    Useful for tests + debugging — lets a consistency check verify that
    every edge endpoint passes ``article_existence`` validation.
    """
    graph = _build_xref_graph()
    edges: list[tuple[str, str]] = []
    for source, targets in graph.items():
        for target in targets:
            edges.append((source, target))
    return tuple(edges)


__all__ = [
    "cross_refs",
    "cross_refs_with_reason",
    "all_edges",
    "MANUAL_XREFS",
    "MANUAL_XREFS_LINTED",
    "BACKFILL_XREFS_LINTED",
]
