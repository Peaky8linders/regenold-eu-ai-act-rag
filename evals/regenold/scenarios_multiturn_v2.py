"""V2 multi-turn eval scenarios — harder than scenarios_multiturn_extended.

Each scenario chains 3+ turns where holding context across turns is the
only way to land the correct citation. Probes coreference, refinement,
scope shifts, cross-framework anchoring, role flips, and Digital Omnibus
date carry-over.

Schema (dict, not Scenario dataclass — these feed a future scoring pass
that compares the engine's final-turn references + answer text against
``expected_final_refs`` + ``expected_final_keywords``):

    {
        "id": str,
        "turns": list[{"role": "user"|"assistant", "content": str}],
        "expected_final_refs": list[str],     # user-facing form, e.g. "Article 26"
        "expected_final_keywords": list[str], # substring markers in final answer
        "notes": str,
    }

Citations use the **user-facing** form (``Article N`` arabic / ``Annex N``
roman) to match what the wire emits. The validation helper in __main__
maps these to ``Art. N`` / ``Annex N`` for ARTICLE_EXISTENCE lookup.
"""
from __future__ import annotations


SCENARIOS: list[dict] = [
    # ─────────────────────────────────────────────────────────────────────
    # Multi-framework carry: AI Act + MDR / AI Act + GDPR / AI Act + NIS2
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "mt_v2_001",
        "turns": [
            {"role": "user", "content": "We are a hospital deploying an AI-based medical-imaging triage system from a CE-marked vendor."},
            {"role": "assistant", "content": "Understood — that system is regulated as a medical device under the MDR and, since it is safety-related AI listed in Annex I, is also high-risk under Article 6(1) of the AI Act."},
            {"role": "user", "content": "Which regulator do we register with under the AI Act side?"},
        ],
        "expected_final_refs": ["Article 49", "Article 26", "Article 70"],
        "expected_final_keywords": ["EU database", "deployer", "competent"],
        "notes": "Cross-framework coref: turn 1 fixes 'hospital' = deployer of high-risk medical-device AI. Turn 3 'we' must resolve to deployer, AI Act registration is Art. 49 (EU database), not MDR side.",
    },
    {
        "id": "mt_v2_002",
        "turns": [
            {"role": "user", "content": "Our bank's anti-money-laundering AI uses customer transaction histories — partly third-country data."},
            {"role": "assistant", "content": "Credit-institution AML AI falls under Annex III(5)(b) high-risk if it influences access to essential services."},
            {"role": "user", "content": "Does our DPO's existing GDPR Art. 35 DPIA cover the AI Act obligations too, or do we still need the FRIA?"},
        ],
        "expected_final_refs": ["Article 27", "Annex III"],
        "expected_final_keywords": ["FRIA", "fundamental rights", "in addition"],
        "notes": "Multi-framework: user attempts to substitute GDPR DPIA for AI Act FRIA. Engine must hold 'we are a deployer of Annex III high-risk' from turn 1 and route to Art. 27 FRIA — DPIA does not replace it.",
    },
    {
        "id": "mt_v2_003",
        "turns": [
            {"role": "user", "content": "We provide an AI-driven SOC platform that detects cyber-attacks on critical infrastructure."},
            {"role": "assistant", "content": "Critical-infrastructure AI safety components are high-risk under Annex III(2)."},
            {"role": "user", "content": "How does that interact with our NIS2 incident-reporting timeline?"},
            {"role": "assistant", "content": "NIS2 governs the cyber incident itself; AI Act adds AI-specific serious incident reporting."},
            {"role": "user", "content": "What's the AI Act window then?"},
        ],
        "expected_final_refs": ["Article 73"],
        "expected_final_keywords": ["serious incident", "15 days", "market surveillance"],
        "notes": "Turn 5 'window' resolves to Art. 73 AI-Act incident reporting after multi-framework establishing context. Tricky because NIS2 has its own timelines that could pollute the answer.",
    },
    # ─────────────────────────────────────────────────────────────────────
    # Role flips (provider → deployer → provider via Art. 25)
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "mt_v2_004",
        "turns": [
            {"role": "user", "content": "We bought a CV-screening AI from Vendor X and use it for shortlisting our hires."},
            {"role": "assistant", "content": "You are a deployer of an Annex III(4) high-risk AI; Vendor X is the provider."},
            {"role": "user", "content": "We fine-tuned it on our 5-year hiring history dataset to match our culture."},
            {"role": "assistant", "content": "Fine-tuning that changes intended purpose can flip the deployer into a provider under Article 25."},
            {"role": "user", "content": "What new obligations does that flip impose on us?"},
        ],
        "expected_final_refs": ["Article 25", "Article 16"],
        "expected_final_keywords": ["provider", "obligations", "substantial modification"],
        "notes": "Role flip across 5 turns. Final answer must enumerate provider obligations under Art. 16, triggered by Art. 25 substantial-modification path. Engine must remember the fine-tune fact from turn 3.",
    },
    {
        "id": "mt_v2_005",
        "turns": [
            {"role": "user", "content": "We're an enterprise running our own GPT-style model internally for HR — never released externally."},
            {"role": "assistant", "content": "Internal-only deployment still falls under the AI Act when used for an Annex III purpose like HR."},
            {"role": "user", "content": "But we built it, so are we provider or deployer? We're both."},
        ],
        "expected_final_refs": ["Article 3", "Article 16", "Article 26"],
        "expected_final_keywords": ["both", "provider", "deployer"],
        "notes": "Ambiguous role: user is provider AND deployer simultaneously. Engine must address both stacks of obligations without picking one and dropping the other.",
    },
    {
        "id": "mt_v2_006",
        "turns": [
            {"role": "user", "content": "We import a high-risk biometric ID system from a US vendor."},
            {"role": "assistant", "content": "You're an importer under Article 23."},
            {"role": "user", "content": "Now we're rebranding it under our own name before selling it on."},
        ],
        "expected_final_refs": ["Article 25", "Article 16"],
        "expected_final_keywords": ["provider", "name", "trademark"],
        "notes": "Importer → provider flip under Art. 25(1)(a) (putting one's name/trademark on a high-risk system). Engine must catch the role transition implicit in 'rebranding'.",
    },
    # ─────────────────────────────────────────────────────────────────────
    # GPAI thresholds + Digital Omnibus (10²³ FLOPs, 1/3 fine-tune rule)
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "mt_v2_007",
        "turns": [
            {"role": "user", "content": "We're pre-training a foundation model at around 5×10²³ FLOPs."},
            {"role": "assistant", "content": "Above the 10²³ FLOPs threshold from the July 2025 Commission Guidelines, you're a GPAI provider under Article 51."},
            {"role": "user", "content": "What if we keep training and hit 1×10²⁵?"},
        ],
        "expected_final_refs": ["Article 51", "Article 55"],
        "expected_final_keywords": ["systemic risk", "10²⁵", "notify"],
        "notes": "Digital Omnibus threshold ladder: 10²³ → standard GPAI (Art. 51), 10²⁵ → systemic-risk GPAI (Art. 55). Engine must hold the 'pre-training a GPAI' context from turn 1.",
    },
    {
        "id": "mt_v2_008",
        "turns": [
            {"role": "user", "content": "We took an open-weights model trained on 9×10²⁴ FLOPs and fine-tuned it on legal-domain data."},
            {"role": "assistant", "content": "Fine-tuning of a GPAI can flip you into a provider role if the additional compute exceeds one-third of base compute (Article 25 + Commission Guidelines)."},
            {"role": "user", "content": "Our fine-tune used 3.3×10²⁴ FLOPs — exactly the 1/3 threshold. Are we now a provider?"},
        ],
        "expected_final_refs": ["Article 25", "Article 51"],
        "expected_final_keywords": ["one-third", "modifier", "provider"],
        "notes": "Boundary case at the Digital Omnibus 1/3 fine-tune rule. Engine must explain the rule deterministically — at exactly 1/3, the modifier becomes provider.",
    },
    {
        "id": "mt_v2_009",
        "turns": [
            {"role": "user", "content": "Our GPAI is open-weights, released on HuggingFace under Apache 2.0."},
            {"role": "assistant", "content": "Article 53(2) carves out most documentation obligations for non-systemic open-weights GPAI."},
            {"role": "user", "content": "We also train it on 2×10²⁵ FLOPs."},
        ],
        "expected_final_refs": ["Article 55", "Article 53"],
        "expected_final_keywords": ["systemic", "carve-out", "does not apply"],
        "notes": "Open-weights carve-out is GONE when the systemic-risk threshold (10²⁵) is hit. Engine must update its prior answer with the contradicting fact from turn 3.",
    },
    # ─────────────────────────────────────────────────────────────────────
    # Scope shifts + refinements
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "mt_v2_010",
        "turns": [
            {"role": "user", "content": "What are the transparency obligations for high-risk AI?"},
            {"role": "assistant", "content": "Article 13 requires providers to design transparency mechanisms for deployers."},
            {"role": "user", "content": "And for chatbots that talk to consumers?"},
            {"role": "assistant", "content": "Article 50(1) requires AI-chatbot interactions with natural persons to be disclosed."},
            {"role": "user", "content": "Which one wins if my chatbot is also a high-risk medical-triage tool?"},
        ],
        "expected_final_refs": ["Article 13", "Article 50"],
        "expected_final_keywords": ["both", "cumulative", "apply"],
        "notes": "Cross-article conflict resolution. Both Art. 13 (high-risk provider transparency) and Art. 50 (chatbot user disclosure) apply cumulatively — engine must not pick one and drop the other.",
    },
    {
        "id": "mt_v2_011",
        "turns": [
            {"role": "user", "content": "We're a SaaS startup with 40 employees and €8M annual turnover."},
            {"role": "assistant", "content": "You qualify as an SME under Article 62."},
            {"role": "user", "content": "We just raised Series B and grew to 250 employees, €60M turnover."},
            {"role": "assistant", "content": "You're now a small mid-cap — the Digital Omnibus extended SME privileges to small mid-caps under Article 62."},
            {"role": "user", "content": "Does our priority sandbox access carry over?"},
        ],
        "expected_final_refs": ["Article 62", "Article 57"],
        "expected_final_keywords": ["small mid-cap", "sandbox", "priority"],
        "notes": "Digital Omnibus small_mid_cap modifier role + sandbox priority. Engine must hold the size transition fact from turn 3 and apply the post-Omnibus rule.",
    },
    {
        "id": "mt_v2_012",
        "turns": [
            {"role": "user", "content": "Is our emotion-recognition tool prohibited?"},
            {"role": "assistant", "content": "Emotion recognition is not categorically prohibited; Article 5(1)(f) only bans it in workplace and education contexts (with a medical/safety carve-out)."},
            {"role": "user", "content": "We sell it to call centres for monitoring agent stress levels."},
        ],
        "expected_final_refs": ["Article 5"],
        "expected_final_keywords": ["workplace", "prohibited", "call centre"],
        "notes": "Refinement reveals workplace deployment, flipping the verdict from 'not categorically prohibited' to 'prohibited under Art. 5(1)(f)'. Engine must update.",
    },
    # ─────────────────────────────────────────────────────────────────────
    # Borderline prohibitions with carve-outs (Recital 16 etc.)
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "mt_v2_013",
        "turns": [
            {"role": "user", "content": "We're building a biometric categorization tool for retail analytics — categorizing shoppers by age range."},
            {"role": "assistant", "content": "Age-based biometric categorization is allowed; Article 5(1)(g) only prohibits inferring race, political opinions, trade-union membership, religion, sex life, or sexual orientation."},
            {"role": "user", "content": "What if we add ethnicity inference for marketing personalisation?"},
        ],
        "expected_final_refs": ["Article 5"],
        "expected_final_keywords": ["prohibited", "race", "ethnicity"],
        "notes": "Borderline prohibition. Turn 1 is OK (age), turn 3 crosses into Art. 5(1)(g) prohibited territory. Engine must flip the verdict.",
    },
    {
        "id": "mt_v2_014",
        "turns": [
            {"role": "user", "content": "Real-time RBI in public spaces — we're a police force investigating a missing-child case."},
            {"role": "assistant", "content": "Article 5(1)(h)(i) carves out a missing-children exception to the real-time RBI prohibition, subject to safeguards."},
            {"role": "user", "content": "Do we still need judicial pre-authorization?"},
        ],
        "expected_final_refs": ["Article 5"],
        "expected_final_keywords": ["judicial", "authorization", "prior"],
        "notes": "Carve-out with conditions. The missing-children exception requires prior judicial/independent administrative authorization per Art. 5(2)–(3).",
    },
    {
        "id": "mt_v2_015",
        "turns": [
            {"role": "user", "content": "Our HR analytics scores employee performance using AI."},
            {"role": "assistant", "content": "Annex III(4)(b) makes performance-evaluation AI in employment high-risk."},
            {"role": "user", "content": "Now we use it to decide who to lay off in a restructuring."},
        ],
        "expected_final_refs": ["Annex III", "Article 5"],
        "expected_final_keywords": ["termination", "high-risk", "fundamental"],
        "notes": "Stays high-risk (Annex III(4)(b) covers termination decisions). Engine should NOT slip into 'prohibited' since this is not social scoring — but must keep high-risk classification firm.",
    },
    # ─────────────────────────────────────────────────────────────────────
    # Penalties + conformity assessment + sandbox interplay
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "mt_v2_016",
        "turns": [
            {"role": "user", "content": "We're testing a high-risk hiring AI in the Spanish regulatory sandbox."},
            {"role": "assistant", "content": "Article 57 permits high-risk AI testing in an approved sandbox under supervision."},
            {"role": "user", "content": "We want to deploy it to a real client during the sandbox phase."},
        ],
        "expected_final_refs": ["Article 60", "Article 57"],
        "expected_final_keywords": ["real-world", "testing", "conditions"],
        "notes": "Sandbox vs real-world testing distinction. Art. 60 governs real-world testing outside sandboxes; combining the two needs care. Engine must surface Art. 60 conditions.",
    },
    {
        "id": "mt_v2_017",
        "turns": [
            {"role": "user", "content": "We knowingly deployed an AI Act prohibited practice for 6 months in our HR product."},
            {"role": "assistant", "content": "That's an Article 5 violation; Article 99(3) caps fines at €35M or 7% of worldwide turnover."},
            {"role": "user", "content": "We're a 25-employee startup — does the €35M cap actually hit us?"},
        ],
        "expected_final_refs": ["Article 99"],
        "expected_final_keywords": ["proportionate", "SME", "lower"],
        "notes": "Art. 99(6) requires fines to be proportionate, with SME/start-up carve-out for proportionality. Engine must not just quote the €35M ceiling.",
    },
    {
        "id": "mt_v2_018",
        "turns": [
            {"role": "user", "content": "Our high-risk AI uses Annex IV technical documentation."},
            {"role": "assistant", "content": "Article 11 + Annex IV mandate the technical documentation contents for high-risk AI."},
            {"role": "user", "content": "Internal conformity assessment or third-party notified body?"},
            {"role": "assistant", "content": "Article 43 routes most high-risk AI to internal control (Annex VI); biometric systems under Annex III(1) need a notified body (Annex VII)."},
            {"role": "user", "content": "We're under Annex III(4) (employment). Which route?"},
        ],
        "expected_final_refs": ["Article 43", "Annex VI"],
        "expected_final_keywords": ["internal", "control", "Annex VI"],
        "notes": "Conformity-assessment routing question across 5 turns. Annex III(4) employment AI uses internal control (Annex VI), not notified-body (Annex VII).",
    },
    # ─────────────────────────────────────────────────────────────────────
    # Digital Omnibus applicability date carry-over
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "mt_v2_019",
        "turns": [
            {"role": "user", "content": "When do high-risk Annex III obligations apply?"},
            {"role": "assistant", "content": "Per the May 2026 Digital Omnibus political agreement, Annex III high-risk obligations apply from 2 December 2027."},
            {"role": "user", "content": "And for Annex I (medical devices etc.) embedded systems?"},
        ],
        "expected_final_refs": ["Article 113"],
        "expected_final_keywords": ["2 August 2028", "Annex I"],
        "notes": "Digital Omnibus deferred timeline. Annex I embedded path moves to 2 Aug 2028 (Art. 113 as amended).",
    },
    {
        "id": "mt_v2_020",
        "turns": [
            {"role": "user", "content": "Our prohibited-practice deadline was 2 Feb 2025, correct?"},
            {"role": "assistant", "content": "Yes — Article 5 prohibitions have applied since 2 February 2025."},
            {"role": "user", "content": "Did the Digital Omnibus push that back?"},
        ],
        "expected_final_refs": ["Article 5", "Article 113"],
        "expected_final_keywords": ["no", "applies", "still"],
        "notes": "Digital Omnibus did NOT defer Art. 5 prohibitions. Engine must reject the false-deferral premise.",
    },
    # ─────────────────────────────────────────────────────────────────────
    # Hard governance / GPAI Code of Practice / Board questions
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "mt_v2_021",
        "turns": [
            {"role": "user", "content": "We're a GPAI provider considering signing the Code of Practice."},
            {"role": "assistant", "content": "Article 56 establishes Codes of Practice for GPAI providers; adherence is voluntary but creates a presumption of conformity."},
            {"role": "user", "content": "If we don't sign, what's the alternative path to demonstrate compliance?"},
        ],
        "expected_final_refs": ["Article 56", "Article 55"],
        "expected_final_keywords": ["adequate means", "alternative", "demonstrate"],
        "notes": "Art. 55(2) lets non-signatories demonstrate compliance by 'other adequate means.' Engine must surface that alternative path rather than imply signing is mandatory.",
    },
    {
        "id": "mt_v2_022",
        "turns": [
            {"role": "user", "content": "The AI Office contacted us about our GPAI."},
            {"role": "assistant", "content": "The AI Office sits within the Commission and oversees GPAI providers under Article 88+."},
            {"role": "user", "content": "Can they fine us directly?"},
        ],
        "expected_final_refs": ["Article 101"],
        "expected_final_keywords": ["Commission", "fines", "GPAI"],
        "notes": "Art. 101 — fines for GPAI providers are imposed by the Commission, not Member State authorities. Distinct from Art. 99 fines route.",
    },
    {
        "id": "mt_v2_023",
        "turns": [
            {"role": "user", "content": "Our high-risk AI was placed on the market in March 2026 — before the Annex III deadline."},
            {"role": "assistant", "content": "Article 111 covers transitional provisions for systems already on the market."},
            {"role": "user", "content": "Do we have to retrofit conformity, or are we grandfathered?"},
        ],
        "expected_final_refs": ["Article 111"],
        "expected_final_keywords": ["substantial change", "transitional", "grandfather"],
        "notes": "Art. 111 grandfathering applies UNLESS the system undergoes substantial change after the applicability date. Engine must surface the carve-out condition.",
    },
    {
        "id": "mt_v2_024",
        "turns": [
            {"role": "user", "content": "We deploy a high-risk AI that makes loan denials."},
            {"role": "assistant", "content": "Loan denial is Annex III(5)(b) — high-risk."},
            {"role": "user", "content": "A customer wants to know why their loan was rejected by our AI."},
        ],
        "expected_final_refs": ["Article 86"],
        "expected_final_keywords": ["explanation", "individual", "right"],
        "notes": "Art. 86 right to explanation of individual decisions — newer obligation, often missed. Engine must surface this and not regress to Art. 13 (which is about provider→deployer transparency, not deployer→affected-person).",
    },
    {
        "id": "mt_v2_025",
        "turns": [
            {"role": "user", "content": "We are an EU subsidiary of a US AI company; our parent is the provider, we just distribute."},
            {"role": "assistant", "content": "As distributor in the Union, Article 24 obligations apply to you."},
            {"role": "user", "content": "If the US parent has no EU establishment, who plays the authorized-representative role?"},
        ],
        "expected_final_refs": ["Article 22", "Article 24"],
        "expected_final_keywords": ["authorised representative", "written mandate", "established"],
        "notes": "Art. 22 — non-EU providers MUST appoint an authorised representative established in the Union. Engine must surface Art. 22, not just Art. 24 distributor obligations.",
    },
]


if __name__ == "__main__":
    print(len(SCENARIOS))
