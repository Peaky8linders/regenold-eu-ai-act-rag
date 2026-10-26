"""R472 — build the expert-review appendix of 26 October 2026 (HTML, then PDF via headless Chrome).

It updates the appendix of 23 October (``docs/measurements/r467/build_appendix.py``): the
same ten reviewed questions, asked again on the build production serves now, and the
corrections made since.

Inputs (this directory unless noted):
  * ``../r467/sept29_answers.json``             the ten answers the October review assessed,
                                                as the 29 September report update printed them;
  * ``expert_review_rerun.json``                the same ten questions asked live on 26 October;
  * ``offline_wire_replay.json``                those ten replayed with no model reachable;
  * ``paraphrase_rerun.json``                   the 30 remediation rephrasings, live + offline;
  * ``heldout.json`` / ``heldout_judged.json``  the 20 held-out rephrasings and their grades;
  * ``../r467/*``                               the 23 October runs of the same sets, for the
                                                before/after columns, and the statutory passages;
  * ``../r468``, ``../r469``, ``../r470``       the measurements of the corrections made since.

Every piece of "after" evidence below is a verbatim substring of the live answer; the
build fails if one is not, so the document cannot quote text the system did not
produce. Absences (``absent``) are checked the same way.

The statutory passages are checked against the Official Journal text under ``tmp/legal-audit-2026-09-29``; a
worktree has none, so set ``REGENOLD_LEGAL_TEXT_DIR`` to the main checkout's folder.

Usage (repo root):
    .venv/Scripts/python.exe docs/measurements/r472/build_appendix.py [--no-pdf] [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
R467, R468, R469, R470 = (HERE.parent / f"r{n}" for n in (467, 468, 469, 470))
OUT_NAME = "Appendix-Expert-Review-2026-10-26"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
DATE = "26 October 2026"
DAY = "26 October"
DAY_SHORT = "26 Oct"
PREV_DAY = "23 October"
NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
                9: "nine", 10: "ten"}

E = html.escape


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The review's points, per question. ``before`` is (tag, remark): a remark that
# starts "Review:" reports the review's finding (quoted where marked); one that
# starts "Answer:" describes the 29 September answer, for the two cases where the
# review set out a correct position instead of numbered points. ``after`` is the
# list of verbatim quotes from the 23 October answer that state the point.
# ---------------------------------------------------------------------------
CASES: list[dict] = [
    {
        "id": "Q45", "part": "A", "title": "Instructions for use (Article 13)",
        "verdict": "Wrong in part, borderline", "kind": "wrong",
        "expected": "Article 13.3",
        "found": "Qualifiers attached to the Article 13(3) categories omitted; list not presented as "
                 "a minimum; Article 13(2) requirements abridged",
        "points": [
            {"label": "Qualifiers attached to the categories",
             "before": ("DEFECT", "Review: every category is named, but the conditions the Act attaches "
                                  "to them are omitted."),
             "after": ["(a) the identity and contact details of the provider and, where applicable, "
                       "of its authorised representative",
                       "(c) the changes to the system and its performance predetermined by the provider "
                       "at the initial conformity assessment, if any",
                       "(f) where relevant, the mechanisms enabling deployers to collect, store and "
                       "interpret the logs under Article 12"]},
            {"label": "Article 13(3) as a minimum, points (a) to (f)",
             "before": ("DEFECT", "Review: \u201cArt. 13(3) sets the minimum content of the instructions "
                                  "for use at points (a) to (f), and several items are required only where "
                                  "applicable, when appropriate or if any.\u201d"),
             "after": ["The Article 13(3) list is a minimum, and the items qualified by where applicable, "
                       "when appropriate or if any are required only where that condition is met."]},
            {"label": "Article 13(2): form and quality of the instructions",
             "before": ("DEFECT", "Review: Article 13(2) requires the instructions to accompany the system "
                                  "in an appropriate digital format or otherwise, with \u201cconcise, "
                                  "complete, correct and clear information that is relevant, accessible and "
                                  "comprehensible to deployers\u201d."),
             "after": ["Article 13(2) requires it to be accompanied by instructions for use, in an "
                       "appropriate digital format or otherwise, containing concise, complete, correct and "
                       "clear information that is relevant, accessible and comprehensible to deployers."]},
        ],
        "notes": ["The answer also states Article 13(1). It sets out point (b) as items (i) to (vii), "
                  "introduced by “including” as in the Act and closely following its wording, with the "
                  "testing and validation reference in (ii) and the intended purpose in (iii) and (vi)."],
        "note_checks": ["limitations of performance, including (i) the intended purpose",
                        "against which the system has been tested and validated",
                        "taking into account the intended purpose"],
    },
    {
        "id": "Q96", "part": "A", "title": "Annex III areas and healthcare",
        "verdict": "Correct overall, 2 precision points", "kind": "correct",
        "expected": "Annex III",
        "found": "Annex III, point 5(a), paraphrased loosely; headings of areas 4 and 5 abridged",
        "points": [
            {"label": "Annex III, point 5(a), as worded in the Act",
             "before": ("PRECISION", "Review: point 5(a) is paraphrased loosely: it omits \u201con behalf "
                                     "of\u201d and the granting, reducing, revoking or reclaiming of "
                                     "benefits, and reduces \u201cessential public assistance benefits and "
                                     "services\u201d to \u201cessential services\u201d."),
             "after": ["AI systems intended to be used by public authorities or on behalf of public "
                       "authorities to evaluate the eligibility of natural persons for essential public "
                       "assistance benefits and services, including healthcare services, and to grant, "
                       "reduce, revoke or reclaim them"]},
            {"label": "Headings of areas 4 and 5",
             "before": ("PRECISION", "Review: the names of areas 4 and 5 are compressed."),
             "after": ["employment, workers' management and access to self-employment; access to and "
                       "enjoyment of essential private services and essential public services and benefits"]},
        ],
        "notes": ["In line with the review's correct position, the answer also identifies points 5(c) and "
                  "7(b), neither of which concerns healthcare decision-making. The 29 September reference "
                  "to Article 6(1) and Annex I is withdrawn; the answer cites Annex III only, the expected "
                  "reference."],
    },
    {
        "id": "Q17", "part": "A", "title": "Amendment of Annex III by delegated act",
        "verdict": "Correct overall, 2 precision points", "kind": "correct",
        "expected": "Article 7.1",
        "found": "Article 97(6) objection procedure omitted (\u201capplies\u201d for \u201center into "
                 "force\u201d); area headings abridged",
        "points": [
            {"label": "Article 97(6): entry into force, objection period and extension",
             "before": ("PRECISION", "Review: the delegated act \u201cshall enter into force only if no "
                                     "objection has been expressed\u201d within three months of "
                                     "notification, extendable by three months; the answer says "
                                     "\u201capplies\u201d and omits the period and its extension."),
             "after": ["the act enters into force only if neither the European Parliament nor the Council "
                       "objects within three months of notification, a period extended by three months at "
                       "the initiative of either of them, or earlier where both inform the Commission that "
                       "they will not object (Article 97(6))"]},
            {"label": "Annex III area headings",
             "before": ("PRECISION", "Review: some area names are compressed."),
             "after_tag": "REMOVED",
             "after": ["the AI systems are intended to be used in any of the areas already listed in "
                       "Annex III"],
             "after_note": "The abridged names no longer appear: the answer refers to the areas listed in "
                           "Annex III rather than naming them."},
        ],
        "notes": ["In line with the review's correct position, the answer also states the consultation of "
                  "experts designated by each Member State (Article 97(4)); it adds the power to remove use "
                  "cases (Article 7(3))."],
    },
    {
        "id": "Q74", "part": "A", "title": "AI-generated audio in an artistic work",
        "verdict": "Wrong in part", "kind": "wrong",
        "expected": "Article 50.4",
        "found": "Deployer status and \u201cevidently\u201d artistic character assumed; provider route, "
                 "application date, Article 3(60) wording and Article 50(5) omitted; non-statutory example",
        "points": [
            {"label": "Capacity of the asker: personal non-professional activity",
             "before": ("DEFECT", "Review: deployer status is assumed; the question does not state the "
                                  "asker's capacity or whether the use is a personal non-professional "
                                  "activity, in which case there is no deployer and no disclosure "
                                  "obligation."),
             "after": ["A person using the system is a deployer under Article 3(4) only where the use is not "
                       "in the course of a personal non-professional activity, and the Act does not apply to "
                       "the obligations of a natural person using an AI system in the course of a purely "
                       "personal non-professional activity (Article 2(10))"]},
            {"label": "\u201cEvidently\u201d artistic character as a condition",
             "before": ("DEFECT", "Review: \u201cevidently\u201d is treated as implied from the outset; "
                                  "whether the work is evidently artistic to the persons exposed to it is a "
                                  "separate condition."),
             "after": ["where it forms part of an evidently artistic, creative, satirical, fictional or "
                       "analogous work that duty is limited to disclosing the existence of the generated "
                       "content in an appropriate manner that does not hamper the display or enjoyment of "
                       "the work"]},
            {"label": "Provider route (Article 3(3) and (11))",
             "before": ("DEFECT", "Review: a person who developed the system, or had it developed, and "
                                  "put it into service for own use under their own name is its provider, "
                                  "bound by the Article 50(2) marking obligation, to which artistic purpose "
                                  "is no exception; on the question's facts, an unlikely edge case."),
             "after": ["a person who develops the system, or has it developed, and puts it into service for "
                       "their own use under their own name or trademark is also its provider (Article 3(3) "
                       "and Article 3(11)) and so bears that marking duty"]},
            {"label": "Application date of Article 50",
             "before": ("DEFECT", "Review: the application date of the Article 50 obligations is not "
                                  "stated."),
             "after": ["these duties apply from 2 August 2026"]},
            {"label": "Article 3(60): \u201cto a person\u201d",
             "before": ("PRECISION", "Review: the deep fake definition omits \u201cto a person\u201d."),
             "after": ["would falsely appear to a person to be authentic or truthful (Article 3(60))"]},
            {"label": "Article 50(5): manner, timing and accessibility",
             "before": ("PRECISION", "Review: Article 50(5) requires the disclosure to be clear and "
                                     "distinguishable, made at the latest at the time of first exposure, "
                                     "and accessible; the answer does not state it."),
             "after": ["The information must be clear and distinguishable, given at the latest at the time "
                       "of first exposure and accessible (Article 50(5))"]},
            {"label": "No non-statutory wording",
             "before": ("PRECISION", "Review: \u201csuch as a credit or accompanying note\u201d does not "
                                     "derive from the Act."),
             "after_tag": "REMOVED",
             "absent": ["credit or accompanying note"],
             "after": [],
             "after_note": "The phrase is no longer in the answer."},
        ],
        "notes": ["The answer cites five provisions where the official appendix expects one (Article 50(4)); "
                  "Article 2(10) and Article 3(3) and (11) are stated but not cited."],
    },
    {
        "id": "Q95", "part": "A", "title": "\u201cArea\u201d and \u201cuse case\u201d under Article 6(2)",
        "verdict": "Correct overall, 3 precision points", "kind": "correct",
        "expected": "Article 6.2, Annex III",
        "found": "Use-case definition inapplicable to area 2; headings of areas 4 and 5 abridged",
        "points": [
            {"label": "Use-case definition applicable to area 2",
             "before": ("PRECISION", "Review: \u201cthe specific lettered entries under each area\u201d "
                                     "fails for area 2 (critical infrastructure), which has no lettered "
                                     "points; its heading states the use."),
             "after": ["in seven of the areas the uses are set out as lettered points, and for critical "
                       "infrastructure the heading itself states the use"]},
            {"label": "Heading of area 4",
             "before": ("PRECISION", "Review: area 4 is named \u201cemployment and workers "
                                     "management\u201d; the heading reads \u201cEmployment, workers' "
                                     "management and access to self-employment\u201d."),
             "after": ["employment, workers' management and access to self-employment"]},
            {"label": "Heading of area 5",
             "before": ("PRECISION", "Review: area 5 is compressed."),
             "after": ["access to and enjoyment of essential private services and essential public services "
                       "and benefits"]},
        ],
        "notes": ["The review also observed that Article 6(2) uses neither term (\u201careas\u201d derives "
                  "from the Annex III heading, \u201cuse cases\u201d from Articles 6(3)(d) and 7(1)) and "
                  "treated the question as answerable. The 29 September sentence on Article 7(1) is "
                  "withdrawn; the citations are the expected Article 6(2) and Annex III."],
    },
    {
        "id": "Q104", "part": "A", "title": "Purpose and use of Annex X",
        "verdict": "Wrong in part, borderline", "kind": "wrong",
        "expected": "Article 111.1, Annex X",
        "found": "Annex X described as establishing the transitional regime; Article 5 reservation omitted",
        "points": [
            {"label": "Annex X as the list relied on by Article 111(1)",
             "before": ("DEFECT", "Review: \u201cIts function is to set a transitional regime under "
                                  "Article 111(1)\u201d is incorrect. Annex X sets nothing; Article 111(1) "
                                  "lays down the transitional rule by reference to the acts Annex X "
                                  "lists."),
             "after": ["It imposes no obligation itself; Article 111(1) uses it to identify the AI systems "
                       "that receive a transitional rule."]},
            {"label": "Reservation of Article 5",
             "before": ("DEFECT", "Review: Article 111(1) applies without prejudice to Article 5, whose "
                                  "prohibitions have applied since 2 February 2025; read alone, the answer "
                                  "places the whole Regulation, prohibitions included, on the 2030 "
                                  "timetable."),
             "after": ["this is without prejudice to Article 5, whose prohibitions have applied to them "
                       "since 2 February 2025 under Article 113, third paragraph, point (a)"]},
        ],
        "notes": ["As in the review's corrected answer, all seven headings of Annex X are now named; the "
                  "29 September answer named three."],
    },
    {
        "id": "Q6 (Case A)", "part": "B", "title": "Minimal-risk AI systems",
        "verdict": "Correct, 1 precision point", "kind": "correct",
        "found": "Product limb of Article 6(1) and third-party conformity assessment condition omitted",
        "points": [
            {"label": "Both limbs of Article 6(1) and the third-party conformity assessment condition",
             "before": ("PRECISION", "Review: \u201c(as an Annex I safety component or an Annex III use "
                                     "case)\u201d omits an AI system that is itself a product covered by "
                                     "Annex I, and the condition that the product be required to undergo a "
                                     "third-party conformity assessment."),
             "after": ["(a safety component of, or itself, a product covered by the Union harmonisation "
                       "legislation listed in Annex I and required to undergo a third-party conformity "
                       "assessment, or an Annex III use case)"]},
        ],
        "notes": ["The remainder of the answer, which the review found correct, is unchanged."],
    },
    {
        "id": "Q10 (Case B)", "part": "B", "title": "Provider and deployer",
        "verdict": "Wrong in part", "kind": "wrong",
        "found": "Roles presented as mutually exclusive; conditions of Article 25(1)(a) to (c) omitted",
        "points": [
            {"label": "Provider and deployer roles are not mutually exclusive",
             "before": ("DEFECT", "Review: \u201cthe difference lies in supplying the system as opposed "
                                  "to using it\u201d presents the roles as alternatives; a party that "
                                  "develops a system and puts it into service for its own use is both its "
                                  "provider and its deployer (Article 3(11), Recital 83)."),
             "after": ["The roles are not alternatives: putting into service includes the supply of a system "
                       "for own use (Article 3(11)), so a party that develops a system and puts it into "
                       "service for its own use under its own name or trademark is both its provider and "
                       "its deployer",
                       "Recital 83 states that an operator acting in more than one role at the same time "
                       "should fulfil cumulatively all relevant obligations associated with those roles"]},
            {"label": "Article 25(1)(a): placed on the market or put into service; contractual allocation",
             "before": ("DEFECT", "Review: the answer states only \u201calready on the market\u201d and "
                                  "omits the reservation for contractual arrangements."),
             "after": ["already placed on the market or put into service, without prejudice to contractual "
                       "arrangements stipulating that the obligations are otherwise allocated"]},
            {"label": "Article 25(1)(b): the modified system must remain high-risk",
             "before": ("DEFECT", "Review: point (b) applies only where the modified system "
                                  "\u201cremains a high-risk AI system pursuant to Article 6\u201d; the "
                                  "answer omits this."),
             "after": ["in such a way that it remains a high-risk AI system pursuant to Article 6"]},
            {"label": "Article 25(1)(c): any AI system, including general-purpose, not classified as "
                      "high-risk",
             "before": ("DEFECT", "Review: point (c) concerns an AI system \u201cincluding a "
                                  "general-purpose AI system, which has not been classified as high-risk "
                                  "and has already been placed on the market or put into service\u201d; "
                                  "the answer retains only the change of purpose and its result."),
             "after": ["modifies the intended purpose of an AI system, including a general-purpose AI "
                       "system, that has not been classified as high-risk and has already been placed on "
                       "the market or put into service"]},
        ],
        "notes": ["The answer also includes general-purpose AI models in the Article 3(3) definition. One "
                  "difference from the review's corrected answer remains by design: the Article 25(1) "
                  "sentence omits the Act's words “under Article 16”. An earlier version that allocated "
                  "duties under Articles 16 and 26 failed the citation and tone criteria of an expert "
                  "re-check."],
        "note_checks": ["develops an AI system or a general-purpose AI model"],
        "note_absent": ["Article 16"],
    },
    {
        "id": "Q16 (Case C)", "part": "B", "title": "Emotion and stress monitoring of workers",
        "verdict": "Wrong in part", "kind": "wrong", "derived": True,
        "found": "Stress treated as an emotion; Annex III route and application dates omitted",
        "points": [
            {"label": "Emotion recognition: the prohibition and its sole exception",
             "before": ("MET", "Answer: states the prohibition, its three acts, the medical or safety "
                               "exception, and that improving efficiency is neither."),
             "after": ["The only Article 5(1)(f) exception is where the use of the AI system is intended to "
                       "be put in place or placed on the market for medical or safety reasons, and improving "
                       "efficiency is neither."]},
            {"label": "Stress addressed separately (Recital 18)",
             "before": ("DEFECT", "Answer: treats stress as an emotion (\u201cInferring stress and "
                                  "emotions from workers' biometric data is exactly what the ban "
                                  "targets\u201d). Recital 18 names stress neither among the emotions nor "
                                  "among the excluded physical states."),
             "after": ["Stress is separate: Recital 18 excludes physical states such as pain or fatigue "
                       "from the notion of emotions and names stress in neither list, so a system inferring "
                       "stress as a physical state may fall outside Article 5(1)(f)"]},
            {"label": "Annex III route for stress monitoring",
             "before": ("DEFECT", "Answer: does not state that, on that branch, the use is permitted only "
                                  "on the conditions following from Annex III, point 4(b), Article 6(2) and "
                                  "(3) and Article 26."),
             "after": ["a system intended to monitor and evaluate the performance and behaviour of persons "
                       "in work-related relationships is high-risk under Article 6(2) and Annex III, point "
                       "4(b), unless Article 6(3) applies, and the company must then meet the Article 26 "
                       "deployer obligations"]},
            {"label": "Application dates",
             "before": ("DEFECT", "Answer: no dates stated."),
             "after": ["Article 5(1)(f) has applied since 2 February 2025 and the obligations attaching to "
                       "a high-risk Annex III system apply from 2 August 2026"]},
        ],
        "notes": ["The review set out a correct position rather than numbered points; the points above are "
                  "its elements. The Annex III date follows the Act as adopted (section 3)."],
    },
    {
        "id": "Q17 (Case D)", "part": "B", "title": "AI safety component in robotic surgery",
        "verdict": "Wrong in part", "kind": "wrong", "derived": True,
        "found": "Device class assumed; Annex I point, MDR classification route and application date "
                 "omitted",
        "points": [
            {"label": "Conclusion conditional on third-party assessment of the robot",
             "before": ("DEFECT", "Answer: asserts \u201ca Class IIb or Class III device\u201d, which the "
                                  "question does not state."),
             "after": ["Yes, where the surgical robot itself is required to undergo a third-party "
                       "conformity assessment"]},
            {"label": "Regulation (EU) 2017/745: Annex I, Section A, point 11",
             "before": ("PARTLY MET", "Answer: refers to \u201cthe Medical Device Regulation listed in Annex "
                                      "I\u201d, without section or point."),
             "after": ["Regulation (EU) 2017/745 on medical devices is listed in Section A of Annex I at "
                       "point 11"]},
            {"label": "Classification by intended purpose; notified body for classes IIa, IIb and III",
             "before": ("DEFECT", "Answer: assumes the class, omits class IIa, and does not cite Articles "
                                  "51(1) and 52 of Regulation (EU) 2017/745."),
             "after": ["the robot's class follows its intended purpose (Article 51(1)), which the question "
                       "does not state, and a notified body takes part in the conformity assessment of "
                       "devices in classes IIa, IIb and III (Article 52(6), (4) and (3))"]},
            {"label": "Application date of Article 6(1)",
             "before": ("DEFECT", "Answer: no date stated."),
             "after": ["Article 6(1) and the corresponding obligations apply from 2 August 2027."]},
        ],
        "notes": ["The review set out a correct position rather than numbered points; the points above are "
                  "its elements. The 29 September statements on Articles 43(3), 14(4) and 72(4), requested "
                  "in the August critique, are not part of this answer; the review's corrected answer "
                  "addresses classification only. The date follows the Act as adopted (section 3)."],
    },
]

OMNIBUS_ROWS = [
    ("Q16 (Case C)", "Obligations for Annex III high-risk systems apply from 2 August 2026.",
     "Chapter III, Sections 1 to 3, apply to Annex III systems from <b>2 December 2027</b> "
     "(Article 113, third paragraph, point (c)(i), as amended)."),
    ("Q17 (Case D)", "Article 6(1) and the corresponding obligations apply from 2 August 2027.",
     "Chapter III, Sections 1 to 3, apply to Annex I systems from <b>2 August 2028</b> "
     "(Article 113, third paragraph, point (c)(ii), as amended)."),
    ("Q104", "The Article 5 prohibitions have applied since 2 February 2025.",
     "Unchanged for the prohibitions of the adopted text. The prohibitions added as Article 5(1), first "
     "subparagraph, points (ba) and (bb), and Article 5(1a) and (1b) apply from <b>2 December 2026</b> "
     "(Article 113, third paragraph, point (a), as amended)."),
    ("Q74", "The Article 50 obligations apply from 2 August 2026.",
     "Unchanged. New Article 111(4): providers of generative AI systems placed on the market before "
     "2 August 2026 must comply with Article 50(2) by <b>2 December 2026</b>."),
    ("Q6 (Case A)", "Providers and deployers remain subject to the Article 4 AI literacy obligation.",
     "Article 4 replaced: the obligation remains with providers and deployers, now to \u201ctake measures "
     "to support the development of AI literacy\u201d, without requiring any specific level of AI literacy."),
]

CSS = r"""
  :root{
    --bg:#fbfaf9; --fg:#1c1a18; --muted:#6b645d; --line:#e2ddd7; --card:#ffffff;
    --ok:#1a7f52; --ok-bg:#eaf6f0; --ok-line:#b6e0cb;
    --bad:#a8341f; --bad-bg:#fbeeea; --bad-line:#f0cec4;
    --note:#7a5c12; --note-bg:#fdf6e3; --note-line:#ecd9a3;
    --accent:#2b5c8a; --accent-bg:#eef4fa; --accent-line:#c2d8ea;
    --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  }
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]){
      --bg:#16151a; --fg:#eceaf0; --muted:#a09aa8; --line:#33303a; --card:#1e1d23;
      --ok:#5fd39b; --ok-bg:#12261d; --ok-line:#2a5a42;
      --bad:#f0907a; --bad-bg:#2a1714; --bad-line:#5e2f26;
      --note:#e0bd6a; --note-bg:#282010; --note-line:#5a4a24;
      --accent:#8ab6de; --accent-bg:#152230; --accent-line:#2e4a63;
    }
  }
  :root[data-theme="dark"]{
    --bg:#16151a; --fg:#eceaf0; --muted:#a09aa8; --line:#33303a; --card:#1e1d23;
    --ok:#5fd39b; --ok-bg:#12261d; --ok-line:#2a5a42;
    --bad:#f0907a; --bad-bg:#2a1714; --bad-line:#5e2f26;
    --note:#e0bd6a; --note-bg:#282010; --note-line:#5a4a24;
    --accent:#8ab6de; --accent-bg:#152230; --accent-line:#2e4a63;
  }
  *{box-sizing:border-box}
  body{background:var(--bg);color:var(--fg);margin:0;
    font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
  .wrap{max-width:none;margin:0;padding:2.5rem 2rem 5rem}
  h1{font-size:1.75rem;line-height:1.25;margin:.2rem 0 .5rem;letter-spacing:-.02em}
  h2{font-size:1.15rem;margin:2.75rem 0 .75rem;letter-spacing:-.01em}
  h3{font-size:1rem;margin:0}
  h3.sub{margin:1.2rem 0 .2rem}
  p{margin:.6rem 0}
  .lede{color:var(--muted);font-size:1rem;margin:.35rem 0 0}
  header{border-bottom:1px solid var(--line);padding-bottom:1.25rem;margin-bottom:1.25rem}
  .scores{display:flex;flex-wrap:wrap;gap:.75rem;margin-top:1.1rem}
  .score{flex:1 1 9rem;border:1px solid var(--line);border-radius:.7rem;padding:.75rem .9rem;background:var(--card)}
  .score .lab{font-size:.68rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:700}
  .score .val{font-size:1.3rem;font-weight:700;margin-top:.15rem;font-variant-numeric:tabular-nums}
  .score .sub2{font-size:.78rem;color:var(--muted);margin-top:.1rem}
  .val.ok{color:var(--ok)}
  table{width:100%;border-collapse:collapse;font-size:.85rem;margin:.5rem 0 0}
  th,td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid var(--line);vertical-align:top}
  th{font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
  td.num .hand{color:var(--muted)}
  tr.legend td{font-size:.7rem;color:var(--muted);padding-top:.2rem;padding-bottom:.2rem}
  td.ok{color:var(--ok);font-weight:700;white-space:nowrap}
  td.nw{white-space:nowrap}
  .scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
  ol.steps,ul.steps{margin:.5rem 0 0;padding-left:1.3rem} ol.steps li,ul.steps li{margin:.4rem 0}
  .part{font-size:1.05rem;margin:1.6rem 0 .9rem;color:var(--accent);text-transform:uppercase;letter-spacing:.05em}
  .case{border:1px solid var(--line);border-radius:.9rem;background:var(--card);padding:1.4rem;margin:1.1rem 0}
  .case-head{display:flex;flex-wrap:wrap;gap:.6rem;align-items:baseline;justify-content:space-between;
    border-bottom:1px solid var(--line);padding-bottom:.8rem;margin-bottom:1rem}
  .tag{font-family:var(--mono);font-size:.7rem;font-weight:700;padding:.15rem .5rem;border-radius:.35rem;
    border:1px solid var(--accent-line);background:var(--accent-bg);color:var(--accent)}
  .pill{font-size:.75rem;font-weight:700;padding:.2rem .6rem;border-radius:999px;white-space:nowrap}
  .pill.ok{color:var(--ok);background:var(--ok-bg);border:1px solid var(--ok-line)}
  .pill.bad{color:var(--bad);background:var(--bad-bg);border:1px solid var(--bad-line)}
  .pill.warn{color:var(--note);background:var(--note-bg);border:1px solid var(--note-line)}
  .pills{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center}
  .q{font-weight:600;margin:0 0 .9rem}
  .cols{display:grid;grid-template-columns:1fr;gap:.9rem}
  @media(min-width:48rem){.cols{grid-template-columns:1fr 1fr}}
  .panel{border-radius:.6rem;padding:.85rem 1rem;font-size:.83rem}
  .panel.before{border:1px solid var(--bad-line);background:var(--bad-bg)}
  .panel.after{border:1px solid var(--ok-line);background:var(--ok-bg)}
  .panel .hd{font-weight:700;font-size:.75rem;text-transform:uppercase;letter-spacing:.06em;margin-bottom:.5rem}
  .panel.before .hd{color:var(--bad)} .panel.after .hd{color:var(--ok)}
  .answer{border:1px solid var(--line);border-radius:.6rem;background:var(--card);
    padding:.9rem 1rem;font-size:.82rem;line-height:1.62;margin:.35rem 0 0}
  .meta{font-family:var(--mono);font-size:.72rem;color:var(--muted);margin-top:.45rem;
    display:flex;flex-wrap:wrap;gap:.3rem .8rem;align-items:baseline;padding-top:.35rem;border-top:1px dashed var(--line)}
  .meta strong{font-family:inherit;font-weight:700;color:var(--fg);text-transform:uppercase;font-size:.65rem;letter-spacing:.04em;margin-right:.2rem}
  .refs{font-family:var(--mono);font-size:.72rem;color:var(--fg)}
  .req{font-family:var(--mono);font-size:.72rem;color:var(--accent)}
  .pt{margin:.5rem 0;line-height:1.5}
  .pt b{font-weight:600}
  .tg{display:inline-block;font-family:var(--mono);font-size:.58rem;font-weight:700;letter-spacing:.03em;
    padding:.05rem .32rem;border-radius:.25rem;margin-right:.35rem;vertical-align:.08em}
  .tg.def{color:var(--bad);border:1px solid var(--bad-line);background:var(--card)}
  .tg.prc{color:var(--note);border:1px solid var(--note-line);background:var(--card)}
  .tg.part{color:var(--note);border:1px solid var(--note-line);background:var(--card)}
  .tg.met{color:var(--ok);border:1px solid var(--ok-line);background:var(--card)}
  .tg.fix{color:var(--ok);border:1px solid var(--ok-line);background:var(--card)}
  .tg.rem{color:var(--ok);border:1px dashed var(--ok);background:var(--card)}
  ul.steps ul{margin:.3rem 0 .2rem;padding-left:1.1rem;list-style:circle} ul.steps ul li{margin:.25rem 0}
  .remark{color:var(--muted);font-style:italic;font-size:.8rem;display:block;margin-top:.15rem}
  .remark.quote{font-style:normal;color:var(--fg)}
  .note{font-size:.8rem;color:var(--muted);margin:.8rem 0 0;padding-top:.6rem;border-top:1px dashed var(--line)}
  .note strong{color:var(--fg)}
  .update{border:1px solid var(--accent-line);background:var(--accent-bg);border-radius:.9rem;padding:1.1rem 1.25rem;margin:1.3rem 0}
  .update h2{margin:0 0 .6rem}
  .update table{background:var(--card);border-radius:.5rem}
  .update h3.sub{margin:1.1rem 0 .2rem}
  @page{size:A4;margin:13mm 12mm 15mm;
    @bottom-left{content:"Antifragile AI \00B7  Regenold EU AI Act Q&A Challenge \00B7  expert review appendix \00B7  26 October 2026";font:7.5pt "Segoe UI",Arial,sans-serif;color:#6b645d}
    @bottom-right{content:"Page " counter(page) " of " counter(pages);font:7.5pt "Segoe UI",Arial,sans-serif;color:#6b645d}}
  @media print{
    html{font-size:11.5px;-webkit-print-color-adjust:exact;print-color-adjust:exact}
    body{font-size:11.5px;background:#fff}
    .wrap{padding:0}
    header{padding-bottom:.9rem;margin-bottom:.9rem}
    .cols{grid-template-columns:1fr 1fr;gap:.6rem}
    thead{display:table-header-group}
    tr,.panel,.case-head,.score{break-inside:avoid}
    h2,h3,.case-head,.q,.part{break-after:avoid}
    .case{break-before:page;break-inside:auto;-webkit-box-decoration-break:clone;box-decoration-break:clone;padding:1rem;margin:0}
    .part + .case{break-before:auto}
    .update{break-inside:auto;padding:.8rem 1rem;margin:.9rem 0}
    h2.sec-method,h2.sec-open{break-before:page;margin-top:0!important}
    h2.sec-cards + .part{margin-top:.4rem}
    #part-4b{break-before:page;margin-top:0!important}
    .panel{padding:.6rem .75rem}
    .answer{padding:.55rem .7rem;line-height:1.5}
    .pt{margin:.35rem 0}
    h2{margin-top:1.6rem}
    th,td{padding:.32rem .5rem}
  }
"""


def tag_class(tag: str) -> str:
    return {"DEFECT": "def", "PRECISION": "prc", "PARTLY MET": "part", "MET": "met"}[tag]


def check_and_collect(cases: list[dict], live: dict[str, dict]) -> int:
    """Assert every quote is in the live answer and every absence is absent."""
    total = 0
    for case in cases:
        answer = norm(live[case["id"]]["answer"])
        for point in case["points"]:
            total += 1
            for quote in point["after"]:
                if norm(quote) not in answer:
                    raise SystemExit(f"{case['id']}: quote not in live answer: {quote[:80]!r}")
            for phrase in point.get("absent", []):
                if norm(phrase).lower() in answer.lower():
                    raise SystemExit(f"{case['id']}: phrase still present: {phrase!r}")
            if not point["after"] and not point.get("absent"):
                raise SystemExit(f"{case['id']}: point {point['label']!r} has no evidence")
        # A card note that describes the answer's wording is checked the same way.
        for phrase in case.get("note_checks", []):
            if norm(phrase) not in answer:
                raise SystemExit(f"{case['id']}: note no longer matches the answer: {phrase[:80]!r}")
        for phrase in case.get("note_absent", []):
            if norm(phrase).lower() in answer.lower():
                raise SystemExit(f"{case['id']}: note says {phrase!r} is absent, but it is present")
    return total


def render_case(case: dict, before: dict, after: dict) -> str:
    n = len(case["points"])
    noun = "point" if n == 1 else "points"
    verdict_pill = "warn" if case["kind"] == "correct" else "bad"
    expected = case.get("expected")
    exp_html = (f'<span class="req"><strong>Expected (official appendix):</strong> {E(expected)}</span>'
                if expected else "")
    head = case["id"] if "Case" not in case["id"] else case["id"].replace(" (", " \u00b7 ").rstrip(")")
    verdict = case["verdict"][0].lower() + case["verdict"][1:]
    out = [f'<article class="case" id="case-{re.sub(r"[^a-z0-9]+", "-", case["id"].lower()).strip("-")}">',
           '  <div class="case-head">',
           f'    <div><span class="tag">{E(head)}</span> <h3 style="display:inline">{E(case["title"])}</h3></div>',
           f'    <div class="pills"><span class="pill {verdict_pill}">Review: {E(verdict)}</span>'
           f'<span class="pill ok">{DAY_SHORT}: {n} of {n} {noun} resolved</span></div>',
           '  </div>',
           f'  <p class="q">\u201c{E(after["question"])}\u201d</p>',
           '  <div class="cols">',
           '    <div class="panel before">',
           '      <div class="hd">29 September answer (as reviewed)</div>',
           f'      <div class="answer">{E(before["answer"])}</div>',
           f'      <div class="meta"><span class="refs"><strong>Citations:</strong> {E(", ".join(before["citations"]))}</span>{exp_html}</div>',
           '    </div>',
           '    <div class="panel after">',
           f'      <div class="hd">{DAY} answer (production)</div>',
           f'      <div class="answer">{E(after["answer"])}</div>',
           f'      <div class="meta"><span class="refs"><strong>Citations:</strong> {E(", ".join(after["references"]))}</span>{exp_html}</div>',
           '    </div>',
           '  </div>',
           '  <div class="cols" style="margin-top:.85rem">',
           '    <div class="panel before">',
           f'      <div class="hd">Expert review, October 2026: {E(verdict)}</div>']
    for point in case["points"]:
        tag, remark = point["before"]
        out.append(f'      <div class="pt"><span class="tg {tag_class(tag)}">{tag}</span><b>{E(point["label"])}</b>'
                   f'<span class="remark">{E(remark)}</span></div>')
    out += ['    </div>',
            '    <div class="panel after">',
            f'      <div class="hd">{DAY} answer: {n} of {n} {noun} resolved</div>']
    for point in case["points"]:
        quotes = " \u2026 ".join(f"\u201c{E(q)}\u201d" for q in point["after"])
        extra = f'<span class="remark">{E(point["after_note"])}</span>' if point.get("after_note") else ""
        body = f'<span class="remark quote">{quotes}</span>' if quotes else ""
        after_tag = point.get("after_tag", "ADDRESSED")
        cls = "fix" if after_tag == "ADDRESSED" else "rem"
        out.append(f'      <div class="pt"><span class="tg {cls}">{after_tag}</span><b>{E(point["label"])}</b>'
                   f'{body}{extra}</div>')
    out += ['    </div>', '  </div>']
    for note in case.get("notes", []):
        out.append(f'  <p class="note"><strong>Note.</strong> {E(note)}</p>')
    out.append('</article>')
    return "\n".join(out)


def heads_equal(refs: list[str], expected: str) -> tuple[bool, bool]:
    """(every expected reference cited, cited list equals the expected list) as sets."""
    exp = {e.strip() for e in expected.split(",")}
    got = set(refs)
    return exp <= got, exp == got


FAMILY_TO_ID = {
    "Q45": "Q45", "Q96": "Q96", "Q17": "Q17", "Q74": "Q74", "Q95": "Q95", "Q104": "Q104",
    "Q6": "Q6 (Case A)", "Q10": "Q10 (Case B)", "Q16": "Q16 (Case C)", "CASE_D": "Q17 (Case D)",
}


def _last_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", norm(text))[-1]


def pinned_families(live_rows: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Which reviewed questions reach a verdict the R467 rules pin (whole text, declared citations).

    Mirrors ``_pinned_verdict_names`` in ``app/routes/regenold.py``: the statutory
    verdicts plus ``role_difference`` (and ``reclassification_scope``, which none of
    the ten reach).
    """
    os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")
    sys.path.insert(0, str(REPO))
    from app.engines._graph_rag_impl import _detect_role_difference_inquiry  # noqa: PLC0415
    from app.engines.statutory_precision import (  # noqa: PLC0415
        STATUTORY_VERDICT_NAMES,
        curated_statutory_verdict,
    )

    pinned, unpinned = [], []
    for case in CASES:
        question = live_rows[case["id"]]["question"]
        verdict = curated_statutory_verdict(question)
        if (verdict and verdict["name"] in STATUTORY_VERDICT_NAMES) or _detect_role_difference_inquiry(question):
            pinned.append(case["id"])
        else:
            unpinned.append(case["id"])
    return pinned, unpinned


def statute_facts() -> int:
    """Run the statute check; every passage the answers rely on must be found."""
    sys.path.insert(0, str(R467))
    import statute_phrase_check as spc  # noqa: PLC0415

    missing = [(w, p) for case, items in spc.CHECKS.items() for w, p in items
               if spc.norm(p) not in (spc.MDR if "MDR" in case else spc.AI)]
    if missing:
        raise SystemExit(f"statutory passages not found verbatim: {missing}")
    return sum(len(items) for items in spc.CHECKS.values())




def rephrasing_facts(live_rows: dict[str, dict], then_rows: dict[str, dict]) -> dict:
    """The 30 remediation rephrasings on 23 October and now, classified mechanically.

    A rephrasing is "statutory" when its live answer is byte-identical to an offline
    replay with no model reachable. A statutory answer is then compared with the
    reviewed question's live answer: identical, shortened (a strict prefix: the cap
    problem the second round fixed), reworded (same closing sentence, i.e. the same
    verdict framed for the question) or another statutory answer.
    """
    def classify(path: Path, reviewed_rows: dict[str, dict]) -> tuple[dict, dict]:
        run = load(path)
        if any("error" in r for r in run["rows"]):
            raise SystemExit(f"{path.name} has errors")
        statutory = [r for r in run["rows"] if r.get("offline_identical")]
        counts = {"identical": 0, "shortened": 0, "reworded": 0, "other": 0}
        for row in statutory:
            reviewed = norm(reviewed_rows[FAMILY_TO_ID[row["family"]]]["answer"])
            answer = norm(row["answer"])
            if answer == reviewed:
                counts["identical"] += 1
            elif reviewed.startswith(answer):
                counts["shortened"] += 1
            elif _last_sentence(answer) == _last_sentence(reviewed):
                counts["reworded"] += 1
            else:
                counts["other"] += 1
        return ({"n": len(run["rows"]), "commit": run["commit"], "statutory": len(statutory),
                 "model": len(run["rows"]) - len(statutory), "ids": {r["id"] for r in statutory}, **counts}, run)

    then, then_run = classify(R467 / "paraphrase_rerun_r467d.json", then_rows)
    now, now_run = classify(HERE / "paraphrase_rerun.json", live_rows)
    # "Answered by the language model": a non-statutory answer must differ from the 23 October
    # run's answer to the same question, i.e. be generated, not stored text.
    previous = {r["id"]: r["answer"] for r in then_run["rows"]}
    stored = [r["id"] for r in now_run["rows"] if not r.get("offline_identical") and r["answer"] == previous[r["id"]]]
    if stored:
        raise SystemExit(f"rephrasings answered identically in two runs, not by the model: {stored}")
    return {"then": then, "now": now}


def offline_facts(live: dict) -> int:
    """The ten live answers must equal the offline replay of the same build."""
    replay = load(HERE / "offline_wire_replay.json")
    ids = {r["id"] for r in live["rows"]}
    same = [r for r in replay if r["answer_identical"] and r["references_identical"]]
    if {r["id"] for r in replay} != ids or len(same) != len(ids):
        raise SystemExit("the offline replay does not reproduce every live answer; update section 5")
    return len(same)


# ---------------------------------------------------------------------------
# The 20 held-out rephrasings, in three runs: before the second round, on 23 October
# and now. The judge grades the answer text only; ``HELDOUT_NOTES`` are the findings a
# hand check adds (a grade that differs from the judge's, or a citation the judge does
# not see). ``check`` is asserted against the run file, so a re-run that no longer shows
# the finding fails the build.
# ---------------------------------------------------------------------------
HELDOUT_RUNS = (
    ("pre", "Before the second round", R467 / "heldout_prefix.json", R467 / "heldout_prefix_judged.json"),
    ("oct", PREV_DAY, R467 / "heldout_r467c.json", R467 / "heldout_r467c_judged.json"),
    ("now", DAY, HERE / "heldout.json", HERE / "heldout_judged.json"),
)
_NEW_AREA_LEAD = "Yes, but only within the limits Article 7 sets."

HELDOUT_NOTES: list[dict] = [
    # -- grades the hand check sets differently from the judge ------------------
    {"run": "pre", "id": "H17_a", "hand": "incorrect",
     "check": lambda r: r["answer"].startswith(_NEW_AREA_LEAD) and r["judgement"]["verdict"] == "correct"},
    {"run": "pre", "id": "H16_b", "hand": "incorrect",
     "check": lambda r: r["judgement"]["verdict"] == "partly" and "or the safety purpose is not genuine" in r["answer"]},
    {"run": "oct", "id": "H17_a", "hand": "incorrect",
     "check": lambda r: r["answer"].startswith(_NEW_AREA_LEAD) and r["judgement"]["verdict"] == "correct"},
    {"run": "oct", "id": "H96_a", "hand": "correct",
     "check": lambda r: r["judgement"]["verdict"] == "incorrect"
     and "where it is, or is a safety component of, a medical device" in r["answer"]},
    {"run": "oct", "id": "H17_b", "hand": "partly",
     "check": lambda r: r["judgement"]["verdict"] == "correct" and "97(6)" in " ".join(r["judgement"]["omissions"])},
    # -- citations, which the judge does not see ---------------------------------
    {"run": "pre", "id": "HD_a", "cite": True, "check": lambda r: "Annex I.20" in r["references"]},
    {"run": "pre", "id": "H96_b", "cite": True, "check": lambda r: r["references"] == ["Annex III.5.a"]},
    {"run": "pre", "id": "HD_b", "cite": True,
     "check": lambda r: "Annex VIII" in r["references"] and "Annex VIII" in r["answer"]},
    {"run": "pre", "id": "H104_b", "cite": True,
     "check": lambda r: "Article 2" in r["references"] and not re.search(r"Article 2\b", r["answer"])},
    {"run": "pre", "id": "H6_b", "cite": True, "check": lambda r: "Article 53" in r["references"]},
    {"run": "pre", "id": "H104_a", "cite": True, "check": lambda r: "Annex III" in r["references"]},
    {"run": "oct", "id": "HD_a", "cite": True, "check": lambda r: "Annex I.20" in r["references"]},
    {"run": "oct", "id": "H6_b", "cite": True,
     "check": lambda r: "Article 16" in r["references"] and "Article 16" not in r["answer"]},
    {"run": "oct", "id": "H104_a", "cite": True, "check": lambda r: "Annex III" in r["references"]},
    {"run": "oct", "id": "H104_b", "cite": True,
     "check": lambda r: "Article 2" in r["references"] and not re.search(r"Article 2\b", r["answer"])},
    {"run": "now", "id": "H6_b", "cite": True,
     "check": lambda r: "Article 26" in r["references"] and "Article 26" not in r["answer"]},
    # Fatigue is a physical state outside Article 5(1)(f) whatever the purpose (Recital 18); the answer
    # makes the conclusion depend on the purpose, as the earlier answer did (see ``pre`` H16_b).
    {"run": "now", "id": "H16_b", "hand": "partly",
     "check": lambda r: r["judgement"]["verdict"] == "correct"
     and "provided safety is the system's intended purpose" in r["answer"]},
]

#: A held-out row answered neither by a statutory verdict nor by the language model: a
#: stored summary, byte-identical in every live run that shows it.
STORED_SUMMARY_IDS = {"H10_a"}
_STORED_SUMMARY_LEAD = "Article 3 defines 68 terms used in the Regulation"

#: The rows that exposed the gaps (the seven failures of the 23 October run). ``then`` is what
#: that run shows, asserted by ``then_check`` on the run; the current column is read from the
#: current run, never written by hand.
GAP_ROWS: list[dict] = [
    {"id": "H17_a", "topic": "Whether a delegated act can add a brand-new area to Annex III",
     "then": "Statutory answer, which opened “Yes, but only within the limits Article 7 sets.”",
     "then_check": lambda r: r["route"] == "statutory" and r["answer"].startswith(_NEW_AREA_LEAD),
     "now": ["No: Article 7(1) empowers the Commission", "so a delegated act cannot add a new area"]},
    {"id": "H74_a", "topic": "Labelling AI-generated backing vocals on an album (Q74)",
     "then": "Language model; took the asker as a deployer and the work as evidently artistic",
     "then_check": lambda r: r["route"] == "model" and "professional activity" in r["answer"]
     and "evidently artistic" in r["answer"] and "liner notes" in r["answer"],
     "now": ["only where the use is not in the course of a personal non-professional activity",
             "where it forms part of an evidently artistic, creative, satirical, fictional or analogous work"]},
    {"id": "H16_a", "topic": "Webcams detecting “frustrated or stressed” call-centre staff (Q16)",
     "then": "Language model; treated stress as an emotion",
     "then_check": lambda r: r["route"] == "model" and "frustration or stress" in r["answer"],
     "now": ["Stress is separate: Recital 18 excludes physical states such as pain or fatigue from the notion of "
             "emotions and names stress in neither list"]},
    {"id": "HD_a", "topic": "An AI module controlling a surgical robot's movements (Case D)",
     "then": "Language model; assumed a device class and cited Annex I, point 20",
     "then_check": lambda r: r["route"] == "model" and "Class IIb or Class III" in r["answer"]
     and "Annex I.20" in r["references"],
     "now": ["Yes, where the surgical robot itself is required to undergo a third-party conformity assessment",
             "Under that Regulation the robot's class follows its intended purpose (Article 51(1)), which the "
             "question does not state"]},
    {"id": "H45_a", "topic": "What goes into the instructions for use (Q45)",
     "then": "Language model; dropped the qualifiers of Article 13(3) and abridged Article 13(2)",
     "then_check": lambda r: r["route"] == "model" and "Article 13(2)" in r["answer"]
     and "relevant, accessible and comprehensible" not in r["answer"] and "where applicable" not in r["answer"],
     "now": ["The Article 13(3) list is a minimum, and the items qualified by where applicable, when appropriate "
             "or if any are required only where that condition is met."]},
    {"id": "H96_a", "topic": "Annex III sectors and a clinical decision-support system (Q96)",
     "then": "Language model; abridged the headings of areas 4 and 5",
     "then_check": lambda r: r["route"] == "model" and "employment and workers' management" in r["answer"],
     "now": ["A system used in clinical care can still be high-risk under Article 6(1), outside Annex III",
             "(Annex I, Section A, points 11 and 12)"]},
    {"id": "H10_a", "topic": "How the Act distinguishes a provider from a deployer (Q10)",
     "then": "Stored summary of Article 3 (68 definitions, nine named)",
     "then_check": lambda r: r["route"] == "stored" and r["judgement"]["verdict"] == "incorrect"
     and "Article 3 defines 68 terms" in r["answer"],
     "now": ["The roles are not alternatives", "is both its provider and its deployer"]},
]

#: The policing row of the same table: the Annex III amendment question that names place-based tools
#: (R470's development row N17_t2). ``then`` is the recorded answer of the system before that correction.
_ART5_PREFIX = ("Risk assessment of natural persons based solely on profiling or personality traits is "
                "prohibited under Article 5(1)(d).")


def _route(row: dict) -> str:
    if row["offline_identical"]:
        return "statutory"
    if row["id"] in STORED_SUMMARY_IDS and row["answer"].startswith(_STORED_SUMMARY_LEAD):
        return "stored"
    return "model"


def heldout_runs() -> dict[str, dict[str, dict]]:
    """Each run's rows, graded, with the route that answered them."""
    runs: dict[str, dict[str, dict]] = {}
    for key, _label, raw_path, judged_path in HELDOUT_RUNS:
        raw, judged = load(raw_path), load(judged_path)
        if any("offline_identical" not in r for r in raw["rows"]):
            raise SystemExit(f"{raw_path.name} is missing its offline classification")
        bad = {v for v in judged["counts"] if v not in ("correct", "partly", "incorrect")}
        if bad:
            raise SystemExit(f"{judged_path.name}: held-out judgements incomplete: {bad}")
        offline = {r["id"]: r["offline_identical"] for r in raw["rows"]}
        runs[key] = {r["id"]: {**r, "offline_identical": offline[r["id"]]} for r in judged["rows"]}
        for row in runs[key].values():
            row["route"] = _route(row)
    for rid in STORED_SUMMARY_IDS:
        shown = {run: runs[run][rid]["answer"] for run in runs if runs[run][rid]["route"] == "stored"}
        if len(set(shown.values())) > 1:
            raise SystemExit(f"{rid} is not the same stored summary in every run that shows it")
    return runs


def heldout_facts(runs: dict[str, dict[str, dict]]) -> dict:
    """The held-out rephrasings in three runs, with the judge's grades and the hand check."""
    for note in HELDOUT_NOTES:
        if not note["check"](runs[note["run"]][note["id"]]):
            raise SystemExit(f"held-out finding no longer holds: {note['run']} {note['id']}")
    for gap in GAP_ROWS:
        if not gap["then_check"](runs["oct"][gap["id"]]):
            raise SystemExit(f"{gap['id']}: the 23 October run no longer shows what the gap table says")

    def grades(run: str, kinds: tuple[str, ...], hand: bool) -> tuple[int, int, int]:
        override = {n["id"]: n["hand"] for n in HELDOUT_NOTES if n["run"] == run and "hand" in n}
        out = {"correct": 0, "partly": 0, "incorrect": 0}
        for rid, row in runs[run].items():
            if row["route"] in kinds:
                verdict = row["judgement"]["verdict"]
                out[override.get(rid, verdict) if hand else verdict] += 1
        return out["correct"], out["partly"], out["incorrect"]

    def cell(run: str, kinds: tuple[str, ...]) -> str:
        n = sum(1 for row in runs[run].values() if row["route"] in kinds)
        if not n:
            return "<td class='num'>0</td>"
        judge, hand = grades(run, kinds, False), grades(run, kinds, True)
        text = " / ".join(map(str, judge))
        if judge != hand:
            text += f" <span class='hand'>[{' / '.join(map(str, hand))}]</span>"
        return f"<td class='num'>{n} · {text}</td>"

    cols = [key for key, *_ in HELDOUT_RUNS]
    n_rows = len(runs["now"])
    rows = ["    <tr class='legend'><td></td>"
            + "".join("<td class='num'>number · correct / partly / incorrect</td>" for _ in cols) + "</tr>"]
    for kinds, label in ((("statutory",), "Answered by a statutory answer"),
                         (("model",), "Answered by the language model"),
                         (("stored",), "Answered from a stored summary"),
                         (("statutory", "model", "stored"), f"All {n_rows}")):
        rows.append(f"    <tr><td>{label}</td>" + "".join(cell(run, kinds) for run in cols) + "</tr>")
    cites = {run: [n for n in HELDOUT_NOTES if n["run"] == run and n.get("cite")] for run in cols}
    rows.append("    <tr><td>Answers citing a provision that does not fit the question (hand check)</td>"
                + "".join(f"<td class='num'>{len(cites[run])}</td>" for run in cols) + "</tr>")
    return {
        "n": n_rows,
        "judge_label": {"claude-sonnet-5": "Claude Sonnet 5"}.get(
            load(HELDOUT_RUNS[-1][3])["judge_model"], load(HELDOUT_RUNS[-1][3])["judge_model"]),
        "table": "\n".join(rows),
        "heads": [label for _, label, *_ in HELDOUT_RUNS],
        "commits": {key: load(raw)["commit"] for key, _l, raw, _j in HELDOUT_RUNS},
        "count": {run: {k: sum(1 for r in runs[run].values() if r["route"] == k)
                        for k in ("statutory", "model", "stored")} for run in cols},
        "grades": grades,
    }


def gap_table(runs: dict[str, dict[str, dict]], pol: dict[str, dict]) -> str:
    """The rows that exposed the gaps: what the 23 October run did, and the current answer's own words."""
    label = {"statutory": "Statutory answer", "model": "Language model", "stored": "Stored summary"}
    out = []
    for gap in GAP_ROWS:
        now = runs["now"][gap["id"]]
        answer = norm(now["answer"])
        for fragment in gap["now"]:
            if norm(fragment) not in answer:
                raise SystemExit(f"{gap['id']}: quote not in the current answer: {fragment[:80]!r}")
        quotes = " … ".join(f"“{E(q)}”" for q in gap["now"])
        out.append(f"<tr><td>{E(gap['topic'])}</td><td>{E(gap['then'])}</td>"
                   f"<td>{label[now['route']]}: {quotes}</td></tr>")
    before = next(r for r in load(R470 / "pairs.json")["rows"] if r["id"] == "N17_t2")["A"]
    after = pol["amend_place_tools"]["answer"]
    if not before.startswith(_ART5_PREFIX) or not after.startswith(_NEW_AREA_LEAD):
        raise SystemExit("the policing row no longer reads as the appendix says")
    out.append("<tr><td>Whether place-based predictive policing tools could be added to Annex III by delegated act"
               f"</td><td>Opened with “{E(_ART5_PREFIX)}”, though the question excludes individuals</td>"
               f"<td>Statutory answer: opens “{E(_NEW_AREA_LEAD)}”, without the Article 5(1)(d) sentence"
               "</td></tr>")
    return "\n".join(out)


def routing(path: Path) -> dict[str, tuple[int, int]]:
    """(rows reaching a vetted answer, rows) per kind, from a routing file of R469."""
    rows = load(path)["rows"]
    return {kind: (sum(1 for r in rows if r["kind"] == kind and r["label"]),
                   sum(1 for r in rows if r["kind"] == kind)) for kind in ("target", "control")}


def update_facts() -> dict:
    """The measurements of the corrections made since 23 October, read from their records."""
    cur, live = load(R468 / "ab_curated.json"), load(R468 / "ab_live.json")
    axes_c, axes_l = cur["axes"], live["axes"]
    if (cur["n_sampled"], cur["discordant"], cur["references_changed"]) != (182, 30, 0):
        raise SystemExit("the curated-answer sample in r468 no longer reads 182 / 30 / 0")
    if (len(live["rows"]), live["discordant"]) != (111, 11):
        raise SystemExit("the model-answer sample in r468 no longer reads 111 / 11")
    longer = [r for r in cur["rows"] if r["discordant"] and len(r["B"]) > len(r["A"])]
    differing = [r for r in cur["rows"] if r["discordant"]]
    mean_a = sum(len(r["A"]) for r in differing) / len(differing)
    mean_b = sum(len(r["B"]) for r in differing) / len(differing)

    h2_main, h2_new = routing(R469 / "route_main_heldout2.json"), routing(R469 / "route_it2_heldout2.json")
    dev_main, dev_new = routing(R469 / "route_main_dev.json"), routing(R469 / "route_it2_dev.json")
    scan = [r for r in load(R470 / "scan.json")["rows"] if r["set"] == "heldout"]
    wrong_before = sum(1 for r in scan if r["kind"] == "target" and "Art. 5.1.d" in r["scan_A"])
    wrong_after = sum(1 for r in scan if r["kind"] == "target" and "Art. 5.1.d" in r["scan_B"])
    right_before = sum(1 for r in scan if r["kind"] == "control" and "Art. 5.1.d" in r["scan_A"])
    right_after = sum(1 for r in scan if r["kind"] == "control" and "Art. 5.1.d" in r["scan_B"])
    n_targets = sum(1 for r in scan if r["kind"] == "target")
    n_controls = sum(1 for r in scan if r["kind"] == "control")
    distinct = len({r["B"] for r in differing})
    expected = {"h2": (3, 6, 34, 0, 0, 14), "dev": (5, 14, 20), "pol": (6, 2, 6, 6, 12, 12), "distinct": (10,),
                "cur": (18, 0, 12, 1, 12, 17), "live": (0, 0, 9, 0, 0, 9, 6, 0, 3)}
    got = {"h2": (h2_main["target"][0], h2_new["target"][0], h2_new["target"][1],
                  h2_main["control"][0], h2_new["control"][0], h2_new["control"][1]),
           "dev": (dev_main["target"][0], dev_new["target"][0], dev_new["target"][1]),
           "distinct": (distinct,),
           "pol": (wrong_before, wrong_after, right_before, right_after, n_targets, n_controls),
           "cur": (axes_c["correctness"]["wins_B"], axes_c["correctness"]["wins_A"], axes_c["correctness"]["ties"],
                   axes_c["conciseness"]["wins_B"], axes_c["conciseness"]["wins_A"], axes_c["conciseness"]["ties"]),
           "live": (axes_l["correctness"]["wins_B"], axes_l["correctness"]["wins_A"], axes_l["correctness"]["ties"],
                    axes_l["conciseness"]["wins_B"], axes_l["conciseness"]["wins_A"], axes_l["conciseness"]["ties"],
                    axes_l["tone"]["wins_B"], axes_l["tone"]["wins_A"], axes_l["tone"]["ties"])}
    if got != expected:
        raise SystemExit(f"a measurement record no longer reads as the appendix says: {got} != {expected}")
    return {"cur": cur, "live": live, "differing": len(differing), "distinct": distinct, "longer": len(longer),
            "mean_a": mean_a, "mean_b": mean_b,
            "h2_main": h2_main, "h2_new": h2_new, "dev_main": dev_main, "dev_new": dev_new,
            "wrong_before": wrong_before, "wrong_after": wrong_after, "right_before": right_before,
            "right_after": right_after, "n_targets": n_targets, "n_controls": n_controls}


def policing_live() -> dict[str, dict]:
    """The live answers to the predictive-policing questions asked on 26 October."""
    run = load(HERE / "policing_live.json")
    if any("error" in r for r in run["rows"]):
        raise SystemExit("the live policing run has errors")
    return {r["id"]: r for r in run["rows"]}


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", norm(text))[0]


def open_items_html(runs: dict, upd: dict) -> str:
    """The limitations the 26 October run and the independent rewordings still show, each asserted."""
    now = runs["now"]
    model_ids = [rid for rid, row in now.items() if row["route"] == "model"]
    n_independent = upd["h2_new"]["target"][1]
    still_model = n_independent - upd["h2_new"]["target"][0]
    cites = [n for n in HELDOUT_NOTES if n["run"] == "now" and n.get("cite")]
    if len(cites) != 1 or cites[0]["id"] != "H6_b":
        raise SystemExit("the citation finding behind section 6 changed; update its text")
    if not now["H17_b"]["answer"].startswith(_NEW_AREA_LEAD) or not now["H17_b"]["question"].startswith("What procedure"):
        raise SystemExit("the procedure-question finding behind section 6 no longer holds")
    biopsy = next(r for r in load(R469 / "route_it2_heldout.json")["rows"] if r["id"] == "ND_t1")
    if biopsy["label"] is not None or not biopsy["question"].startswith("We're a Munich start-up"):
        raise SystemExit("the scenario-question finding behind section 6 no longer holds")
    hand = [n for n in HELDOUT_NOTES if n["run"] == "now" and "hand" in n]
    if [n["id"] for n in hand] != ["H16_b"]:
        raise SystemExit("the hand-check findings behind section 6 changed; update its text")
    items = [
        f"<i>Unfamiliar rewordings still reach the language model.</i> {still_model} of the {n_independent} independent "
        f"rewordings do (routing measured offline), and {len(model_ids)} of the {len(now)} held-out ones (live). "
        "The statutory answers are found by "
        "recognising how a question is put, and each round of recognition fits the phrasings it was shown. The "
        "language-model answers to the held-out rewordings reach no wrong conclusion on hand check, but one makes "
        "fatigue monitoring depend on its purpose where Recital 18 does not, and one cites a provision that does not "
        "fit the question (Article 26, for an AI spam filter).",
        "<i>A statutory answer keeps its opening when the question differs.</i> “What procedure applies when the "
        "Commission wants to update the list of high-risk use cases?” receives the Article 7 answer, which opens "
        "“Yes, but only within the limits Article 7 sets.” The procedure that follows is complete.",
        "<i>Scenario-style questions.</i> A long question that opens with a company description (a start-up building "
        "an AI that steers the needle during robot-assisted biopsies) is handled as a scenario and so reaches the "
        "language model, not the Case D answer. It was found in the recognition tests (routing measured offline), not "
        "in a live run.",
    ]
    return "\n".join(f"  <li>{item}</li>" for item in items)


#: The independent R469 sample judged before the operator stopped the judge: correctness
#: (statutory answer wins, loses, level) over the 10 pairs reached. See r469/CHECKPOINT.md.
R469_JUDGED = (8, 0, 2)
#: Changed answers the R469 comparison planned to judge; the judge was stopped after the first 10
#: (the 3 from the independent set, then 7 of the 18 existing questions the change moved, in file order).
R469_PAIRS = 61


def canon(text: str) -> str:
    """Words only: lower case, no punctuation, single spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text.lower())).strip()


def lead(text: str, limit: int = 150) -> str:
    """The opening words of an answer, verbatim, cut at a word boundary within ``limit`` characters."""
    words = norm(text).split(" ")
    out = words[0]
    for word in words[1:]:
        if len(out) + 1 + len(word) > limit:
            return out + "…"
        out += " " + word
    return out


def update_html(upd: dict, runs: dict, held: dict, pol: dict, stable: str, n_points: int) -> str:
    cur = upd["cur"]["axes"]
    h2m, h2n = upd["h2_main"], upd["h2_new"]
    won, lost, level = R469_JUDGED
    place = pol["place_based"]
    if not place["answer"].startswith("No. Article 5(1)(d) only prohibits"):
        raise SystemExit("the live answer to the place-based policing question no longer opens as the appendix says")
    if not runs["now"]["H17_a"]["answer"].startswith("No"):
        raise SystemExit("the live answer to the new-area question no longer opens with No")
    kinds = ("statutory", "model", "stored")
    judged_now, hand_now = held["grades"]("now", kinds, False), held["grades"]("now", kinds, True)
    judged_oct, hand_oct = held["grades"]("oct", kinds, False), held["grades"]("oct", kinds, True)
    if judged_now != (held["n"], 0, 0) or lost:
        raise SystemExit("the grades no longer read as the notes under the tables say; update them")
    return f"""<section class="update">
<h2 class="sec-update">Update of {DATE}: fixes and improvements</h2>
<p>Since {PREV_DAY} the system has been corrected in four areas. The ten reviewed questions were asked again on the
production build: {stable}, so all {n_points} review points remain addressed. Section 5 describes how each correction
was measured.</p>
<div class="scroll"><table>
  <thead><tr><th></th><th>Area</th><th>What changed</th><th>Measured</th></tr></thead>
  <tbody>
  <tr><td class="nw"><span class="tg fix">IMPROVED</span></td><td><b>Rewordings reach the statutory answers</b></td>
  <td>The statutory answers are recognised under more ways of asking the same question. Look-alike
  questions with a different correct answer are left alone.</td>
  <td>{h2n['target'][1]} independent rewordings: {h2n['target'][0]} now reach a statutory answer (before:
  {h2m['target'][0]}); none of {h2n['control'][1]} look-alikes does. The judge, stopped after
  {won + lost + level} of {R469_PAIRS} changed answers, preferred the statutory answer on correctness in {won} and found
  {level} level, none worse.</td></tr>
  <tr><td class="nw"><span class="tg fix">FIXED</span></td><td><b>Corrected answers</b></td>
  <td>Asked whether a delegated act can add a brand-new area to Annex III, the system now answers &ldquo;No&rdquo;
  (Article 7(1)); it opened &ldquo;{E(_NEW_AREA_LEAD)}&rdquo; A clinical decision-support question now gets the full
  area headings and a precise citation of the medical-device route (Annex I, Section A, points 11 and 12).</td>
  <td>Live answers below.</td></tr>
  <tr><td class="nw"><span class="tg fix">IMPROVED</span></td><td><b>Complete, readable answers</b></td>
  <td>Pre-drafted answers keep their verdict leads and statutory clauses, which a length limit used to drop, and
  lists read as sentences, not fragments.</td>
  <td>{upd['cur']['n_sampled']} questions answered by pre-drafted answers: {upd['differing']} got a changed answer
  ({upd['distinct']} distinct answers); {cur['correctness']['wins_B']} were judged more correct and
  {cur['correctness']['wins_A']} less, at some cost in length. {len(upd['live']['rows'])} model answers: the
  {upd['live']['discordant']} that contained a list now read as sentences.</td></tr>
  <tr><td class="nw"><span class="tg fix">FIXED</span></td><td><b>Predictive policing</b></td>
  <td>For forecasting where crime will occur, without assessing individuals, the system no longer opens its answer
  with an Article 5(1)(d) sentence that concerns individuals, not places (recital 42). Its stored answer, used when
  the language model is unavailable, no longer calls such forecasting high-risk under Annex III. Assessing a person's
  risk of offending is unchanged (Article 5(1)(d); Annex III, point 6(d)).</td>
  <td>{upd['n_targets'] + upd['n_controls']} independent questions: the Article 5(1)(d) rule fired wrongly on
  {upd['wrong_before']} of {upd['n_targets']} place-based questions and now on {upd['wrong_after']}; it still fires on
  all {upd['right_after']} person-based questions where it applies. No answer to these questions changed, because
  model answers already stated the limit; the change shows in the Annex III answer below. Live, {DAY}: &ldquo;Is
  place-based predictive policing prohibited under the AI Act?&rdquo; &rarr; &ldquo;{E(lead(place['answer']))}&rdquo;</td></tr>
  </tbody>
</table></div>
<h3 class="sub">Live answers, before and after</h3>
<div class="scroll"><table>
  <thead><tr><th>Reworded question</th><th>Before</th><th>{DAY}</th></tr></thead>
  <tbody>
{gap_table(runs, pol)}
  </tbody>
</table></div>
<p class="note" style="border-top:none">&ldquo;Before&rdquo; is the {PREV_DAY} run, and for the last row the system
with the policing correction switched off. All eight rows were used to develop the corrections, so they show what was
fixed, not independent evidence: {held['count']['now']['statutory']} of {held['n']} held-out rewordings now reach a
statutory answer ({PREV_DAY}: {held['count']['oct']['statutory']}), and the judge grades all {held['n']} answers
correct, {hand_now[0]} on hand check ({PREV_DAY}: {judged_oct[0]} and {hand_oct[0]}).</p>
</section>
"""


def build(no_pdf: bool, out_dir: Path) -> None:
    out_html = out_dir / f"{OUT_NAME}.html"
    out_pdf = out_dir / f"{OUT_NAME}.pdf"
    before_rows = {r["id"]: r for r in load(R467 / "sept29_answers.json")["rows"]}
    then = load(R467 / "expert_review_rerun_r467d.json")
    then_rows = {r["id"]: r for r in then["rows"]}
    live = load(HERE / "expert_review_rerun.json")
    live_rows = {r["id"]: r for r in live["rows"]}
    if any("error" in r for r in live["rows"]) or live["commit"] != live["commit_after"]:
        raise SystemExit("the live run has errors or the deployment changed during it")
    n_points = check_and_collect(CASES, live_rows)
    para = rephrasing_facts(live_rows, then_rows)
    if para["now"]["shortened"] or para["then"]["shortened"]:
        raise SystemExit("a statutory rephrasing answer is shortened; section 5 says none is")
    runs = heldout_runs()
    held = heldout_facts(runs)
    n_offline = offline_facts(live)
    n_passages = statute_facts()
    upd = update_facts()
    pol = policing_live()
    # The live held-out counts must agree with the routing record of the change that made them.
    if (held["count"]["oct"]["statutory"], held["count"]["now"]["statutory"]) != (
            upd["dev_main"]["target"][0], upd["dev_new"]["target"][0]):
        raise SystemExit("the live held-out routing no longer matches the R469 routing record")
    official = [c for c in CASES if c.get("expected")]
    b_cov = [heads_equal(before_rows[c["id"]]["citations"], c["expected"]) for c in official]
    t_cov = [heads_equal(then_rows[c["id"]]["references"], c["expected"]) for c in official]
    a_cov = [heads_equal(live_rows[c["id"]]["references"], c["expected"]) for c in official]

    # How the ten answers compare with 23 October: identical, or differing in punctuation only.
    changed = [cid for cid in live_rows if live_rows[cid]["answer"] != then_rows[cid]["answer"]]
    if any(live_rows[cid]["references"] != then_rows[cid]["references"] for cid in live_rows):
        raise SystemExit("a citation list differs from 23 October; update the text")
    if any(canon(live_rows[cid]["answer"]) != canon(then_rows[cid]["answer"]) for cid in changed):
        raise SystemExit("an answer differs from 23 October by more than punctuation; update the text")
    n_same = len(live_rows) - len(changed)
    if len(changed) == 0:
        stable = "all ten answers and their citations are identical to those of " + PREV_DAY
    else:
        stable = (f"{NUMBER_WORDS[n_same]} answers and all ten citation lists are identical to those of "
                  f"{PREV_DAY}, and {'the other differs' if len(changed) == 1 else 'the others differ'} "
                  "by punctuation only")

    n_removed = sum(p.get("after_tag") == "REMOVED" for c in CASES for p in c["points"])
    n_stated = n_points - n_removed
    tags = [p["before"][0] for c in CASES for p in c["points"]]
    n_open = sum(t in ("DEFECT", "PRECISION") for t in tags)
    n_part = tags.count("PARTLY MET")
    n_met = tags.count("MET")
    wrong = sum(c["kind"] == "wrong" for c in CASES)
    borderline = sum("borderline" in c["verdict"] for c in CASES)
    correct = len(CASES) - wrong
    b_chars = [len(before_rows[c["id"]]["answer"]) for c in CASES]
    t_chars = [len(then_rows[c["id"]]["answer"]) for c in CASES]
    a_chars = [len(live_rows[c["id"]]["answer"]) for c in CASES]
    b_refs = [len(before_rows[c["id"]]["citations"]) for c in CASES]
    t_refs = [len(then_rows[c["id"]]["references"]) for c in CASES]
    a_refs = [len(live_rows[c["id"]]["references"]) for c in CASES]
    pinned, unpinned = pinned_families(live_rows)
    unpinned_labels = [m.group(0) if (m := re.search(r"Case [A-D]", cid)) else cid for cid in unpinned]
    shorter = [c["id"] for c, b, a in zip(CASES, b_chars, a_chars, strict=True) if a < b]
    shorter_text = (f"; {' and '.join(shorter)} {'is' if len(shorter) == 1 else 'are'} shorter"
                    if shorter else "")
    lat = [live_rows[c["id"]]["latency_s"] for c in CASES]
    pt, pn = para["then"], para["now"]
    same_split = (f"The same {pt['statutory']} were answered by the statutory answers on {PREV_DAY}."
                  if pt["ids"] == pn["ids"] else
                  f"On {PREV_DAY}: {pt['statutory']} by the statutory answers and {pt['model']} by the language model.")

    parts = []
    parts.append(f"""<header>
  <h1>Regenold EU AI Act Q&amp;A Challenge: expert review appendix</h1>
  <p class="lede">Appendix to the report update of 29 September 2026 · the ten reviewed questions, re-answered
  on {DATE} · update of the appendix of {PREV_DAY}</p>
</header>
<p>The report update of 29 September 2026 set out the system's answers to ten questions: the six representative
cases from the official evaluation appendix of 25 August 2026, and Cases A–D from the Antifragile EU AI Act
Compliance Advisor. An expert review in October 2026 assessed those answers against the text of the Act. Its points
concern statutory precision rather than the choice of provision: conditions, qualifiers and exceptions the Act
attaches, facts assumed rather than stated as conditions, abridged statutory wording, and application dates. This
appendix sets each reviewed answer beside the answer the production system gives on {DATE}, assesses it against
every point the review raised, and summarises the corrections made since {PREV_DAY}. All quoted evidence is
verbatim.</p>
<div class="scores">
  <div class="score"><div class="lab">Answers reviewed</div><div class="val">{len(CASES)}</div><div class="sub2">6 official appendix cases and Cases A–D</div></div>
  <div class="score"><div class="lab">Review verdict, 29 Sep</div><div class="val">{wrong} wrong in part</div><div class="sub2">{borderline} borderline; {correct} correct, with precision points</div></div>
  <div class="score"><div class="lab">Points raised</div><div class="val">{n_points}</div><div class="sub2">On 29 Sep: {n_open} not met, {n_part} partly met, {n_met} met</div></div>
  <div class="score"><div class="lab">Resolved, {DAY_SHORT}</div><div class="val ok">{n_points} of {n_points}</div><div class="sub2">{n_stated} now stated, {n_removed} by removing the wording at issue</div></div>
</div>
""")
    parts.append(update_html(upd, runs, held, pol, stable, n_points))

    rows = []
    for c in CASES:
        n = len(c["points"])
        rows.append(f"<tr><td><b>{E(c['id'])}</b><br><span style='color:var(--muted)'>{E(c['title'])}</span></td>"
                    f"<td>{E(c['verdict'])}</td><td>{E(c['found'])}</td>"
                    f"<td class='ok'>{n} of {n}</td></tr>")
    parts.append(f"""<h2>1 · Review findings and status</h2>
<div class="scroll"><table>
  <thead><tr><th>Question</th><th>Review verdict</th><th>Points raised by the review</th><th>Resolved</th></tr></thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table></div>
<p class="note" style="border-top:none">Verdicts as stated in the review, on the 29 September answers. For Q16
(Case C) and Q17 (Case D) the review set out a correct position rather than numbered points; the points counted
are its elements.</p>

<h2 class="sec-remediation">2 · Remediation</h2>
<p>The remediation was made in the system's statutory content, not in the final language model. For each of the
ten question families the system now holds a pre-drafted statutory answer that states the conditions the review
identified in the same sentence as the provision imposing them: Article 13(3) with its qualifiers “where
applicable”, “when appropriate” and “if any”; Article 25(1) with each of its three
points; Article 50 with the marking obligation, the disclosure obligation and the manner of disclosure kept
distinct. These answers are served as drafted and are not rewritten by the language model, so a condition cannot
be paraphrased away. The summaries of Annex III, Annex X and Articles 5(1)(f), 7, 50 and 111 used elsewhere in the
system were corrected at the same time.</p>
<p>A second round on {PREV_DAY} addressed how these answers behave when the question is phrased differently. For
{NUMBER_WORDS[len(pinned)]} of the ten families (all but {E(' and '.join(unpinned_labels))}), the statutory answer is no
longer shortened when the question is read as a single request, and its citations are limited to the provisions
it states. A separate statutory answer to Article 25(1) questions (“When does a deployer become a provider
under Article 25(1)?”) now states the condition attached to each point. The Q74 answer names the medium asked
about (audio, images or video), and an image question about an art project now reaches it. Wording was corrected
against the Official Journal text in three answers: a self-developer is “also” the provider (Q74);
Recital 83 “should” and general-purpose AI models in Article 3(3) (Q10); and the items of Article
13(3)(b), introduced by “including” with items (ii), (iii) and (vi) in full (Q45). The answers still
paraphrase the Act elsewhere.</p>
<p>A third round of corrections, deployed on 25 and 26 October 2026, is summarised at the head of this appendix.
The ten reviewed answers did not need to change. Section 5 reports the rephrased questions and section 6 what remains open.</p>
<div class="scroll"><table>
  <thead><tr><th>The ten reviewed answers</th><th class="num">29 Sep</th><th class="num">{PREV_DAY.replace(' October', ' Oct')}</th><th class="num">{DAY_SHORT}</th></tr></thead>
  <tbody>
    <tr><td>Average length (characters)</td><td class="num">{sum(b_chars)/len(b_chars):,.0f}</td><td class="num">{sum(t_chars)/len(t_chars):,.0f}</td><td class="num">{sum(a_chars)/len(a_chars):,.0f}</td></tr>
    <tr><td>Citations per answer</td><td class="num">{sum(b_refs)/len(b_refs):.1f}</td><td class="num">{sum(t_refs)/len(t_refs):.1f}</td><td class="num">{sum(a_refs)/len(a_refs):.1f}</td></tr>
    <tr><td>Official appendix cases: all expected references cited</td><td class="num">{sum(x for x, _ in b_cov)} of {len(official)}</td><td class="num">{sum(x for x, _ in t_cov)} of {len(official)}</td><td class="num">{sum(x for x, _ in a_cov)} of {len(official)}</td></tr>
    <tr><td>Official appendix cases: citations identical to the expected set</td><td class="num">{sum(y for _, y in b_cov)} of {len(official)}</td><td class="num">{sum(y for _, y in t_cov)} of {len(official)}</td><td class="num">{sum(y for _, y in a_cov)} of {len(official)}</td></tr>
  </tbody>
</table></div>
<p class="note" style="border-top:none">In total the ten answers are {(sum(a_chars)/sum(b_chars)-1)*100:.0f}%
longer than on 29 September, mostly the conditions now stated in full{shorter_text}. Some of the added text
goes beyond the question, as the cards note (for example Articles 13(1) and 7(3)).</p>
""")

    if len(OMNIBUS_ROWS) != 5:
        raise SystemExit("section 3 says five statements; update its text")
    om_rows = "\n".join(f"<tr><td class='nw'><b>{E(a)}</b></td><td>{E(b)}</td><td>{c}</td></tr>"
                        for a, b, c in OMNIBUS_ROWS)
    parts.append(f"""<h2>3 · Legal basis</h2>
<p>The challenge rules define the scope as the AI Act, Regulation (EU) 2024/1689 of 13 June 2024, and the system
answers on the text as adopted. Regulation (EU) 2026/1744 (Digital Omnibus on AI), published in the Official
Journal on 24 July 2026 and in force since 27 July 2026, has since amended the Act. Five statements in the answers
below differ under the amended text. The review's corrected answers likewise apply the adopted text.</p>
<div class="scroll"><table>
  <thead><tr><th>Answer</th><th>Statement (Act as adopted)</th><th>Position under Regulation (EU) 2026/1744</th></tr></thead>
  <tbody>
{om_rows}
  </tbody>
</table></div>
<p>Not amended in substance: Articles 7, 13 and 26; Article 25(1); Article 50(2), (4) and (5); Article 97(6) as it
applies to delegated acts under Article 7(1); Article 111(1); Annexes III and X. Regulation (EU) 2017/745 remains
point 11 of Section A of Annex I.</p>
""")

    parts.append('<h2 class="sec-cards">4 · The ten answers, before and after</h2>')
    parts.append('<h3 class="part">Part 4A · Official evaluation appendix: six representative cases</h3>')
    for c in CASES:
        if c["part"] == "B" and not any(p.startswith('<h3 class="part" id="part-4b"') for p in parts):
            parts.append('<h3 class="part" id="part-4b">Part 4B · Compliance Advisor cases A–D</h3>')
        parts.append(render_case(c, before_rows[c["id"]], live_rows[c["id"]]))

    parts.append(f"""<h2 class="sec-method">5 · Method and rephrased questions</h2>
<ul class="steps">
  <li><b>Baseline.</b> The ten answers the review assessed, with their citations, as printed in the report
  update of 29 September 2026.</li>
  <li><b>Re-run.</b> One single-turn request per question, worded as in the review, to the production endpoint
  on {DATE} (build <code>{E(str(live['commit']))}</code>). Response times {min(lat):.1f}–{max(lat):.1f} s.
  Compared with {PREV_DAY}, unchanged apart from punctuation in one answer.</li>
  <li><b>Provenance.</b> Replayed with no language model reachable, the system returned identical answers and
  citations for all {NUMBER_WORDS.get(n_offline, n_offline)} questions: these are the system's statutory
  answers, not generated text. The
  language model stage (Claude Opus 5.5) was operational on the same deployment and answers questions outside
  the statutory answers.</li>
  <li><b>Assessment.</b> A point is marked addressed where the {DAY} answer states it, and removed where the
  review objected to wording the answer no longer contains ({NUMBER_WORDS.get(n_removed, n_removed)} points).
  When this document is generated, quoted evidence is verified verbatim against the live answer and removed
  wording is verified absent. The {n_passages} statutory passages the answers draw on were located verbatim in the
  Official Journal text of Regulation (EU) 2024/1689 and, for Case D, in Regulation (EU) 2017/745 (consolidated
  version of 19 July 2026); the answers quote some of them and paraphrase others.</li>
  <li><b>Scope.</b> Single-turn answers only (the challenge's easy mode). The hard mode, nine prior turns and a
  challenge to the answer, was not re-run.</li>
  <li><b>Samples for the third round.</b> Each correction was compared before and after on the same questions and
  judged by Claude Sonnet 5 in both orders. Recognition: {upd['h2_new']['target'][1]} independent rewordings and
  {upd['h2_new']['control'][1]} look-alikes, routed before and after; of the {R469_PAIRS} changed answers the judge
  reached {sum(R469_JUDGED)} (the 3 from the independent set, then 7 existing questions the change moved, in file
  order) before it was stopped. Formatting: {upd['cur']['n_sampled']} pre-drafted answers ({upd['differing']} changed,
  all judged) and {len(upd['live']['rows'])} model answers ({upd['live']['discordant']} with lists, {sum(upd['live']['axes']['correctness'][k] for k in ('wins_A', 'wins_B', 'ties'))} judged). Policing:
  {upd['n_targets'] + upd['n_controls']} independent questions routed before and after, where no answer changed, and
  one development answer, preferred after the correction. The two corrected answers in the update are shown live and
  were not judged. The independent questions were written without reference to the system's code and recorded before
  the final version of the change they test.</li>
  <li><b>Rephrasings prepared during the remediation.</b> {pn['n']} rephrasings, three per question, asked on
  the same build. The remediation was adjusted in response to some of them, so this set is not out-of-sample.
  {pn['statutory']} were answered by the statutory answers: {pn['identical']} identical to the reviewed
  answer, {pn['reworded']} the same answer worded for the question, {pn['other']} another statutory answer
  that fits the question, and none shortened. {pn['model']} were answered by the language model from retrieved
  provisions. {same_split}</li>
  <li><b>Held-out rephrasings.</b> {held['n']} further rephrasings, two per question, recorded before the second
  round. An intermediate run of this set prompted one further change on {PREV_DAY} (the area-and-use-case answer),
  and the seven answers it showed to be poor guided the third round, so neither later column is out-of-sample; the
  independent figures are at the head of this appendix. A separate model
  ({E(held['judge_label'])}) graded each answer's text against a reference position for its question family,
  condensed from the review's corrected answer or correct position: correct; partly correct (a material omission);
  incorrect (a legal error, including a fact the question does not state taken as given). The statutory answers were
  drafted from the same positions, so their grades are not independent; the language-model answers are the stronger
  test. Every answer and its citations were also checked by hand; where that differs from the judge, its grade is in
  brackets.</li>
</ul>
<div class="scroll"><table>
  <thead><tr><th>Held-out rephrasings ({held['n']})</th>{''.join(f'<th class="num">{E(h)}</th>' for h in held['heads'])}</tr></thead>
  <tbody>
{held['table']}
  </tbody>
</table></div>
<p class="note" style="border-top:none">The language-model answers are generated afresh in each run.</p>
<h2 class="sec-open">6 · Open limitations</h2>
<p>Found by the rephrased questions and not fixed.</p>
<ul class="steps">
{open_items_html(runs, upd)}
</ul>
""")

    body = "\n".join(parts)
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Regenold EU AI Act Q&amp;A Challenge: expert review appendix</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{body}
</div>
</body>
</html>
"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_html.write_text(doc, encoding="utf-8")
    print(f"wrote {out_html} ({len(doc):,} bytes); points={n_points}")
    if no_pdf:
        return
    cmd = [str(CHROME), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000",
           f"--print-to-pdf={out_pdf}", out_html.as_uri()]
    subprocess.run(cmd, check=True, timeout=180, capture_output=True)
    print(f"wrote {out_pdf} ({out_pdf.stat().st_size:,} bytes)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--out-dir", default=str(REPO / "docs" / "reports"))
    args = ap.parse_args()
    build(args.no_pdf, Path(args.out_dir))
    sys.exit(0)
