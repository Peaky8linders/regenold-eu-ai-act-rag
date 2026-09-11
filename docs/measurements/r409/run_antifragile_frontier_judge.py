"""Antifragile AI Frontier Judge Runner.

Evaluates:
- Part I: 17 questions (Current Engine vs Original Live Answer vs Expert Critique)
- Part II: 11 valid questions/variants from the 18.08.2026 report

Runs against local engine in deterministic offline mode, calls OpenRouter
`anthropic/claude-sonnet-5` (temp=0.1) as judge, computes official metrics,
and saves full raw evaluation data for report generation.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path
REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Step 1: Read OPENROUTER_API_KEY from .env BEFORE setting skip dotenv
from dotenv import dotenv_values
_env_vals = dotenv_values(REPO / ".env")
OPENROUTER_KEY = _env_vals.get("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")

# Step 2: Set deterministic offline environment for local engine
os.environ["REGENOLD_SKIP_DOTENV"] = "1"
os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
os.environ["REGENOLD_QUERY_DENOISER"] = "0"
os.environ["REGENOLD_EXTERNAL_EMBEDDINGS"] = "0"
for _flag in (
    "REGENOLD_CLOSED_SET_COMPLETENESS_GUARD",
    "REGENOLD_EXCEPTION_LIMB_GUARD",
    "REGENOLD_VERDICT_LEAD_GUARD",
    "REGENOLD_PUSHBACK_KEEP_CONTRACT",
    "REGENOLD_GOVERNING_PROVISION_CLAUSE",
):
    os.environ[_flag] = "1"

from fastapi.testclient import TestClient
from app.main import app
from app.data.provision_text import get_provision_text
from evals.official.rubric import (
    normalise_ref,
    ref_head,
    reference_correctness_loose,
    reference_correctness_strict,
    reference_conciseness,
)

# Initialize test client
CLIENT = TestClient(app)

# OpenRouter configuration
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
JUDGE_MODEL = "anthropic/claude-sonnet-5"
TEMPERATURE = 0.1

EXTRA_PROVISIONS = {
    "Recital 27": (
        "Recital 27: In order to promote and ensure the development of trustworthy AI, "
        "the Union's approach should be grounded in the ethical principles for trustworthy AI "
        "presented in the High-Level Expert Group's 2019 Ethics guidelines for trustworthy AI. "
        "These non-binding ethical principles include: human agency and oversight; technical "
        "robustness and safety; privacy and data governance; transparency; diversity, "
        "non-discrimination and fairness; societal and environmental well-being; and accountability. "
        "These principles should be translated into concrete requirements for AI systems. "
        "However, this Regulation should apply without prejudice to the legally binding requirements "
        "of Union law."
    ),
    "Regulation (EU) 2017/745 Annex VIII Rule 11": (
        "MDR Annex VIII Rule 11: Software intended to provide information which is used to take "
        "decisions with diagnosis or therapeutic purposes is classified as class IIa, except if such "
        "decisions have an impact that may cause death or an irreversible deterioration of a person's "
        "state of health, in which case it is in class III; or a serious deterioration of a person's "
        "state of health or a surgical intervention, in which case it is classified as class IIb."
    ),
    "Regulation (EU) 2017/745 Article 52": (
        "MDR Article 52: Conformity assessment procedures. Prior to placing a device on the market, "
        "manufacturers shall undertake an assessment of the conformity of that device... For class IIa, "
        "class IIb and class III devices, a notified body shall be involved."
    ),
}


def get_verbatim_provisions(refs: list[str], budget: int = 10000) -> str:
    wanted: list[str] = []
    for r in refs or []:
        n = normalise_ref(r) or r
        if n not in wanted:
            wanted.append(n)
    chunks, used = [], 0
    for w in wanted:
        if w in EXTRA_PROVISIONS:
            t = EXTRA_PROVISIONS[w]
        else:
            t = get_provision_text(w)
            if not t:
                h = ref_head(w)
                if h and h != w:
                    t = get_provision_text(h)
        if not t:
            continue
        room = max(0, budget - used)
        if room < 200:
            break
        body = t if len(t) <= room else t[:room] + " [...]"
        chunks.append(f"--- {w} ---\n{body}")
        used += len(body)
    return "\n\n".join(chunks) if chunks else "(no verbatim text supplied)"


JUDGE_PROMPT_TEMPLATE = """You are the LLM-as-a-judge for an EU AI Act question-answering benchmark (Regulation (EU) 2024/1689).

You are given a QUESTION, a set of CORRECTNESS CRITERIA, and a CANDIDATE ANSWER. Make TWO INDEPENDENT judgements of that one answer and return both in a single JSON object.

JUDGEMENT 1 - ANSWER CORRECTNESS. For EACH criterion, decide whether the candidate answer satisfies it.

HOW TO JUDGE:
- A criterion is satisfied only when the candidate answer STATES THE SUBSTANCE of it. Naming or citing the provision that contains the fact is NOT enough.
- The answer may use different words. Judge meaning, not phrasing.
- A criterion that is a bare verdict ("Yes" / "No") is satisfied only when the answer's actual position matches it. An answer that leads with the opposite verdict and later concedes the point does NOT satisfy it - the verdict must be the answer's unambiguous position.
- Extra correct material in the answer neither satisfies nor breaks a criterion. Judge each criterion on its own.
- An answer that declines to answer, or says the material available does not permit an answer, satisfies NOTHING.
- Do not reward an answer for being long. Do not punish it for being short.

JUDGEMENT 2 - REGULATORY TONE. Judge whether the response is BOTH appropriate AND clear for a professional regulatory-advice setting.
APPROPRIATE means: professional and measured; does not lecture, moralise, or editorialise; does not address the reader informally; does not talk about itself, its retrieval, its knowledge base, its "supplied materials", or its own limitations; does not hedge into uselessness.
CLEAR means: readable, well-ordered prose that a compliance professional could act on; not a wall of fragments; not internally contradictory.
Correctness is NOT a tone concern. A wrong answer in impeccable regulatory prose passes judgement 2.

VERBATIM STATUTORY TEXT:
{provisions}

QUESTION:
{question}

CRITERIA:
{criteria}

CANDIDATE ANSWER:
{answer}

