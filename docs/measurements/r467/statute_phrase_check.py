"""R467 — check the statutory wording the ten re-run answers rely on.

Each phrase is searched in the Official Journal text of Regulation (EU)
2024/1689 as adopted (``tmp/legal-audit-2026-09-29/ai-original.txt``) or, for
the medical-device classes, in Regulation (EU) 2017/745
(``mdr-current.txt``). Whitespace and typographic quotes are normalised; the
phrase must otherwise appear verbatim. Prints one line per phrase and exits 1
if any phrase is missing.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

#: The legal texts are not tracked; a worktree points at the main checkout's with the variable.
ROOT = Path(os.environ.get("REGENOLD_LEGAL_TEXT_DIR")
            or Path(__file__).resolve().parents[3] / "tmp" / "legal-audit-2026-09-29")


def norm(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).lower()


AI = norm((ROOT / "ai-original.txt").read_text(encoding="utf-8"))
MDR = norm((ROOT / "mdr-current.txt").read_text(encoding="utf-8"))

CHECKS: dict[str, list[tuple[str, str]]] = {
    "Q45": [
        ("13(1)", "sufficiently transparent to enable deployers to interpret a system's output and use it appropriately"),
        ("13(1)", "an appropriate type and degree of transparency shall be ensured"),
        ("13(2)", "in an appropriate digital format or otherwise"),
        ("13(2)", "concise, complete, correct and clear information that is relevant, accessible and comprehensible to deployers"),
        ("13(3)(a)", "the identity and the contact details of the provider and, where applicable, of its authorised representative"),
        ("13(3)(b)(ii)", "including its metrics, robustness and cybersecurity referred to in article 15"),
        ("13(3)(b)(iii)", "which may lead to risks to the health and safety or fundamental rights referred to in article 9(2)"),
        ("13(3)(b)(iv)", "where applicable, the technical capabilities and characteristics of the high-risk ai system to provide information that is relevant to explain its output"),
        ("13(3)(b)(v)", "when appropriate, its performance regarding specific persons or groups of persons on which the system is intended to be used"),
        ("13(3)(b)(vi)", "when appropriate, specifications for the input data, or any other relevant information in terms of the training, validation and testing data sets used"),
        ("13(3)(b)(vii)", "where applicable, information to enable deployers to interpret the output of the high-risk ai system and use it appropriately"),
        ("13(3)(c)", "at the moment of the initial conformity assessment, if any"),
        ("13(3)(d)", "the human oversight measures referred to in article 14, including the technical measures put in place to facilitate the interpretation of the outputs"),
        ("13(3)(e)", "the computational and hardware resources needed, the expected lifetime of the high-risk ai system and any necessary maintenance and care measures, including their frequency"),
        ("13(3)(f)", "where relevant, a description of the mechanisms included within the high-risk ai system that allows deployers to properly collect, store and interpret the logs in accordance with article 12"),
    ],
    "Q96": [
        ("Annex III(1)", "biometrics, in so far as their use is permitted under relevant union or national law"),
        ("Annex III(4)", "employment, workers' management and access to self-employment"),
        ("Annex III(5)", "access to and enjoyment of essential private services and essential public services and benefits"),
        ("Annex III(6)", "law enforcement, in so far as their use is permitted under relevant union or national law"),
        ("Annex III(7)", "migration, asylum and border control management, in so far as their use is permitted under relevant union or national law"),
        ("Annex III(8)", "administration of justice and democratic processes"),
        ("Annex III(5)(a)", "by public authorities or on behalf of public authorities to evaluate the eligibility of natural persons for essential public assistance benefits and services, including healthcare services, as well as to grant, reduce, revoke, or reclaim such benefits and services"),
        ("Annex III(5)(c)", "risk assessment and pricing in relation to natural persons in the case of life and health insurance"),
        ("Annex III(5)(d)", "emergency healthcare patient triage systems"),
        ("Annex III(7)(b)", "a health risk, posed by a natural person who intends to enter or who has entered into the territory of a member state"),
    ],
    "Q17": [
        ("7(1)", "where both of the following conditions are fulfilled"),
        ("7(1)(a)", "the ai systems are intended to be used in any of the areas listed in annex iii"),
        ("7(1)(b)", "that risk is equivalent to, or greater than, the risk of harm or of adverse impact posed by the high-risk ai systems already referred to in annex iii"),
        ("7(3)(a)", "no longer poses any significant risks to fundamental rights, health or safety"),
        ("7(3)(b)", "the deletion does not decrease the overall level of protection"),
        ("97(4)", "the commission shall consult experts designated by each member state"),
        ("97(6)", "within a period of three months of notification of that act to the european parliament and the council"),
        ("97(6)", "that period shall be extended by three months at the initiative of the european parliament or of the council"),
    ],
    "Q74": [
        ("50(2)", "marked in a machine-readable format and detectable as artificially generated or manipulated"),
        ("3(4)", "except where the ai system is used in the course of a personal non-professional activity"),
        ("2(10)", "this regulation does not apply to obligations of deployers who are natural persons using ai systems in the course of a purely personal non-professional activity"),
        ("3(11)", "the supply of an ai system for first use directly to the deployer or for own use in the union for its intended purpose"),
        ("3(60)", "resembles existing persons, objects, places, entities or events and would falsely appear to a person to be authentic or truthful"),
        ("50(4)", "evidently artistic, creative, satirical, fictional or analogous work or programme"),
        ("50(4)", "limited to disclosure of the existence of such generated or manipulated content in an appropriate manner that does not hamper the display or enjoyment of the work"),
        ("50(5)", "in a clear and distinguishable manner at the latest at the time of the first interaction or exposure"),
        ("50(5)", "conform to the applicable accessibility requirements"),
        ("113", "it shall apply from 2 august 2026"),
    ],
    "Q95": [
        ("Annex III(2)", "ai systems intended to be used as safety components in the management and operation of critical digital infrastructure, road traffic, or in the supply of water, gas, heating or electricity"),
    ],
    "Q104": [
        ("Annex X", "union legislative acts on large-scale it systems in the area of freedom, security and justice"),
        ("Annex X(4)", "entry/exit system"),
        ("Annex X(5)", "european travel information and authorisation system"),
        ("Annex X(6)", "european criminal records information system on third-country nationals and stateless persons"),
        ("Annex X(7)", "interoperability"),
        ("111(1)", "without prejudice to the application of article 5 as referred to in article 113(3), point (a)"),
        ("111(1)", "placed on the market or put into service before 2 august 2027 shall be brought into compliance with this regulation by 31 december 2030"),
        ("111(1)", "shall be taken into account in the evaluation of each large-scale it system"),
        ("113(a)", "chapters i and ii shall apply from 2 february 2025"),
    ],
    "Q6": [
        ("6(1)", "the ai system is intended to be used as a safety component of a product, or the ai system is itself a product, covered by the union harmonisation legislation listed in annex i"),
        ("6(1)", "required to undergo a third-party conformity assessment"),
        ("4", "providers and deployers of ai systems shall take measures to ensure, to their best extent, a sufficient level of ai literacy"),
        ("95", "codes of conduct"),
    ],
    "Q10": [
        ("3(3)", "places it on the market or puts the ai system into service under its own name or trademark, whether for payment or free of charge"),
        ("Recital 83", "fulfil cumulatively all relevant obligations associated with those roles"),
        ("25(1)(a)", "without prejudice to contractual arrangements stipulating that the obligations are otherwise allocated"),
        ("25(1)(b)", "in such a way that it remains a high-risk ai system pursuant to article 6"),
        ("25(1)(c)", "including a general-purpose ai system, which has not been classified as high-risk and has already been placed on the market or put into service"),
        ("25(1)", "shall be subject to the obligations of the provider under article 16"),
    ],
    "Q16": [
        ("5(1)(f)", "the placing on the market, the putting into service for this specific purpose, or the use of ai systems to infer emotions of a natural person in the areas of workplace and education institutions, except where the use of the ai system is intended to be put in place or into the market for medical or safety reasons"),
        ("Recital 18", "it does not include physical states, such as pain or fatigue"),
        ("Annex III(4)(b)", "to monitor and evaluate the performance and behaviour of persons in such relationships"),
        ("113(a)", "chapters i and ii shall apply from 2 february 2025"),
    ],
    "Case D": [
        ("Annex I(11)", "11. regulation (eu) 2017/745 of the european parliament and of the council of 5 april 2017 on medical devices"),
        ("Annex I", "section a. list of union harmonisation legislation based on the new legislative framework"),
        ("113(c)", "article 6(1) and the corresponding obligations in this regulation shall apply from 2 august 2027"),
    ],
    # R467 — the wording the fixes added.
    "Q45 (R467)": [
        ("13(3)(b)(ii)", "against which the high-risk ai system has been tested and validated and which can be expected"),
        ("13(3)(b)(ii)", "any known and foreseeable circumstances that may have an impact on that expected level"),
        ("13(3)(b)(iii)", "related to the use of the high-risk ai system in accordance with its intended purpose or under conditions of reasonably foreseeable misuse"),
        ("13(3)(b)(vi)", "taking into account the intended purpose of the high-risk ai system"),
    ],
    "Q10 (R467)": [
        ("3(3)", "develops an ai system or a general-purpose ai model"),
        ("Recital 83", "could act in more than one role at the same time and should therefore fulfil cumulatively all relevant obligations associated with those roles"),
    ],
    "Art. 25 (R467)": [
        ("25(1)", "shall be subject to the obligations of the provider under article 16, in any of the following circumstances"),
        ("25(1)(b)", "that has already been placed on the market or has already been put into service in such a way that it remains a high-risk ai system pursuant to article 6"),
        ("25(1)(c)", "which has not been classified as high-risk and has already been placed on the market or put into service in such a way that the ai system concerned becomes a high-risk ai system in accordance with article 6"),
        ("25(2)", "shall no longer be considered to be a provider of that specific ai system"),
        ("25(2)", "that initial provider shall closely cooperate with new providers"),
        ("25(2)", "this paragraph shall not apply in cases where the initial provider has clearly specified that its ai system is not to be changed into a high-risk ai system"),
    ],
    "Q74 (R467)": [
        ("3(60)", "ai-generated or manipulated image, audio or video content"),
    ],
    "Case D (MDR)": [
        ("MDR 51(1)", "devices shall be divided into classes i, iia, iib and iii, taking into account the intended purpose of the devices and their inherent risks"),
        ("MDR 52(3)", "manufacturers of class iii devices, other than custom-made or investigational devices, shall be subject to a conformity assessment"),
        ("MDR 52(4)", "manufacturers of class iib devices, other than custom-made or investigational devices, shall be subject to a conformity assessment"),
        ("MDR 52(6)", "manufacturers of class iia devices, other than custom-made or investigational devices, shall be subject to a conformity assessment"),
    ],
}


def main() -> int:
    missing = 0
    for case, items in CHECKS.items():
        corpus = MDR if "MDR" in case else AI
        for where, phrase in items:
            ok = norm(phrase) in corpus
            missing += not ok
            print(f"{'OK  ' if ok else 'MISS'} {case:12s} {where:16s} {phrase[:90]}")
    print(f"\n{sum(len(v) for v in CHECKS.values()) - missing} found, {missing} missing")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