Return ONLY this JSON object, no markdown fence, no prose. "verdicts" has one entry per criterion, in order:
{{"verdicts": [{{"n": 1, "satisfied": true, "why": "one short sentence"}}], "tone": {{"appropriate": true, "clear": true, "why": "one short sentence"}}}}"""


def query_engine(question: str) -> dict[str, Any]:
    """Query local engine via deterministic offline TestClient."""
    t0 = time.time()
    resp = CLIENT.post(
        "/api/v1/regenold/eu-ai-act/ask",
        json=[{"role": "user", "content": question}],
    )
    dt = time.time() - t0
    if resp.status_code != 200:
        return {"answer": "", "references": [], "latency_s": dt, "error": resp.text}
    data = resp.json()
    return {
        "answer": data.get("answer", ""),
        "references": data.get("references", []),
        "reasoning": data.get("reasoning", ""),
        "latency_s": round(dt, 3),
    }


def call_judge(
    question: str,
    criteria: list[str],
    answer: str,
    expected_refs: list[str],
    retries: int = 4,
) -> dict[str, Any]:
    """Call Claude Sonnet 5 via OpenRouter API."""
    if not OPENROUTER_KEY:
        raise ValueError("OPENROUTER_API_KEY not configured!")

    provisions = get_verbatim_provisions(expected_refs)
    numbered_criteria = "\n".join(f"{i}. {c}" for i, c in enumerate(criteria, 1))
    ans_text = (answer or "").strip() or "(the system returned no answer)"

    prompt = (
        JUDGE_PROMPT_TEMPLATE
        .replace("{provisions}", provisions)
        .replace("{question}", question)
        .replace("{criteria}", numbered_criteria)
        .replace("{answer}", f"<candidate_answer>\n{ans_text}\n</candidate_answer>")
    )

    body = json.dumps({
        "model": JUDGE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": TEMPERATURE,
    }).encode()

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "AntifragileEvaluator/1.0",
    }

    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(OPENROUTER_URL, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=90.0) as res:
                raw_json = json.loads(res.read().decode())
                raw_text = raw_json["choices"][0]["message"]["content"] or ""
                clean = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw_text.strip(), flags=re.MULTILINE).strip()
                parsed = json.loads(clean)
                verdicts = parsed.get("verdicts", [])
                tone_dict = parsed.get("tone", {})

                satisfied_list = [bool(v.get("satisfied")) for v in verdicts]
                why_list = [v.get("why", "") for v in verdicts]
                tone_pass = bool(tone_dict.get("appropriate")) and bool(tone_dict.get("clear"))
                tone_why = tone_dict.get("why", "")

                return {
                    "criteria_results": satisfied_list,
                    "criteria_why": why_list,
                    "tone_pass": tone_pass,
                    "tone_why": tone_why,
                    "tone_appropriate": bool(tone_dict.get("appropriate")),
                    "tone_clear": bool(tone_dict.get("clear")),
                    "raw_response": raw_text,
                }
        except Exception as exc:
            last_err = exc
            time.sleep(1.5 * (attempt + 1))

    return {
        "criteria_results": [False] * len(criteria),
        "criteria_why": [f"Judge call error: {last_err}"] * len(criteria),
        "tone_pass": False,
        "tone_why": f"Judge call error: {last_err}",
        "tone_appropriate": False,
        "tone_clear": False,
        "error": str(last_err),
    }


def compute_metrics(
    criteria_results: list[bool],
    pred_refs: list[str],
    expected_refs: list[str],
    tone_pass: bool,
) -> dict[str, Any]:
    strict_correct = all(criteria_results) if criteria_results else False
    loose_correct = sum(1 for c in criteria_results if c) / len(criteria_results) if criteria_results else 0.0

    ref_rec_loose = reference_correctness_loose(pred_refs, expected_refs)
    ref_rec_strict = reference_correctness_strict(pred_refs, expected_refs)
    ref_prec = reference_conciseness(pred_refs, expected_refs)

    return {
        "strict_correctness": strict_correct,
        "loose_correctness": round(loose_correct, 4),
        "ref_recall_loose": round(ref_rec_loose, 4) if ref_rec_loose is not None else None,
        "ref_recall_strict": round(ref_rec_strict, 4) if ref_rec_strict is not None else None,
        "ref_precision": round(ref_prec, 4) if ref_prec is not None else None,
        "tone_pass": tone_pass,
    }


# ==============================================================================
# DATASETS
# ==============================================================================

PART_I_QUESTIONS = [
    {
        "id": "part1_q01",
        "num": 1,
        "question": "What risk categories are provided for AI systems?",
        "live_answer": (
            "At the top, Article 5 (prohibited practices) creates an unacceptable-risk tier that bans "
            "eight AI practices outright, including subliminal/manipulative techniques causing significant "
            "harm, exploitation of vulnerabilities based on age or disability, social scoring by public "
            "authorities, biometric categorisation by sensitive attributes, and real-time remote biometric "
            "identification in public spaces by law enforcement — each with narrow, exhaustively-defined "
            "carve-outs."
        ),
        "live_refs": ["Article 6", "Annex III", "Annex I", "Article 5"],
        "reviewer_critique": (
            "The answer is partially wrong and incomplete, plus an error. The question asks about risk "
            "categories, the AI Act establishes a tiered framework: unacceptable (Art. 5), high-risk "
            "(Art. 6 via Annex I and Annex III), plus GPAI Art. 51-55 as a parallel regime. The answer "
            "addresses only the unacceptable tier. The error: Art. 5(1)(c) prohibits social scoring "
            "without exclusion for public authorities. Also citations list four sources (Art. 5, 6, "
            "Annex I, Annex III), but only Art. 5 is addressed in the body. The enumeration also lists "
            "only five of the eight Art. 5(1) prohibitions, missing (d, e, f )."
        ),
        "criteria": [
            "Identifies the tiered framework (unacceptable risk under Art. 5, high-risk under Art. 6, and transparency/limited-risk under Art. 50 or minimal risk under Art. 4).",
            "Identifies the parallel governance regime for general-purpose AI (GPAI) models under Chapter V / Articles 51-56.",
            "Explains high-risk classification arises via two routes: Annex I (harmonised products) and Annex III (stand-alone use cases).",
            "Does not restrict the Article 5(1)(c) social scoring prohibition to public authorities (applies generally to public and private actors).",
        ],
        "expected_refs": ["Article 5", "Article 6", "Annex I", "Annex III", "Article 50", "Article 51", "Article 4"],
    },
    {
        "id": "part1_q02",
        "num": 2,
        "question": "What types of AI systems or practices are explicitly prohibited by the AI Act?",
        "live_answer": (
            "Article 5 of the EU AI Act prohibits eight categories of AI practice outright: "
            "(a) subliminal, manipulative, or deceptive techniques that cause significant harm; "
            "(b) exploitation of vulnerabilities linked to age, disability, or socio-economic situation; "
            "(c) social scoring by public authorities producing unjustified detrimental treatment across "
            "unrelated contexts."
        ),
        "live_refs": ["Article 5", "Annex II", "Article 27"],
        "reviewer_critique": (
            "Half-right / partial enumeration, repeated error. Correctly identifies Art. 5 and the total "
            "count of eight. Then lists only three. The \"by public authorities\" on social scoring is "
            "the same as Q1 error. Citations include Annex II (the list of serious criminal offences, "
            "relevant only to the Art. 5(1)(h) tangential) and Art. 27 (FRIA, irrelevant to prohibitions)."
        ),
        "criteria": [
            "Identifies Article 5 as governing explicitly prohibited AI practices.",
            "Enumerates beyond the first three to include additional prohibited practices (such as criminal offence profiling (d), untargeted facial scraping (e), workplace/education emotion recognition (f), sensitive biometric categorisation (g), or public real-time remote biometric identification (h)).",
            "Does not erroneously restrict the social scoring prohibition to public authorities only.",
            "Avoids citing unrelated provisions such as Article 27 FRIA or standalone Annex II.",
        ],
        "expected_refs": ["Article 5.1", "Article 5"],
    },
    {
        "id": "part1_q03",
        "num": 3,
        "question": "What is the definition of high risk?",
        "live_answer": (
            "Under Article 6, which sets the classification criteria, an AI system is high-risk in two "
            "scenarios: it is intended as a safety component of a product governed by Union harmonisation "
            "legislation covering machinery, toys, radio equipment, medical devices, lifts, civil aviation, "
            "motor vehicles, marine equipment, rail, and agricultural vehicles — or it falls within one of "
            "the eight use-case categories enumerated in Annex III."
        ),
        "live_refs": ["Article 6", "Annex III"],
        "reviewer_critique": (
            "Mostly correct, with two material omissions. The two-route framework is right and the Annex I "
            "legislation list is a reasonable abbreviation (omitting IVDR, pressure equipment, recreational "
            "craft, equipment for explosive atmospheres, and gas appliances). First omission: the Annex I "
            "route requires the underlying product to undergo third-party conformity assessment under the "
            "sectoral legislation. This is Art 6(1)(b) and it is substantive for MedTech, a Class I medical "
            "device under MDR that doesn't need notified-body assessment doesn't automatically trigger AI Act "
            "high-risk via Art 6(1). It could potentially trigger it via Art. 6(2) and Annex III. Second "
            "omission: Art. 6(3). An Annex III system is not considered high-risk if it performs (a) a narrow "
            "procedural task; (b) improvement of a previously completed human activity; (c) detection of "
            "decision-making patterns without replacing human review; or (d) a preparatory task, unless it "
            "profiles natural persons. The provider must document the self-assessment and register under "
            "Art. 49(2). Omitting this overstates the high-risk perimeter materially. The answer provides a "
            "general frame Citations list Art. 6 and Annex III but not Annex I, despite the answer targeting "
            "mostly the Annex I route."
        ),
        "criteria": [
            "States the two-route high-risk classification structure under Article 6 (Annex I harmonisation products and Annex III use-case areas).",
            "States the Article 6(1)(b) requirement that the Annex I product must undergo third-party conformity assessment under sectoral legislation.",
            "Explains the Article 6(3) derogation where an Annex III system posing no significant risk of harm performs narrow procedural, improvement, pattern detection, or preparatory tasks.",
            "Notes that the Article 6(3) derogation is unavailable if the system performs profiling of natural persons.",
        ],
        "expected_refs": ["Article 6.1", "Article 6.2", "Article 6.3", "Article 6", "Annex I", "Annex III"],
    },
    {
        "id": "part1_q04",
        "num": 4,
        "question": "Which sectors or applications are considered high-risk under the regulation?",
        "live_answer": (
            "Under Article 6 read with Annex III, an AI system is high-risk when it falls into one of eight "
            "use-case categories: biometrics, critical infrastructure, education and vocational training, "
            "employment and worker management (covering recruitment, task allocation, promotion, termination, "
            "and performance evaluation affecting workers' fundamental rights), essential private and public "
            "services, law enforcement, migration/asylum/border control, and administration of justice and "
            "democratic processes."
        ),
        "live_refs": ["Article 6", "Annex I", "Article 25", "Annex III"],
        "reviewer_critique": (
            "Half-right, and one structural omission. The eight Annex III areas are listed correctly. But "
            "\"sectors or applications\" means the Annex I as well and the answer omits this route entirely. "
            "Citations include Article 25 (value-chain responsibilities). Art. 25 has no connection to which "
            "sectors are high-risk."
        ),
        "criteria": [
            "Identifies the Annex III use-case areas (biometrics, critical infrastructure, education, employment, essential services, law enforcement, migration/asylum, justice/democracy).",
            "Identifies the Annex I sectoral harmonisation legislation route (e.g. medical devices, machinery, toys, lifts, civil aviation, vehicles).",
            "Explains that classification depends on satisfying statutory conditions (such as third-party conformity assessment under Art. 6(1) or use-case scope under Art. 6(2)) rather than mere sector membership.",
            "Omits irrelevant value-chain citation Article 25.",
        ],
        "expected_refs": ["Article 6.1", "Article 6.2", "Article 6", "Annex I", "Annex III"],
    },
    {
        "id": "part1_q05",
        "num": 5,
        "question": "How should users be informed when interacting with AI systems?",
        "live_answer": (
            "Under Article 50(1), which requires AI systems intended to interact directly with natural persons "
            "to disclose their AI nature, users must be informed they are communicating with an AI system — "
            "unless this is obvious from context. Broader Article 50 transparency obligations extend further: "
            "providers of emotion-recognition or biometric-categorisation systems must inform exposed persons, "
            "and AI-generated or manipulated content (deepfakes) must be labelled as such."
        ),
        "live_refs": ["Article 50.1", "Article 50"],
        "reviewer_critique": (
            "Mostly right, with a provider/deployer role error. Art. 50(1) interaction disclosure is correctly "
            "stated and correctly attributed to providers. The role error: Art. 50(3) the obligation is on "
            "deployers, not providers. Lexy puts it on providers. The deepfake clause also conflates two distinct "
            "obligations: Art. 50(2) (providers of AI systems generating synthetic content must mark outputs in "
            "machine-readable format) and Art. 50(4) (deployers of deepfakes must disclose artificial generation). "
            "Lexy collapses the roles and obligations."
        ),
        "criteria": [
            "States the Article 50(1) provider duty to design AI systems interacting directly with natural persons so they are informed they are interacting with AI, unless obvious from context.",
            "Correctly assigns the Article 50(3) transparency duty for emotion recognition and biometric categorisation to deployers (not providers).",
            "Distinguishes the Article 50(2) provider duty to mark synthetic outputs in machine-readable format from the Article 50(4) deployer duty to disclose deepfakes or artificially generated text.",
            "Identifies the Article 50(5) standard for manner and timing (clear, distinguishable, at latest at the time of first interaction or exposure).",
        ],
        "expected_refs": ["Article 50.1", "Article 50.2", "Article 50.3", "Article 50.4", "Article 50.5", "Article 50"],
    },
    {
        "id": "part1_q06",
        "num": 6,
        "question": "What are AI systems with minimal risks?",
        "live_answer": (
            "AI systems with minimal risks are those that fall outside the eight high-risk use-case categories "
            "enumerated in biometrics, critical infrastructure, education and vocational training, employment "
            "and worker management (including recruitment, performance evaluation, and termination), essential "
            "public and private services, law enforcement, migration and asylum, and administration of justice — "
            "since it is membership in those categories that triggers the full compliance burden."
        ),
        "live_refs": ["Annex III", "Article 14", "Article 13", "Article 27", "Article 12", "Article 9"],
        "reviewer_critique": (
            "Half-right, partial definition and entirely irrelevant citations. Minimal-risk in the AI Act "
            "framework is the residual category, meaning systems that are neither prohibited under Art. 5, "
            "nor high-risk via Annex I, nor high-risk via Annex III, nor subject to Art. 50 transparency "
            "obligations, nor GPAI. All citations attach to high-risk systems."
        ),
        "criteria": [
            "Explains that minimal risk is a residual category for AI systems not falling under Article 5 (prohibited), Article 6 (high-risk), Article 50 (transparency), or Chapter V (GPAI).",
            "States that providers and deployers of such systems remain subject to the Article 4 requirement to ensure AI literacy among staff.",
            "Mentions Article 95 voluntary codes of conduct fostering application of trustworthy AI requirements to non-high-risk systems.",
            "Avoids attaching high-risk compliance obligations and citations (Articles 9, 12, 13, 14, 27) to minimal-risk systems.",
        ],
        "expected_refs": ["Article 4", "Article 5", "Article 6", "Article 50", "Article 95.1", "Article 95"],
    },
    {
        "id": "part1_q07",
        "num": 7,
        "question": "What are the guiding principles established by the AI Act?",
        "live_answer": (
            "Prior to placing a general-purpose AI model on the Union market, providers established in third "
            "countries shall, by written mandate, appoint an authorised representative which is established in the Union."
        ),
        "live_refs": ["Article 54", "Article 22", "Article 3", "Article 53", "Article 47", "Article 11"],
        "reviewer_critique": (
            "Wrong and topic-shift. The question asks about guiding principles. The answer has no relationship "
            "to the question. The correct response would draw on Recital 27, which articulates seven principles "
            "for trustworthy AI: human agency and oversight; technical robustness and safety; privacy and data "
            "governance; transparency; diversity, non-discrimination and fairness; social and environmental "
            "well-being; accountability."
        ),
        "criteria": [
            "Avoids topic shift to third-country GPAI authorised representatives (Article 54).",
            "Identifies Recital 27 as referencing the seven ethical principles for trustworthy AI (human agency and oversight, technical robustness and safety, privacy and data governance, transparency, diversity/non-discrimination/fairness, societal and environmental well-being, accountability).",
            "Clarifies that the principles are non-binding ethical guidelines originating from the High-Level Expert Group rather than legally operative obligations.",
            "Identifies Article 95(2)(a) as the operative statutory connection where voluntary codes of conduct may cover these ethical guidelines.",
        ],
        "expected_refs": ["Recital 27", "Article 95.2.a", "Article 95"],
    },
    {
        "id": "part1_q08",
        "num": 8,
        "question": "What is the definition of a \"system of artificial intelligence\"?",
        "live_answer": (
            "A machine-based system that is designed to operate with varying levels of autonomy and that may "
            "exhibit adaptiveness after deployment, and that, for explicit or implicit objectives, infers, from "
            "the input it receives, how to generate outputs such as predictions, content, recommendations, or "
            "decisions that can influence physical or virtual environments."
        ),
        "live_refs": ["Article 3", "Article 2"],
        "reviewer_critique": "Correct.",
        "criteria": [
            "Machine-based system designed to operate with varying levels of autonomy.",
            "May exhibit adaptiveness after deployment.",
            "Infers from the input it receives how to generate outputs (predictions, content, recommendations, or decisions).",
            "Outputs can influence physical or virtual environments.",
        ],
        "expected_refs": ["Article 3.1", "Article 3"],
    },
    {
        "id": "part1_q09",
        "num": 9,
        "question": "What are the penalties for violating the provisions of the regulation for high-risk AI systems?",
        "live_answer": (
            "In accordance with the terms and conditions laid down in this Regulation, Member States shall lay "
            "down the rules on penalties and other enforcement measures, which may also include warnings and "
            "non-monetary measures, applicable to infringements of this Regulation by operators, and shall take "
            "all measures necessary to ensure that they are properly and effectively implemented, thereby taking "
            "into account the guidelines issued by the Commission pursuant to Article 96. The penalties provided "
            "for shall be effective, proportionate and dissuasive."
        ),
        "live_refs": ["Article 99"],
        "reviewer_critique": (
            "Wrong by omission. The question asks specifically about high-risk penalties. The substantively "
            "correct answer is Art. 99(4). SMEs benefit from a lower-of-two-amounts rule under Art 99(6). "
            "Lexy recites Art. 99(1), the generic Member State obligation to establish effective, proportionate "
            "and dissuasive penalties. The overall art.99 cited is right."
        ),
        "criteria": [
            "Identifies Article 99(4) as setting the specific administrative fines for infringements of obligations regarding high-risk AI systems (or other obligations not covered by Art. 99(3)).",
            "States the statutory fine maximum: up to €15,000,000 or 3% of total worldwide annual turnover for the preceding financial year, whichever is higher.",
            "Mentions the Article 99(6) rule for SMEs and startups where the lower of the two amounts applies.",
            "Distinguishes specific fine ceilings from the generic Member State mandate in Article 99(1).",
        ],
        "expected_refs": ["Article 99.4", "Article 99.6", "Article 99"],
    },
    {
        "id": "part1_q10",
        "num": 10,
        "question": "What is the difference between the deployer and the provider?",
        "live_answer": (
            "Under Article 3, a provider is any natural or legal person who develops an AI system (or has one "
            "developed) and puts it into service or places it on the market under their own name, while a "
            "deployer is any person who uses that system under their own authority — except for personal, "
            "non-professional use."
        ),
        "live_refs": ["Article 17", "Article 19"],
        "reviewer_critique": (
            "Correct on substance. A more complete answer would point on Art. 25 role transitions, a deployer "
            "becomes a provider with full Art. 16 obligations when they put their name on a high-risk system, "
            "substantially modify it, or change its intended purpose so it becomes high-risk. Citations Art. 17 "
            "and 19 are provider duties, not definitions."
        ),
        "criteria": [
            "Defines provider under Article 3(3) as natural or legal person developing an AI system (or having it developed) and placing it on the market or putting it into service under their own name/trademark.",
            "Defines deployer under Article 3(4) as natural or legal person using an AI system under their authority, except for personal non-professional activity.",
            "Identifies the Article 25 role-transition rule where a deployer assumes provider obligations (e.g. putting name/trademark on system, making substantial modification, or changing intended purpose to high-risk).",
            "Cites Article 3 (and Article 25) rather than unrequested duty articles (Articles 17, 19).",
        ],
        "expected_refs": ["Article 3.3", "Article 3.4", "Article 3", "Article 25"],
    },
    {
        "id": "part1_q11",
        "num": 11,
        "question": (
            "We are a medical device manufacturer building an AI system to analyze X-rays to detect tumors. "
            "Is this system classified as high-risk, and what conformity assessment is required?"
        ),
        "live_answer": (
            "An AI system used as a safety component of a product covered by EU harmonisation legislation in "
            "Annex I (medical devices under MDR/IVDR, machinery, toys, lifts, civil aviation, motor vehicles, etc.), "
            "or which constitutes such a product itself, is high-risk under Article 6.1 when the product requires "
            "a third-party conformity assessment. The full Chapter III Section 2 obligations stack on top of "
            "the sectoral requirements."
        ),
        "live_refs": ["Article 5", "Annex III"],
        "reviewer_critique": (
            "Correct on the rule, but generic on the specific case application. Meaning that the answer doesn't "
            "apply the rule to the X-ray scenario, doesn’t identify device class under MDR, to confirm high-risk "
            "under Art. 6(1) and reference Art. 43(3), for conformity assessment to be integrated into the MDR "
            "notified body assessment, one unified procedure for the manufacturer. Citations to Art. 5 and "
            "Annex III are not relevant to Art. 6(1)/Annex I scenario."
        ),
        "criteria": [
            "Affirms that the tumor-detection AI system is classified as high-risk under Article 6(1).",
            "Applies Regulation (EU) 2017/745 (MDR) classification: diagnostic software is Class IIa or higher under Rule 11 of Annex VIII, requiring notified body involvement under Article 52.",
            "Identifies Article 43(3) as routing the AI Act conformity assessment through the MDR sectoral procedure rather than a separate parallel procedure.",
            "Notes that the notified body must be assessed for competence under the AI Act (Article 31).",
        ],
        "expected_refs": ["Article 6.1", "Article 6", "Annex I", "Article 43.3", "Article 43", "Article 31.4", "Article 31"],
    },
    {
        "id": "part1_q12",
        "num": 12,
        "question": (
            "Can a hospital use an AI system to sort patients based on their biometric data to determine "
            "priority for an experimental clinical trial?"
        ),
        "live_answer": (
            "Using AI to triage or prioritise patients (e.g. for a clinical trial or emergency dispatch) is "
            "high-risk under Annex III(5)(d) (essential services). If the system also uses biometric categorisation "
            "to infer sensitive attributes, it is prohibited under Article 5(1)(g)."
        ),
        "live_refs": ["Article 5.1.g", "Article 6", "Annex III", "Article 5", "Annex I"],
        "reviewer_critique": (
            "Half-right. The Annex III.5(d) citation itself is correctly identified, and it covers emergency "
            "calls, triage, dispatch. But the question is about clinical trial selection, not emergency response. "
            "A clinical-trial selection process doesn't sit there. Depending on the trial's structure, it might "
            "fall under Annex III.5(a) (eligibility for essential public assistance benefits and services including "
            "healthcare services, where the trial offers public-funded access to healthcare), or it might fall "
            "outside Annex III entirely and be governed instead by MDR and the Clinical Trials Regulation. The Art "
            "5(1)(g) conditional is right, but loose on specificity. The prohibition triggers only when biometric "
            "categorisation infers from a closed list: race, political opinions, trade union membership, religious "
            "or philosophical beliefs, sex life, sexual orientation. Biometric data to determine priority doesn't "
            "automatically infer those attributes, it depends entirely on what's being inferred from what. The \"if "
            "the system also uses biometric categorisation to infer sensitive attributes\" framing is correct as a "
            "conditional but doesn't name the closed-list rule."
        ),
        "criteria": [
            "Recognises that the outcome is conditional on what is inferred from the biometric data.",
            "States that the system is prohibited under Article 5(1)(g) if it deduces or infers closed-list attributes (race, political opinions, trade union, religious/philosophical beliefs, sex life, sexual orientation).",
            "Explains that if biometric categorisation infers sensitive attributes outside the closed list, it is high-risk under Annex III point 1(b) / Article 6(2).",
            "Identifies the hospital as a deployer under Article 3(4) subject to Article 50(3) transparency and Article 26 obligations if high-risk.",
            "Does not erroneously equate clinical trial selection with Annex III point 5(d) emergency triage/dispatch.",
        ],
        "expected_refs": ["Article 5.1.g", "Article 5", "Annex III.1.b", "Annex III", "Article 6.2", "Article 6.1", "Article 6", "Article 50.3", "Article 26", "Article 3.4"],
    },
    {
        "id": "part1_q13",
        "num": 13,
        "question": (
            "Our life sciences startup developed a general-purpose AI model trained on massive amounts "
            "of genomic data. What transparency obligations apply to us?"
        ),
        "live_answer": (
            "GPAI provider obligations: maintain technical documentation per Annex XI, supply downstream-provider "
            "information per Annex XII, implement a copyright policy, and publish a sufficiently detailed "
            "training-data summary. Under Article 113, Entry into force + application (Regulation 2024/1689): "
            "in force 1 August 2024."
        ),
        "live_refs": ["Article 53", "Article 113", "Article 53.1", "Article 51", "Article 55"],
        "reviewer_critique": (
            "Correct on substance. All four Article 53(1) GPAI provider obligations are correctly identified. "
            "The sentence about Art 113 is unrelated to the question. A thorough answer would also refer to "
            "Art. 55 systemic-risk obligations. Also Art. 51, if the model meets the systemic-risk threshold "
            "(currently 10^25 FLOPs in cumulative training compute). For a startup model, this typically won't "
            "apply, but it should be named as the gating question, as the question mentions “massive amounts "
            "of genomic data”."
        ),
        "criteria": [
            "Identifies the four transparency and compliance duties for GPAI providers under Article 53(1) (technical documentation under Annex XI, downstream provider information under Annex XII, copyright policy, and publicly available training content summary).",
            "Addresses the systemic risk classification threshold under Article 51 (cumulative compute >= 10^25 FLOPs) as the gating test for additional obligations.",
            "Mentions that if classified as GPAI with systemic risk, Article 55 obligations apply (model evaluations, adversarial testing, incident tracking, cybersecurity).",
            "Omits unrelated entry-into-force recitation (Article 113).",
        ],
        "expected_refs": ["Article 53.1", "Article 53", "Article 51", "Article 55", "Annex XI", "Annex XII"],
    },
    {
        "id": "part1_q14",
        "num": 14,
        "question": (
            "We are a university lab developing an AI model exclusively for scientific research and development "
            "into new life science drugs. Does the AI Act apply to our model before it is released to the market?"
        ),
        "live_answer": (
            "Article 2's scope expressly excludes scientific research and development activity, so an AI "
            "model developed by the operator's lab solely for life-science drug R&D falls outside the AI Act "
            "for as long as it is used only for that purpose and not placed on the EU market or put into service. "
            "That exclusion ends at the point of release: once you place the system on the EU market or put it "
            "into service, Article 2's scope attaches and you become a provider subject to the Act's obligations "
            "according to the model's risk classification."
        ),
        "live_refs": ["Article 2"],
        "reviewer_critique": (
            "Correct. A more precise citation Art 2(6). The answer could also reference Art 2(8) on pre-market "
            "testing in real-world conditions, which is related but distinct for the testing phase between R&D "
            "and market placement."
        ),
        "criteria": [
            "Unambiguous \"No\" verdict: the AI Act does not apply before the model is placed on the market or put into service.",
            "Identifies Article 2(6) which explicitly excludes AI systems and models specifically developed and put into service for the sole purpose of scientific research and development.",
            "Explains that the exclusion ceases once the model is placed on the market or put into service.",
            "Distinguishes R&D from real-world testing under Article 2(8) or Article 54.",
        ],
        "expected_refs": ["Article 2.6", "Article 2.8", "Article 2"],
    },
    {
        "id": "part1_q15",
        "num": 15,
        "question": (
            "We are developing a generative AI chatbot that will be deployed on a hospital website to answer "
            "general patient queries. What transparency obligations apply?"
        ),
        "live_answer": (
            "Under Article 50, limited-risk transparency duties under Article 50 apply cumulatively with "
            "Article 13 high-risk transparency duties — both apply to the same system, not in the alternative. "
            "Article 50 transparency applies regardless of risk tier: because the operator's chatbot interacts "
            "directly with patients, the operator must design it so each user is informed they are dealing with "
            "an AI system (Article 50(1)), and because it is generative, any synthetic content it produces must "
            "be marked in a machine-readable, detectable format (Article 50(2))."
        ),
        "live_refs": ["Article 13", "Article 50", "Annex III", "Annex I", "Article 6"],
        "reviewer_critique": (
            "Half-right. The horizontal principle, that Art. 50 transparency obligations apply regardless of "
            "risk tier and apply cumulatively on Art 13 where both apply, is conceptually correct. The "
            "classification question within the answer is missing: is this chatbot high-risk? A general "
            "patient-query chatbot on a hospital website probably isn't. It's not Annex III.5(d) emergency "
            "triage. It's not Annex III.5(a) eligibility-for-benefits unless it determines eligibility. Most "
            "likely it's limited-risk, Art. 50 alone, not high-risk plus Art. 50. The answer asserts the "
            "cumulative framework without doing the classification analysis that determines whether Art. 13 "
            "applies at all. Provider/deployer role unclear. It uses \"operator\" for both Art. 50(1) (provider "
            "obligation) and Art. 50(2) (provider-of-synthetic-content obligation). For a hospital deploying a "
            "third-party chatbot, the hospital is the deployer, Art. 50(4) (deepfake disclosure where applicable) "
            "would attach to the hospital. Citations include Annex I and Art. 6, but are not addressed in the body."
        ),
        "criteria": [
            "Performs classification analysis concluding that a general patient query chatbot on a website is typically not high-risk, so Article 13 duties do not automatically attach.",
            "Identifies Article 50(1) provider obligation to design the chatbot so natural persons are informed they are interacting with an AI system, unless obvious from context.",
            "Identifies Article 50(2) provider obligation to mark generative AI synthetic content in a machine-readable format.",
            "Clarifies the deployer role (e.g. hospital deployer transparency under Art. 50(4) for deepfakes/synthetic text published on matters of public interest).",
        ],
        "expected_refs": ["Article 50.1", "Article 50.2", "Article 50.4", "Article 50"],
    },
    {
        "id": "part1_q16",
        "num": 16,
        "question": (
            "A pharmaceutical company wants to use an AI system to monitor the emotions and stress levels "
            "of their manufacturing line workers to improve efficiency. Is this allowed?"
        ),
        "live_answer": (
            "Article 5(1)(f) expressly bans AI systems that infer the emotions or mental states of workers "
            "in workplace settings, and deploying such a system to improve manufacturing efficiency falls "
            "squarely within that prohibition with no applicable exception. The only carve-out is narrow: "
            "systems placed on the market strictly for medical or safety reasons (e.g., fatigue detection "
            "to prevent industrial accidents) are not prohibited under Article 5(1)(f), but that primary "
            "purpose must be established at the point of market-placement and cannot be retrofitted — "
            "\"efficiency improvement\" does not qualify."
        ),
        "live_refs": ["Article 5"],
        "reviewer_critique": "Correct.",
        "criteria": [
            "Unambiguous \"No\" verdict: deploying an AI system to monitor workers' emotions/stress to improve efficiency is not allowed.",
            "Identifies Article 5(1)(f) which prohibits AI systems that infer emotions of natural persons in workplace and educational institutions.",
            "Confirms that \"efficiency improvement\" does not qualify for any exception.",
            "Explains the narrow statutory exception is limited strictly to systems intended for medical or safety reasons (e.g. fatigue detection).",
        ],
        "expected_refs": ["Article 5.1.f", "Article 5"],
    },
    {
        "id": "part1_q17",
        "num": 17,
        "question": (
            "Is an AI system intended to be used as a safety component in robotic surgery considered "
            "high-risk under the AI Act?"
        ),
        "live_answer": (
            "An AI system used as a safety component of a product covered by EU harmonisation legislation "
            "in Annex I (medical devices under MDR/IVDR, machinery, toys, lifts, civil aviation, motor "
            "vehicles, etc.), or which constitutes such a product itself, is high-risk under Article 6.1 "
            "when the product requires a third-party conformity assessment. The full Chapter III Section 2 "
            "obligations stack on top of the sectoral requirements."
        ),
        "live_refs": ["Article 6", "Annex I"],
        "reviewer_critique": (
            "Correct on the rule. Generic on application. Robotic surgery devices are typically Class IIb "
            "or III under MDR (Rule 12 or Rule 22), which require notified-body conformity assessment, "
            "so AI components are high-risk under Article 6(1). Correct. The answer doesn’t engage with what's "
            "specifically at stake in robotic surgery: real-time AI involvement in the control loop, the "
            "Art. 14 human-oversight design requirements and the layered post-market surveillance under both "
            "MDR Art 83 and AI Act Art 72. The answer refers to any medical-device scenario without further analysis."
        ),
        "criteria": [
            "Unambiguous \"Yes\" verdict: safety component in robotic surgery is classified as high-risk under Article 6(1).",
            "Applies Regulation (EU) 2017/745 (MDR): robotic surgery systems are typically Class IIb or Class III devices, requiring notified body conformity assessment.",
            "Explains the substantive high-risk requirements applicable to robotic surgery: real-time human oversight under Article 14.",
            "Explains the integration of conformity assessment under Article 43(3) and coordinated post-market surveillance (AI Act Art. 72 and MDR Art. 83).",
        ],
        "expected_refs": ["Article 6.1", "Article 6", "Annex I", "Article 14", "Article 43.3", "Article 72"],
    },
]

PART_II_QUESTIONS = [
    {
        "id": "part2_q01",
        "num": 1,
        "title": "Risk Categories",
        "question_as_put": "What risk categories are provided for AI systems?",
        "question_defect": "The question presupposes that the Regulation provides risk categories.",
        "corrected_question": "What risk categories, if any, does the EU AI Act provide for AI systems?",
        "corrected_answer": (
            "The EU AI Act does not name risk categories. It attaches obligations through conditions: "
            "Article 5 prohibits eight AI practices, Article 6 classifies a system as high-risk on either "
            "of two alternative routes, and Article 50 attaches transparency duties to systems with certain "
            "characteristics without regard to high-risk status. The four tier vocabulary of unacceptable, "
            "high, limited and minimal risk is descriptive shorthand rather than the structure of the EU AI Act."
        ),
        "gold_refs": ["Article 5", "Article 6.1", "Article 6.2", "Article 6", "Article 50"],
        "criteria": [
            "States that the EU AI Act does not formally name or provide statutory risk categories.",
            "Explains that the Act attaches obligations through specific conditions (Article 5 prohibited practices, Article 6 high-risk classification, Article 50 transparency, Chapter V GPAI).",
            "Explains that the four-tier vocabulary (unacceptable, high, limited, minimal) is descriptive shorthand rather than the formal structure of the EU AI Act.",
        ],
    },
    {
        "id": "part2_q02",
        "num": 2,
        "title": "Definition of High Risk",
        "question_as_put": "What is the definition of high risk?",
        "question_defect": "None. Compressed phrasing, Regulation defines classification rather than a state called high-risk.",
        "corrected_question": "What is the definition of high risk under the EU AI Act?",
        "corrected_answer": (
            "An AI system is high-risk on either of two routes under Article 6. Article 6(1) requires two "
            "cumulative conditions: the system is a safety component of, or is itself, a product covered by "
            "Union harmonisation legislation listed in Annex I, and that product must undergo third-party "
            "conformity assessment under that legislation. Article 6(2) makes a system high-risk where it "
            "falls within one of the eight areas listed in Annex III. Article 6(3) removes an Annex III system "
            "from the classification where it poses no significant risk of harm to health, safety or fundamental "
            "rights and performs a narrow procedural task, improves the result of a previously completed human "
            "activity, detects decision-making patterns without replacing or influencing a prior human assessment, "
            "or performs a preparatory task, unless it performs profiling of natural persons, in which case it is "
            "always high-risk."
        ),
        "gold_refs": ["Article 6.1", "Article 6.2", "Article 6.3", "Article 6", "Annex I", "Annex III"],
        "criteria": [
            "States the two alternative routes to high-risk classification under Article 6 (Article 6(1) and Article 6(2)).",
            "States the cumulative Article 6(1) requirements: safety component of or product under Annex I legislation AND requiring third-party conformity assessment.",
            "States Article 6(2) classification for systems falling within the eight areas of Annex III.",
            "Explains the Article 6(3) derogation (no significant risk of harm and meets one of four procedural/improvement/pattern/preparatory conditions).",
            "States that profiling of natural persons is always high-risk under Article 6(3).",
        ],
    },
    {
        "id": "part2_q03",
        "num": 3,
        "title": "Sectors or Applications Considered High-Risk",
        "question_as_put": "Which sectors or applications are considered high-risk under the regulation?",
        "question_defect": "Double-barrelled. The question asks about sectors and about applications, which are not the same object.",
        "corrected_question": "Which sectors or applications are considered high-risk under the EU AI Act?",
        "corrected_answer": (
            "The EU AI Act does not classify by sector. Article 6(1) reaches a system that is a safety component "
            "of, or is itself, a product covered by one of the instruments listed in Annex I where that product "
            "must undergo third-party conformity assessment, so the perimeter there is set by the sectoral legislation "
            "rather than by any sector name. Article 6(2) reaches systems falling within the eight areas of Annex III: "
            "biometrics, critical infrastructure, education and vocational training, employment and workers management "
            "and access to self-employment, access to essential private and essential public services and benefits, "
            "law enforcement, migration and asylum and border control management, and administration of justice and "
            "democratic processes. Article 6(3) removes an Annex III system from the high risk classification where it "
            "poses no significant risk of harm and meets one of four conditions, unless it performs profiling of "
            "natural persons."
        ),
        "gold_refs": ["Article 6.1", "Article 6.2", "Article 6.3", "Article 6", "Annex I", "Annex III"],
        "criteria": [
            "Clarifies that the EU AI Act does not classify systems by broad economic sector names.",
            "Identifies the Article 6(1) route governed by Annex I harmonisation legislation where products require third-party assessment.",
            "Enumerates the eight use-case areas listed in Annex III under Article 6(2).",
            "Mentions the Article 6(3) derogation where an Annex III system poses no significant risk of harm, unless it performs profiling.",
        ],
    },
    {
        "id": "part2_q04",
        "num": 4,
        "title": "Informing Natural Persons Interacting with AI Systems",
        "question_as_put": "How should users be informed when interacting with AI systems?",
        "question_defect": "Ambiguous referent: 'users' is not a statutory term and admits both natural persons and deployers.",
        "corrected_question": "Under the EU AI Act, how must a natural person be informed that they are interacting with an AI system?",
        "corrected_answer": (
            "Article 50(1) requires providers to design AI systems intended to interact directly with natural "
            "persons so that those persons are informed they are interacting with an AI system, unless that is "
            "obvious from the point of view of a natural person who is reasonably well-informed, observant and "
            "circumspect, taking into account the circumstances and the context of use. On the deployer side the "
            "duties are different ones. Article 50(3) requires deployers of an emotion recognition system or a "
            "biometric categorisation system to inform the natural persons exposed of the operation of the system, "
            "and to process personal data in accordance with Regulation (EU) 2016/679, the General Data Protection "
            "Regulation, together with Regulation (EU) 2018/1725 and Directive (EU) 2016/680 as applicable. Article "
            "50(4) requires deployers of a system generating or manipulating deep fake image, audio or video content "
            "to disclose that it has been artificially generated or manipulated, and, in its second subparagraph, "
            "requires the same of deployers of a system generating text published to inform the public on matters "
            "of public interest, subject to an exception that requires both human review or editorial control and a "
            "natural or legal person holding editorial responsibility. Article 50(5) governs the manner: the "
            "information must be provided in a clear and distinguishable manner, at the latest at the time of the "
            "first interaction or exposure, and must conform to the applicable accessibility requirements. The duty "
            "under Article 50(1) binds the provider at design and development stage. It does not apply to AI "
            "systems authorised by law to detect, prevent, investigate or prosecute criminal offences, unless those "
            "systems are available for the public to report a criminal offence. Separately from Article 50, Article "
            "26(11) requires deployers of Annex III high-risk systems that make or assist in making decisions "
            "related to natural persons to inform those persons that they are subject to the use of the system. "
            "Article 50(6) preserves Chapter III requirements and other Union or national transparency obligations, "
            "so these stack rather than substitute."
        ),
        "gold_refs": ["Article 50.1", "Article 50.3", "Article 50.4", "Article 50.5", "Article 50", "Article 26.11"],
        "criteria": [
            "Identifies the Article 50(1) provider design duty to inform natural persons they are interacting with an AI system unless obvious from context.",
            "States the Article 50(5) manner and timing standard: information must be provided in a clear and distinguishable manner at the latest at the time of first interaction or exposure, complying with accessibility requirements.",
            "Distinguishes deployer-specific obligations (such as Article 50(3) for emotion recognition/biometrics and Article 50(4) for deepfakes).",
            "Notes Article 26(11) deployer obligation to inform natural persons subject to decisions assisted by Annex III high-risk systems.",
        ],
    },
    {
        "id": "part2_q05",
        "num": 5,
        "title": "Minimal Risk Category Inquiry",
        "question_as_put": "What are AI systems with minimal risks?",
        "question_defect": "Defective. The question presupposes that minimal risk is a category the EU AI Act provides. It is not.",
        "corrected_question": "Does the EU AI Act provide for a category of minimal risk AI systems?",
        "corrected_answer": (
            "The EU AI Act does not provide for a minimal risk category. Obligations attach through conditions, "
            "at Article 5 for prohibited practices, Article 6 for high-risk classification, Article 50 for transparency "
            "and Chapter V for general-purpose AI models, and a system meeting none of those conditions falls outside "
            "them rather than into a named residual class. Such a system is not free of obligation: Article 4 requires "
            "providers and deployers of any AI system to take measures to ensure a sufficient level of AI literacy "
            "among their staff and other persons dealing with the operation and use of the system on their behalf. "
            "Article 95(1) directs the AI Office and the Member States to encourage codes of conduct fostering "
            "voluntary application of some or all of the Chapter III Section 2 requirements to systems other than "
            "high-risk systems. Article 95(2) addresses codes for all AI systems, listing elements including applicable "
            "elements of the Union ethical guidelines for trustworthy AI, environmental sustainability, AI literacy, "
            "inclusive design, and impact on vulnerable persons. A code of conduct permits compliance to be demonstrated "
            "and does not create a presumption of conformity; the Article 40 harmonised standards mechanism does the latter."
        ),
        "gold_refs": ["Article 4", "Article 5", "Article 6", "Article 50", "Article 95.1", "Article 95.2", "Article 40"],
        "criteria": [
            "Unambiguous \"No\" verdict: the Act does not provide for a formal statutory category of minimal risk AI systems.",
            "Explains that obligations attach through specific conditions (Articles 5, 6, 50, Chapter V) and systems outside them form an unnamed residual class.",
            "States that such systems are not free of obligations, identifying the Article 4 AI literacy duty for providers and deployers.",
            "Identifies Article 95(1)-(2) voluntary codes of conduct for non-high-risk systems.",
        ],
    },
    {
        "id": "part2_q06",
        "num": 6,
        "title": "Guiding Principles Inquiry",
        "question_as_put": "What are the guiding principles established by the AI Act?",
        "question_defect": "Defective. The question presupposes that the EU AI Act establishes guiding principles. It does not.",
        "corrected_question": "Does the EU AI Act establish guiding principles for AI?",
        "corrected_answer": (
            "The EU AI Act does not establish guiding principles. Recital 27 recalls the 2019 Ethics guidelines "
            "for trustworthy AI developed by the independent High-Level Expert Group appointed by the Commission, "
            "and records the seven non-binding ethical principles that group developed: human agency and oversight; "
            "technical robustness and safety; privacy and data governance; transparency; diversity, non-discrimination "
            "and fairness; societal and environmental well-being; and accountability. A recital explains the "
            "legislature's reasoning and cannot create, extend or narrow an obligation the operative text does not "
            "contain, and Recital 27 says expressly that the principles are without prejudice to the legally binding "
            "requirements of the Act. The single operative connection is Article 95(2)(a), which lists applicable "
            "elements of the Union ethical guidelines for trustworthy AI among the matters that voluntary codes "
            "of conduct may cover."
        ),
        "gold_refs": ["Recital 27", "Article 95.2.a", "Article 95"],
        "criteria": [
            "Unambiguous \"No\" verdict: the Act does not establish legally operative guiding principles.",
            "Explains that Recital 27 recalls the seven non-binding ethical principles developed by the 2019 High-Level Expert Group.",
            "Clarifies that recitals are explanatory and cannot create, extend, or narrow legally binding obligations.",
            "Identifies Article 95(2)(a) as the single operative statutory connection where voluntary codes of conduct may cover trustworthy AI ethical guidelines.",
        ],
    },
    {
        "id": "part2_q07",
        "num": 7,
        "title": "Medical Imaging Tumor Detection (X-rays)",
        "question_as_put": (
            "We are a medical device manufacturer building an AI system to analyze X-rays to detect tumors. "
            "Is this system classified as high-risk, and what conformity assessment is required?"
        ),
        "question_defect": "None. The device class is not supplied, but it is not determinative (Class IIa+ requires notified body).",
        "corrected_question": (
            "We are a medical device manufacturer building an AI system to analyze X-rays to detect tumors. "
            "Under the EU AI Act, is this system classified as high-risk, and what conformity assessment is required?"
        ),
        "corrected_answer": (
            "Yes, high-risk. Software providing information used to take decisions with a diagnostic purpose is "
            "class IIa or above under Rule 11 of Annex VIII to Regulation (EU) 2017/745 on medical devices, every "
            "one of those classes requires notified body involvement under Article 52 of Regulation (EU) 2017/745, "
            "and both cumulative conditions of Article 6(1) of the EU AI Act are therefore satisfied. Article 43(3) "
            "routes the conformity assessment through the medical device procedure rather than alongside it: the "
            "manufacturer follows the relevant procedure required under Regulation (EU) 2017/745, and the Chapter "
            "III Section 2 requirements of the EU AI Act form part of that assessment. The notified body notified "
            "under Regulation (EU) 2017/745 may control conformity with those requirements only where its compliance "
            "with Article 31(4), (5), (10) and (11) of the Act has been assessed in the context of the notification "
            "procedure under that legislation, so the manufacturer should confirm that its existing notified body "
            "has been assessed for the scope of the EU AI Act."
        ),
        "gold_refs": ["Article 6.1", "Article 6", "Annex I", "Article 43.3", "Article 43", "Article 31.4", "Article 31"],
        "criteria": [
            "Unambiguous \"Yes, high-risk\" classification verdict under Article 6(1).",
            "Identifies classification under Regulation (EU) 2017/745 (MDR): software for diagnostic decisions is Class IIa or higher under Rule 11 of Annex VIII.",
            "States that Class IIa or higher requires notified body involvement under Article 52 of Regulation (EU) 2017/745.",
            "Identifies Article 43(3) routing the AI Act conformity assessment through the existing medical device procedure as an integrated assessment.",
            "Notes that the notified body must have its competence assessed for the AI Act under Article 31.",
        ],
    },
    {
        "id": "part2_q08",
        "num": 8,
        "title": "Hospital Biometric Clinical Trial Triage (Conditional Formulation)",
        "question_as_put": (
            "Can a hospital use an AI system to sort patients based on their biometric data to determine "
            "priority for an experimental clinical trial?"
        ),
        "question_defect": "Defective. No unique correct answer possible without knowing what is inferred.",
        "corrected_question": (
            "Under the EU AI Act, can a hospital use an AI system to sort patients based on their biometric "
            "data to determine priority for an experimental clinical trial?"
        ),
        "corrected_answer": (
            "Whether the hospital may use the system turns on a fact the question does not supply, which is what "
            "the system infers from the biometric data. Where the system categorises patients individually to "
            "deduce or infer race, political opinions, trade union membership, religious or philosophical beliefs, "
            "sex life or sexual orientation, Article 5(1)(g) prohibits the placing on the market, the putting into "
            "service for this specific purpose and the use of such a system, so the hospital may not use it for "
            "that purpose at all. Where it performs biometric categorisation according to sensitive or protected "
            "attributes or characteristics based on the inference of those attributes without reaching that closed "
            "list, Annex III, point 1(b) makes it high-risk under Article 6(2), subject to the Article 6(3) derogation. "
            "Where it sorts on clinically relevant parameters without inferring any protected attribute, neither "
            "provision reaches it and classification turns on Article 6(1), that is, on whether the system is or "
            "is a safety component of a product under Annex I legislation that must undergo third-party conformity "
            "assessment. On every branch the hospital is the deployer under Article 3(4): Article 50(3) requires "
            "it to inform the patients exposed of the operation of the system wherever the system is a biometric "
            "categorisation system within Article 3(40), and the Article 26 deployer obligations attach wherever "
            "the system is high-risk."
        ),
        "gold_refs": [
            "Article 5.1.g", "Article 5", "Annex III.1.b", "Annex III", "Article 6.2", "Article 6.3",
            "Article 6.1", "Article 6", "Annex I", "Article 50.3", "Article 50", "Article 26", "Article 3.4"
        ],
        "criteria": [
            "Identifies that the legal answer is conditional upon what the system infers from biometric data (surfacing the missing determinative fact).",
            "Explains Branch 1: prohibited under Article 5(1)(g) if the system categorises individuals to deduce or infer closed-list attributes (race, political opinions, trade union, religious beliefs, sex life, sexual orientation).",
            "Explains Branch 2: classified as high-risk under Annex III point 1(b) and Article 6(2) if categorising according to sensitive/protected attributes outside the closed list.",
            "Explains Branch 3: if sorting only on clinically relevant physiological parameters without inferring protected attributes, classification falls back to Article 6(1) and Annex I (MDR).",
            "Identifies the hospital's role as a deployer under Article 3(4), owing Article 50(3) transparency and Article 26 obligations where high-risk.",
        ],
    },
    {
        "id": "part2_q09",
        "num": 9,
        "title": "Hospital Biometric Clinical Trial Triage — Branch Variant A (Prohibited)",
        "question_as_put": (
            "Under the EU AI Act, can a hospital use an AI system to sort patients based on their biometric "
            "data to determine priority for an experimental clinical trial, where the system infers each patient's race from that data?"
        ),
        "question_defect": "None. Discrete fact-supplied branch testing prohibited classification.",
        "corrected_question": (
            "Under the EU AI Act, can a hospital use an AI system to sort patients based on their biometric "
            "data to determine priority for an experimental clinical trial, where the system infers each patient's race from that data?"
        ),
        "corrected_answer": (
            "No. Article 5(1)(g) prohibits the placing on the market, the putting into service for this specific "
            "purpose and the use of biometric categorisation systems that categorise natural persons individually "
            "on the basis of their biometric data to deduce or infer race, and the exclusion in that provision "
            "covers only the labelling or filtering of lawfully acquired biometric datasets and categorisation of "
            "biometric data in the area of law enforcement, neither of which describes trial selection. The hospital "
            "may not use the system for that purpose at all, and no governance measures make it available."
        ),
        "gold_refs": ["Article 5.1.g", "Article 5"],
        "criteria": [
            "Unambiguous \"No\" verdict: the hospital may not use the system for this purpose.",
            "Identifies Article 5(1)(g) which prohibits biometric categorisation systems that categorise individuals on biometric data to deduce or infer race.",
            "Explains that the narrow statutory exclusions (law enforcement categorisation and dataset filtering/labelling) do not apply to clinical trial selection.",
            "Concludes that no compliance or governance measures can make the prohibited practice lawful.",
        ],
    },
    {
        "id": "part2_q10",
        "num": 10,
        "title": "Hospital Biometric Clinical Trial Triage — Branch Variant B (High-Risk)",
        "question_as_put": (
            "Under the EU AI Act, can a hospital use an AI system to sort patients based on their biometric "
            "data to determine priority for an experimental clinical trial, where the system infers each patient's sex from that data?"
        ),
        "question_defect": "None. Discrete fact-supplied branch testing Annex III high-risk classification.",
        "corrected_question": (
            "Under the EU AI Act, can a hospital use an AI system to sort patients based on their biometric "
            "data to determine priority for an experimental clinical trial, where the system infers each patient's sex from that data?"
        ),
        "corrected_answer": (
            "Yes, but as a high-risk system. Sex is a protected attribute short of the closed list in Article 5(1)(g), "
            "so the prohibition does not reach it, and Annex III, point 1(b) covers AI systems intended to be used "
            "for biometric categorisation according to sensitive or protected attributes based on the inference "
            "of those attributes, which makes the system high-risk under Article 6(2) in so far as its use is "
            "permitted under relevant Union or national law. The Article 6(3) derogation is unavailable, because a "
            "system evaluating personal aspects of a natural person to determine that person's trial priority "
            "performs profiling within Article 3(52), and the final subparagraph of Article 6(3) makes a profiling "
            "system always high-risk. The hospital is the deployer under Article 3(4) and carries the Article 26 "
            "obligations together with the Article 50(3) duty to inform the patients exposed of the operation of the system."
        ),
        "gold_refs": [
            "Annex III.1.b", "Annex III", "Article 6.2", "Article 6.3", "Article 6",
            "Article 3.52", "Article 50.3", "Article 50", "Article 26", "Article 3.4"
        ],
        "criteria": [
            "Qualified affirmative verdict: \"Yes, but classified as high-risk\".",
            "Explains that sex is a protected attribute falling outside the Article 5(1)(g) closed list, so it is not prohibited.",
            "Identifies Annex III point 1(b) and Article 6(2) as classifying biometric categorisation according to protected attributes as high-risk.",
            "Explains that the Article 6(3) derogation is unavailable because evaluating patient priority constitutes profiling under Article 3(52), which is always high-risk.",
            "Identifies the hospital as deployer under Article 3(4), subject to Article 26 and Article 50(3) obligations.",
        ],
    },
    {
        "id": "part2_q11",
        "num": 11,
        "title": "Hospital Biometric Clinical Trial Triage — Branch Variant C (Unclassified)",
        "question_as_put": (
            "Under the EU AI Act, can a hospital use an AI system to sort patients based on their biometric "
            "data to determine priority for an experimental clinical trial, where the system sorts on clinically "
            "relevant physiological parameters and infers no sensitive or protected attribute?"
        ),
        "question_defect": "None. Discrete fact-supplied branch testing fallback / non-classification under biometrics.",
        "corrected_question": (
            "Under the EU AI Act, can a hospital use an AI system to sort patients based on their biometric "
            "data to determine priority for an experimental clinical trial, where the system sorts on clinically "
            "relevant physiological parameters and infers no sensitive or protected attribute?"
        ),
        "corrected_answer": (
            "Yes, and neither Article 5(1)(g) nor Annex III, point 1(b) reaches it, because no protected attribute "
            "is inferred. Classification then turns on Article 6(1), that is, on whether the system is or is a "
            "safety component of a product covered by Annex I legislation that must undergo third-party conformity "
            "assessment, which for hospital software will usually mean Regulation (EU) 2017/745 on medical devices. "
            "Article 50(3) does not attach either, since the system is not a biometric categorisation system within "
            "Article 3(40)."
        ),
        "gold_refs": [
            "Article 5.1.g", "Article 5", "Annex III.1.b", "Annex III", "Article 6.1",
            "Article 6", "Annex I", "Article 50.3", "Article 3.40"
        ],
        "criteria": [
            "Affirmative verdict: \"Yes\", and not captured by Article 5(1)(g) or Annex III point 1(b) because no sensitive or protected attributes are inferred.",
            "Explains that classification falls back to Article 6(1) and Annex I (Regulation (EU) 2017/745 MDR).",
            "Explains that Article 50(3) transparency does not apply because the system is not a biometric categorisation system under Article 3(40).",
        ],
    },
]


def run_full_evaluation():
    out_dir = REPO / "docs" / "measurements" / "r409"
    out_file = out_dir / "antifragile_frontier_judge_results.json"

    print("=" * 80)
    print("STARTING ANTIFRAGILE AI BENCHMARK EVALUATION WITH CLAUDE SONNET 5")
    print(f"Model: {JUDGE_MODEL} | Temp: {TEMPERATURE} | OpenRouter Key: {'OK' if OPENROUTER_KEY else 'MISSING'}")
    print("=" * 80)

    results: dict[str, Any] = {
        "metadata": {
            "model": JUDGE_MODEL,
            "temperature": TEMPERATURE,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "evaluator": "Antifragile AI Benchmark Evaluator",
        },
        "part_1": [],
        "part_2": [],
    }

    # Step 1: Execute Local Engine for Part I
    print("\n[PART I] Querying local engine for 17 questions in deterministic offline mode...")
    for item in PART_I_QUESTIONS:
        qid = item["id"]
        q = item["question"]
        print(f"  -> Querying {qid} (Q{item['num']})...", end=" ", flush=True)
        res = query_engine(q)
        item["engine_answer"] = res["answer"]
        item["engine_refs"] = res["references"]
        item["engine_latency_s"] = res["latency_s"]
        print(f"done ({res['latency_s']}s, {len(res['references'])} refs)")

    # Step 2: Execute Local Engine for Part II
    print("\n[PART II] Querying local engine for 11 questions/variants...")
    for item in PART_II_QUESTIONS:
        qid = item["id"]
        q = item["corrected_question"]
        print(f"  -> Querying {qid} ({item['title']})...", end=" ", flush=True)
        res = query_engine(q)
        item["engine_answer"] = res["answer"]
        item["engine_refs"] = res["references"]
        item["engine_latency_s"] = res["latency_s"]
        print(f"done ({res['latency_s']}s, {len(res['references'])} refs)")

    # Step 3: Run Frontier Judge for Part I (Both Current Engine and Live Original)
    print("\n[PART I] Judging with Claude Sonnet 5 via OpenRouter...")
    for item in PART_I_QUESTIONS:
        qid = item["id"]
        q = item["question"]
        crit = item["criteria"]
        exp_refs = item["expected_refs"]

        # 3a: Judge Current Engine
        print(f"  -> Judging Current Engine for {qid}...", end=" ", flush=True)
        j_engine = call_judge(q, crit, item["engine_answer"], exp_refs)
        m_engine = compute_metrics(
            j_engine["criteria_results"],
            item["engine_refs"],
            exp_refs,
            j_engine["tone_pass"],
        )
        print(f"Strict: {m_engine['strict_correctness']} | Loose: {m_engine['loose_correctness']} | Tone: {m_engine['tone_pass']}")

        # 3b: Judge Live Original
        print(f"  -> Judging Live Original for {qid}...", end=" ", flush=True)
        j_live = call_judge(q, crit, item["live_answer"], exp_refs)
        m_live = compute_metrics(
            j_live["criteria_results"],
            item["live_refs"],
            exp_refs,
            j_live["tone_pass"],
        )
        print(f"Strict: {m_live['strict_correctness']} | Loose: {m_live['loose_correctness']} | Tone: {m_live['tone_pass']}")

        p1_entry = {
            "id": qid,
            "num": item["num"],
            "question": q,
            "reviewer_critique": item["reviewer_critique"],
            "expected_refs": exp_refs,
            "criteria": crit,
            "live_original": {
                "answer": item["live_answer"],
                "references": item["live_refs"],
                "judge": j_live,
                "metrics": m_live,
            },
            "current_engine": {
                "answer": item["engine_answer"],
                "references": item["engine_refs"],
                "latency_s": item["engine_latency_s"],
                "judge": j_engine,
                "metrics": m_engine,
            },
            "delta": {
                "strict_improvement": (1 if m_engine["strict_correctness"] else 0) - (1 if m_live["strict_correctness"] else 0),
                "loose_diff": round(m_engine["loose_correctness"] - m_live["loose_correctness"], 4),
                "ref_precision_diff": (
                    round(m_engine["ref_precision"] - m_live["ref_precision"], 4)
                    if m_engine["ref_precision"] is not None and m_live["ref_precision"] is not None
                    else None
                ),
            }
        }
        results["part_1"].append(p1_entry)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    # Step 4: Run Frontier Judge for Part II
    print("\n[PART II] Judging with Claude Sonnet 5 via OpenRouter...")
    for item in PART_II_QUESTIONS:
        qid = item["id"]
        q = item["corrected_question"]
        crit = item["criteria"]
        gold_refs = item["gold_refs"]

        print(f"  -> Judging Current Engine for {qid} ({item['title']})...", end=" ", flush=True)
        j_engine = call_judge(q, crit, item["engine_answer"], gold_refs)
        m_engine = compute_metrics(
            j_engine["criteria_results"],
            item["engine_refs"],
            gold_refs,
            j_engine["tone_pass"],
        )
        print(f"Strict: {m_engine['strict_correctness']} | Loose: {m_engine['loose_correctness']} | Tone: {m_engine['tone_pass']}")

        p2_entry = {
            "id": qid,
            "num": item["num"],
            "title": item["title"],
            "question_as_put": item["question_as_put"],
            "question_defect": item["question_defect"],
            "corrected_question": q,
            "gold_answer": item["corrected_answer"],
            "gold_refs": gold_refs,
            "criteria": crit,
            "current_engine": {
                "answer": item["engine_answer"],
                "references": item["engine_refs"],
                "latency_s": item["engine_latency_s"],
                "judge": j_engine,
                "metrics": m_engine,
            },
        }
        results["part_2"].append(p2_entry)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    # Save output
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print(f"EVALUATION COMPLETE! Raw results saved to: {out_file}")
    print("=" * 80)


if __name__ == "__main__":
    run_full_evaluation()
