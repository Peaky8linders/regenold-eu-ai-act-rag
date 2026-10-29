"""R473 — build the concise expert-review appendix of 29 October 2026 (HTML, then PDF via headless Chrome).

A short, plain-language re-issue of the appendices of 23 and 26 October (``docs/measurements/r467`` and
``r472``). It keeps what the expert review asked about: each of its points, the answer the system gives
now, and where the answer states the point. It leaves out how the system produces its answers.

Inputs
  * ``expert_review_rerun.json``      the ten reviewed questions asked live on 29 October (this directory);
  * ``offline_wire_replay.json``      the same ten replayed with no model reachable (this directory);
  * ``../r467/sept29_answers.json``   the answers the review assessed (29 September report update);
  * ``../r467/expert_review_rerun_r467d.json``  the same ten on 23 October;
  * ``../r472``                       the 26 October run, its measurement records and its build script, whose
                                      evidence functions are reused so their assertions still run;
  * the expert review (``Antifragile AI Oct 2026 expert review.txt``) and the Official Journal texts
    (``tmp/legal-audit-2026-09-29``), neither tracked: both are found in the main checkout, or set
    ``REGENOLD_EXPERT_REVIEW_FILE`` / ``REGENOLD_LEGAL_TEXT_DIR``.

The build refuses to write a document when:
  * a quoted passage is not a verbatim substring of the live answer, or removed wording is still there;
  * a quotation attributed to the review is not in the review document (or the 29 September answer);
  * a verdict does not match the review's own;
  * the offline replay does not reproduce the live answers;
  * a statement about Regulation (EU) 2026/1744 does not read as the amending text says;
  * the finished page names a system internal (``INTERNALS``), which this issue keeps out on purpose.

Usage (repo root):
    <main checkout>/.venv/Scripts/python.exe docs/measurements/r473/build_appendix.py [--no-pdf] [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import copy
import html
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
R467, R472 = HERE.parent / "r467", HERE.parent / "r472"
OUT_NAME = "Appendix-Expert-Review-2026-10-29"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
DATE = "29 October 2026"
E = html.escape


def _main_checkout() -> Path:
    out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                         cwd=REPO, capture_output=True, text=True, check=False).stdout.strip()
    return Path(out).parent if out else REPO


MAIN = _main_checkout()
LEGAL_DIR = Path(os.environ.get("REGENOLD_LEGAL_TEXT_DIR") or MAIN / "tmp" / "legal-audit-2026-09-29")
REVIEW_FILE = Path(os.environ.get("REGENOLD_EXPERT_REVIEW_FILE") or MAIN / "Antifragile AI Oct 2026 expert review.txt")
os.environ["REGENOLD_LEGAL_TEXT_DIR"] = str(LEGAL_DIR)  # the R467 statute check reads it at import


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fold(text: str) -> str:
    """Typographic quotes and spaces folded, lower case: for matching text across documents."""
    for a, b in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'), ("\u00a0", " ")):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip().lower()


def load_r472():
    spec = importlib.util.spec_from_file_location("r472_build_appendix", R472 / "build_appendix.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Words that describe how the system works. None may appear on the finished page: this
# issue is about the answers and the review, not the machinery behind them.
# ---------------------------------------------------------------------------
INTERNALS = (r"R4\d\d", r"\b[0-9a-f]{12}\b", r"wrapper", r"Railway", r"endpoint", r"Sonnet", r"Opus", r"Claude", r"offline",
             r"held-out", r"routing", r"language model", r"statutory answer", r"stored summary", r"pre-drafted",
             r"\bbyte", r"\bhash", r"\bAPI\b", r"\bJSON\b", r"pipeline", r"\bjudge", r"\bflag\b", r"Stage-?[012]")


# ---------------------------------------------------------------------------
# What this issue changes in the cases it takes from r472 (``CASES``): the notes, shortened and
# written for a reader outside the project. Each ``note_checks`` / ``note_absent`` is asserted against
# the live answer by ``check_and_collect``.
# ---------------------------------------------------------------------------
NOTES = {
    "Q45": {"notes": ["The answer also states Article 13(1) and sets out point (b) as items (i) to (vii), "
                      "closely following the Act's wording. Items (e) and (f) paraphrase it; item (f) leaves out "
                      "the Act's \u201ca description of\u201d."],
            "note_checks": ["(f) where relevant, the mechanisms enabling deployers"],
            "note_absent": ["a description of"]},
    "Q96": {"notes": ["Point 5(a) follows the Act's wording; its closing words are condensed (\u201cto grant, "
                      "reduce, revoke or reclaim them\u201d for \u201cas well as to grant, reduce, revoke, or "
                      "reclaim such benefits and services\u201d). Areas 1, 6 and 7 keep the Annex III "
                      "qualifier \u201cin so far as their use is permitted under relevant Union or national "
                      "law\u201d, which the review's list leaves out. The 29 September reference to "
                      "Article 6(1) and Annex I is no longer in the answer."],
             "note_checks": ["to grant, reduce, revoke or reclaim them",
                             "biometrics, in so far as their use is permitted under relevant Union or national law"]},
    "Q17": {"notes": ["The answer also states the consultation of experts designated by each Member State "
                      "(Article 97(4)), as the review's correct position does, and, in paraphrase, the power to "
                      "remove use cases (Article 7(3))."]},
    "Q74": {"notes": ["The review notes that the question leaves three facts open (whether the use is a personal "
                      "non-professional activity, whether the audio is a deep fake, whether the work is evidently "
                      "artistic to those exposed to it) and finds it not defective, since a single conditional "
                      "answer is available. The answer states each fact as a condition. It does not say, as the "
                      "review does, that artistic purpose is no exception to the provider's duty or that the "
                      "provider branch is unlikely on these facts, and its deep-fake definition still omits "
                      "\u201cimage, audio or video\u201d, as the review's corrected answer does. It cites five "
                      "provisions where the official appendix expects one (Article 50(4))."],
            "note_checks": ["personal non-professional activity", "deep fake", "evidently artistic",
                            "AI-generated or manipulated content that resembles"],
            "note_absent": ["unlikely", "edge case", "artistic purpose", "image, audio or video"]},
    "Q95": {"notes": ["The review observed that Article 6(2) uses neither term and treated the question as "
                      "answerable. The 29 September sentence on Article 7(1) is gone."],
            "note_absent": ["in so far as their use is permitted"]},
    "Q104": {"notes": ["All seven headings of Annex X are now named; the 29 September answer named three."]},
    "Q6 (Case A)": {"notes": ["The review adds that \u201cnor high-risk under Article 6\u201d covers both routes. "
                              "Article 6(1) is qualified by the 2026 amendment (see Legal basis)."],
                    "note_checks": ["nor high-risk under Article 6"]},
    "Q10 (Case B)": {"notes": ["The answer also includes general-purpose AI models in the Article 3(3) "
                               "definition. One difference from the review's corrected answer remains: the "
                               "Article 25(1) sentence does not repeat the Act's words \u201cunder Article 16\u201d."],
                     "note_checks": ["develops an AI system or a general-purpose AI model"],
                     "note_absent": ["Article 16"]},
    "Q16 (Case C)": {"notes": ["The answer states the Annex III route and the Article 26 obligations but does not "
                               "say, in the review's words, that the use is \u201callowed only on "
                               "conditions\u201d. The Annex III date follows the Act as adopted (see Legal basis)."],
                     "note_absent": ["allowed only", "permitted only"]},
    "Q17 (Case D)": {"notes": ["The review also observes that the question itself supplies the safety-component "
                               "characterisation (Article 3(14)); the answer takes that as given. Like the review's "
                               "corrected answer, it addresses classification only. The date and the notion of "
                               "safety component follow the Act as adopted (see Legal basis)."],
                     "note_absent": ["3(14)"]},
}

#: Statements the answers make that the Act as amended by Regulation (EU) 2026/1744 words differently or
#: qualifies. Every figure and quotation is asserted against the amending text by ``omnibus_facts``.
OMNIBUS_ROWS = [
    ("Q16 (Case C)", "Obligations for Annex III high-risk systems apply from 2 August 2026.",
     "Chapter III, Sections 1 to 3, apply to Annex III systems from <b>2 December 2027</b> "
     "(Article 113, third paragraph, point (c)(i), as amended)."),
    ("Q17 (Case D)", "Article 6(1) and the corresponding obligations apply from 2 August 2027.",
     "Chapter III, Sections 1 to 3, apply to Annex I systems from <b>2 August 2028</b> "
     "(Article 113, third paragraph, point (c)(ii), as amended)."),
    ("Q17 (Case D), Q6 (Case A), Q95",
     "Article 6(1) covers an AI system that is, or is a safety component of, a product covered by Annex I and "
     "needing third-party conformity assessment (Q17, Q6). Annex III point 2 lists safety components of critical "
     "infrastructure (Q95).",
     "For the whole Act, \u201csafety component\u201d (Article 3(14)) now also says that a component fulfils a "
     "safety function where its intended purpose is to prevent or mitigate risks to health and safety of persons "
     "or property. New Article 6(1a): systems used solely for non-safety aspects such as user assistance or quality "
     "control do not qualify; (1b) systems whose failure or malfunctioning would endanger health and safety do; "
     "(1c) a product requiring third-party assessment solely due to risks other than risks to health and safety, "
     "such as radio spectrum or electromagnetic interference, does not meet the condition in Article 6(1), "
     "point (b). Annex III is unchanged."),
    ("Q104", "The Article 5 prohibitions have applied since 2 February 2025.",
     "Unchanged for the prohibitions of the adopted text. The new prohibitions in Article 5(1), first "
     "subparagraph, points (ba) and (bb), and Article 5(1a) and (1b), which delimit them, apply from "
     "<b>2 December 2026</b> (Article 113, third paragraph, point (a), as amended)."),
    ("Q74", "The Article 50 obligations apply from 2 August 2026.",
     "Unchanged. New Article 111(4): providers of AI systems, including general-purpose AI systems, generating "
     "synthetic audio, image, video or text content that were placed on the market before 2 August 2026 must take "
     "the necessary steps to comply with Article 50(2) by <b>2 December 2026</b>."),
    ("Q6 (Case A)", "Providers and deployers remain subject to the Article 4 AI literacy obligation.",
     "Article 4 replaced: the obligation remains with providers and deployers, now to \u201ctake measures to "
     "support the development of AI literacy\u201d; it does not require them to guarantee any specific level of "
     "AI literacy of any individual."),
]

UNCHANGED = ("Articles 7, 13 and 26; Article 2(10); Article 3(3), (4), (11) and (60); Article 5(1)(f); "
             "Article 25(1); Article 50(2), (4) and (5); Article 111(1); Annexes III and X. Article 97(6) now "
             "also covers delegated acts under Article 2(13) and Article 30(2); its objection period and "
             "extension are unchanged. Regulation (EU) 2017/745 remains point 11 of Section A of Annex I.")

#: New Article 2(13): not a row, because it changes no statement an answer makes today.
NEW_2_13 = ("New Article 2(13) lets specific requirements of Articles 9 to 15 and 17 to 25 (which include Articles "
            "13 and 25) be limited for Article 6(1) systems where legislation listed in Section A of Annex I gives "
            "equivalent or higher protection; the Commission is to specify them by delegated act by 2 August 2027. "
            "The text of Articles 13 and 25(1) is unchanged.")


def omnibus_facts() -> int:
    """Assert every statement about Regulation (EU) 2026/1744 against its text; returns the claims checked."""
    flat = lambda t: re.sub(r"\s+", " ", t)  # noqa: E731
    amend = flat((LEGAL_DIR / "ai-amendment.txt").read_text(encoding="utf-8"))
    original = fold((LEGAL_DIR / "ai-original.txt").read_text(encoding="utf-8"))
    current = fold((LEGAL_DIR / "ai-current.txt").read_text(encoding="utf-8"))
    start = amend.find("Regulation (EU) 2024/1689 is amended as follows")
    items = re.split(r"(?<=[;\u2019:.]) (?=\(\d{1,2}\) )", amend[start:])
    ops: dict[int, str] = {}
    for item in items[1:]:  # numbering restarts for the other regulations the act amends
        n = int(re.match(r"\((\d+)\)", item).group(1))
        if n != len(ops) + 1:
            break
        ops[n] = item
    if len(ops) != 43:
        raise SystemExit(f"the amending act has {len(ops)} operative items for the AI Act, expected 43")

    claims = 0

    def need(cond: bool, what: str) -> None:
        nonlocal claims
        claims += 1
        if not cond:
            raise SystemExit(f"Regulation (EU) 2026/1744 no longer reads as the appendix says: {what}")

    heads = {n: re.sub(r"^\(\d+\) ", "", it)[:70] for n, it in ops.items()}
    # -- provisions the answers cite that the act leaves alone ---------------------------------------
    for n, head in heads.items():
        need(not re.match(r"(?:in )?Article (7|13|26)\b", head), f"item ({n}) touches Article 7, 13 or 26")
        need(not re.match(r"(?:in )?Annex (III|X)\b", head), f"item ({n}) touches Annex III or X")
    need(re.findall(r"paragraphs? (\d+)", ops[2]) == ["2", "7"], "Article 2 amended beyond paragraphs 2 and 7")
    need("paragraph is added: \u2018" + "13." in ops[3], "Article 2(13) is the added paragraph")
    need(re.findall(r"point \((\d+[a-z]?)\) is amended", ops[4]) == ["14"] and "(14a)" in ops[4]
         and "(14b)" in ops[4] and not re.search(r"\((3|4|11|60)\) “", ops[4]),
         "Article 3 amended beyond points (14), (14a) and (14b)")
    need("point (f)" not in ops[7] and "(ba)" in ops[7] and "(bb)" in ops[7], "Article 5(1)(f) is untouched")
    need(re.findall(r"\(([a-z])\) (?:in )?paragraphs? (\d+)", ops[12]) == [("a", "2"), ("b", "4")],
         "Article 25 amended beyond paragraphs 2 and 4")
    need(heads[20].startswith("in Article 50, paragraph 7 is replaced"), "Article 50 amended beyond paragraph 7")
    need(re.findall(r"\(([a-z])\) (?:paragraph|paragraphs) ([\d, and]+) (?:is|are) replaced", ops[39])
         == [("a", "2")] and "the following paragraph is added: \u20184." in ops[39],
         "Article 111 amended beyond paragraphs 2 and 4")
    # -- the rows of the table -----------------------------------------------------------------------
    need("(i) 2 December 2027 as regards AI systems classified as high-risk pursuant to Article 6(2) and Annex III"
         in ops[40] and "(ii) 2 August 2028 as regards AI systems classified as high-risk pursuant to Article 6(1) "
         "and Annex I" in ops[40] and "Chapter III, Sections 1, 2, and 3" in ops[40], "Article 113(3)(c)")
    need("with the exception of Article 5(1), first subparagraph, points (ba) and (bb), and Article 5(1a) and (1b) "
         "which shall apply from 2 December 2026" in ops[40], "Article 113(3)(a)")
    need("Providers of AI systems, including general-purpose AI systems, generating synthetic audio, image, video "
         "or text content, that have been placed on the market before 2 August 2026 shall take the necessary steps "
         "in order to comply with Article 50(2) by 2 December 2026" in ops[39], "Article 111(4)")
    need("\u2018(14) \u201csafety component\u201d means a component of a product or of an AI system" in ops[4],
         "the new Article 3(14)")
    need("AI systems that are solely used for non-safety related aspects of user assistance, performance "
         "optimisation, service efficiency, automation or convenience or quality control shall not qualify as "
         "safety components" in ops[8], "Article 6(1a)")
    need("AI systems the failure or malfunctioning of which would endanger health and safety shall qualify as "
         "safety components" in ops[8], "Article 6(1b)")
    need("required to undergo a third-party conformity assessment solely due to risks other than risks to health "
         "and safety" in ops[8] and "shall not be considered as fulfilling the condition in paragraph 1, point (b)"
         in ops[8], "Article 6(1c)")
    need("Article 4 is replaced" in ops[5] and "shall take measures to support the development of AI literacy" in
         ops[5] and "does not require providers or deployers to guarantee any specific level of AI literacy" in
         ops[5], "Article 4")
    need("(a) paragraphs 2 and 3 are replaced" in ops[37] and "(b) paragraph 6 is replaced" in ops[37]
         and "shall enter into force only if no objection has been expressed" in ops[37]
         and "within a period of three months of notification" in ops[37]
         and "That period shall be extended by three months at the initiative of the European Parliament or of "
         "the Council" in ops[37] and "Article 2(13)" in ops[37] and "Article 30(2)" in ops[37],
         "Article 97(6)")
    need("in Section A, point 1 is deleted" in ops[41], "Annex I, Section A, point 1")
    need("for the purposes of this definition, a component fulfils a safety function where its intended purpose is "
         "to prevent or mitigate risks to health and safety of persons or property" in ops[4], "Article 3(14), new limb")
    need("For the purposes of this Regulation, including paragraph 1 of this Article" in ops[8], "Article 6(1a) scope")
    need("in particular risks relating to the distribution of radio spectrum or electromagnetic interference that do "
         "not affect health and safety" in ops[8], "Article 6(1c) examples")
    need("1a. For the purposes of paragraph 1, first subparagraph, points (ba) and (bb)" in ops[7]
         and "1b. For the purposes of paragraph 1, first subparagraph, point (ba)" in ops[7],
         "Article 5(1a) and (1b) delimit points (ba) and (bb)")
    need("the application of specific requirements or obligations laid down in Articles 9 to 15 and 17 to 25 may be "
         "limited" in ops[3] and "providing an equivalent or higher level of protection" in ops[3]
         and "By 2 August 2027, the Commission shall adopt delegated acts in accordance with Article 97" in ops[3],
         "Article 2(13)")
    # -- the consolidated text: provisions stated unchanged -----------------------------------------
    f_text = ("(f) the placing on the market, the putting into service for this specific purpose, or the use of ai "
              "systems to infer emotions of a natural person in the areas of workplace and education institutions, "
              "except where the use of the ai system is intended to be put in place or into the market for medical "
              "or safety reasons")
    need(f_text in original and f_text in current, "Article 5(1)(f) differs between the adopted and consolidated texts")
    need("11. regulation (eu) 2017/745 of the european parliament and of the council of 5 april 2017 on medical "
         "devices" in current, "Regulation (EU) 2017/745 is no longer point 11 of Annex I, Section A")
    return claims


# ---------------------------------------------------------------------------
# The review document
# ---------------------------------------------------------------------------
REVIEW_KEY = {"Q45": "Q45", "Q96": "Q96", "Q17": "Q17", "Q74": "Q74", "Q95": "Q95", "Q104": "Q104",
              "Q6 (Case A)": "Q6 Case A", "Q10 (Case B)": "Q10 Case B", "Q16 (Case C)": "Q16 Case C",
              "Q17 (Case D)": "Q17 Case D"}


def review_blocks() -> dict[str, str]:
    text = REVIEW_FILE.read_text(encoding="utf-8", errors="replace")
    parts = re.split(r"\n\d+\.\s+(Q\d+(?: Case [A-D])?)\s*\n", "\n" + text)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def check_review(cases: list[dict], before_rows: dict[str, dict], live_rows: dict[str, dict]) -> int:
    """Verdicts match the review's own; every quotation in a remark or note is in the review, the 29 September
    answer, today's answer or the Act (the notes quote all four)."""
    blocks = review_blocks()
    if set(blocks) != set(REVIEW_KEY.values()):
        raise SystemExit(f"the review document no longer has the ten cases: {sorted(blocks)}")
    whole = fold(REVIEW_FILE.read_text(encoding="utf-8", errors="replace"))
    act = fold((LEGAL_DIR / "ai-original.txt").read_text(encoding="utf-8"))
    n = 0
    for case in cases:
        block = blocks[REVIEW_KEY[case["id"]]]
        said = re.search(r"September 29, answer:\s*(.+)", block)
        if not said or not fold(case["verdict"]).startswith(fold(said.group(1)).rstrip(". ")):
            raise SystemExit(f"{case['id']}: verdict {case['verdict']!r} is not the review's {said and said.group(1)!r}")
        sept = fold(before_rows[case["id"]]["answer"])
        for point in case["points"]:
            for quote in re.findall(r"\u201c([^\u201d]+)\u201d", point["before"][1]):
                n += 1
                q = fold(quote).rstrip(".,;")
                if q not in whole and q not in sept:
                    raise SystemExit(f"{case['id']}: quotation not in the review or the 29 September answer: {quote!r}")
        now = fold(live_rows[case["id"]]["answer"])
        for note in case.get("notes", []):
            for quote in re.findall(r"\u201c([^\u201d]+)\u201d", note):
                q = fold(quote).rstrip(".,;")
                if not any(q in text for text in (whole, sept, now, act)):
                    raise SystemExit(f"{case['id']}: a note quotes text found nowhere: {quote!r}")
    return n


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
TAG_CLASS = {"DEFECT": "def", "PRECISION": "prc", "PARTLY MET": "part", "MET": "met"}
TAG_LABEL = {"DEFECT": "Defect", "PRECISION": "Precision", "PARTLY MET": "Partly met", "MET": "Met"}


def remark_text(remark: str) -> str:
    if remark.startswith("Review: "):
        rest = remark[len("Review: "):]
        return rest[0].upper() + rest[1:]
    if remark.startswith("Answer: "):
        return "29 September answer: " + remark[len("Answer: "):]
    raise SystemExit(f"unclassified remark: {remark[:60]!r}")


def answer_html(answer: str, points: list[dict]) -> str:
    """The answer with the passages that state each point marked and numbered."""
    text = norm(answer)
    spans = []
    for i, point in enumerate(points, 1):
        for quote in point["after"]:
            q = norm(quote)
            if text.count(q) != 1:
                raise SystemExit(f"evidence is not a single passage of the answer: {q[:70]!r}")
            start = text.index(q)
            spans.append((start, start + len(q), i))
    spans.sort()
    if any(a[1] > b[0] for a, b in zip(spans, spans[1:], strict=False)):
        raise SystemExit("two evidence passages overlap")
    out, pos = [], 0
    for start, end, i in spans:
        out.append(E(text[pos:start]))
        out.append(f'<mark class="ev">{E(text[start:end])}</mark><sup class="evn">{i}</sup>')
        pos = end
    out.append(E(text[pos:]))
    return "".join(out)


def render_case(case: dict, live: dict) -> str:
    n = len(case["points"])
    noun = "point" if n == 1 else "points"
    pill = "warn" if case["kind"] == "correct" else "bad"
    head = case["id"].replace(" (", " \u00b7 ").rstrip(")")
    verdict = case["verdict"][0].lower() + case["verdict"][1:]
    expected = case.get("expected")
    cites = f'<span class="refs"><strong>Cites:</strong> {E(", ".join(live["references"]))}</span>'
    if expected:
        cites += f'<span class="req"><strong>Official appendix expects:</strong> {E(expected)}</span>'
    sub_head = ("\u2713 = our assessment" if not case.get("derived")
                else "points read from its correct position; \u2713 = our assessment")
    # The two columns share the width in proportion to their text, so neither leaves the other a long blank.
    left = sum(len(p["label"]) + len(remark_text(p["before"][1])) + 45 for p in case["points"])
    share = max(0.40, min(0.70, (len(live["answer"]) + 60) / (left + len(live["answer"]) + 60)))
    out = [f'<article class="case" id="case-{re.sub(r"[^a-z0-9]+", "-", case["id"].lower()).strip("-")}">',
           '  <div class="case-head">',
           f'    <div><span class="tag">{E(head)}</span> <h3 style="display:inline">{E(case["title"])}</h3></div>',
           f'    <div class="pills"><span class="pill {pill}">Review of 29 Sep answer: {E(verdict)}</span>'
           f'<span class="pill ok">{n} of {n} {noun} addressed</span></div>',
           '  </div>',
           f'  <p class="q">\u201c{E(live["question"])}\u201d</p>',
           f'  <div class="cols" style="--cols:{1 - share:.2f}fr {share:.2f}fr">',
           '    <div class="panel before">',
           f'      <div class="hd">Expert review, October 2026<span class="hd2">{sub_head}</span></div>']
    for i, point in enumerate(case["points"], 1):
        tag, remark = point["before"]
        if point.get("after_tag") == "REMOVED":
            status = f'<span class="res nb">\u2713 Wording removed.</span> {E(point["after_note"])}'
        elif tag == "MET":
            status = '<span class="res nb">\u2713 Still met</span>'
        elif point.get("qualify"):
            status = f'<span class="res">\u2713 Addressed ({E(point["qualify"])})</span>'
        else:
            status = '<span class="res nb">\u2713 Addressed</span>'
        out.append(f'      <div class="pt"><span class="pn">{i}</span><span class="tg {TAG_CLASS[tag]}">'
                   f'{TAG_LABEL[tag]}</span><b>{E(point["label"])}</b>'
                   f'<span class="remark">{E(remark_text(remark))} {status}</span></div>')
    out += ['    </div>',
            '    <div class="panel after">',
            f'      <div class="hd">Answer, {DATE}</div>',
            f'      <div class="answer">{answer_html(live["answer"], case["points"])}</div>',
            f'      <div class="meta">{cites}</div>',
            '    </div>',
            '  </div>']
    for note in case.get("notes", []):
        out.append(f'  <p class="note"><strong>Note.</strong> {E(note)}</p>')
    out.append('</article>')
    return "\n".join(out)


CSS = r"""
  :root{
    --bg:#fbfaf9; --fg:#1c1a18; --muted:#6b645d; --line:#e2ddd7; --card:#ffffff;
    --ok:#1a7f52; --ok-bg:#eaf6f0; --ok-line:#b6e0cb; --ok-mark:rgba(26,127,82,.17);
    --bad:#a8341f; --bad-bg:#fbeeea; --bad-line:#f0cec4;
    --note:#7a5c12; --note-bg:#fdf6e3; --note-line:#ecd9a3;
    --accent:#2b5c8a; --accent-bg:#eef4fa; --accent-line:#c2d8ea;
  }
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]){
      --bg:#16151a; --fg:#eceaf0; --muted:#a09aa8; --line:#33303a; --card:#1e1d23;
      --ok:#5fd39b; --ok-bg:#12261d; --ok-line:#2a5a42; --ok-mark:rgba(95,211,155,.2);
      --bad:#f0907a; --bad-bg:#2a1714; --bad-line:#5e2f26;
      --note:#e0bd6a; --note-bg:#282010; --note-line:#5a4a24;
      --accent:#8ab6de; --accent-bg:#152230; --accent-line:#2e4a63;
    }
  }
  *{box-sizing:border-box}
  body{background:var(--bg);color:var(--fg);margin:0;
    font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
  .wrap{max-width:68rem;margin:0 auto;padding:2.5rem 2rem 4rem}
  h1{font-size:1.75rem;line-height:1.25;margin:.2rem 0 .5rem;letter-spacing:-.02em}
  h2{font-size:1.15rem;margin:2.4rem 0 .7rem;letter-spacing:-.01em}
  h3{font-size:1rem;margin:0}
  p{margin:.6rem 0}
  header{border-bottom:1px solid var(--line);padding-bottom:1.25rem;margin-bottom:1.25rem}
  table{width:100%;border-collapse:collapse;font-size:.85rem;margin:.5rem 0 0}
  th,td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid var(--line);vertical-align:top}
  th{font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
  td.ok{color:var(--ok);font-weight:700;white-space:nowrap}
  td.nw{white-space:nowrap}
  .scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
  ul.steps{margin:.5rem 0 0;padding-left:1.3rem} ul.steps li{margin:.45rem 0}
  .part{font-size:1rem;margin:1.6rem 0 .6rem;color:var(--accent);text-transform:uppercase;letter-spacing:.05em}
  .case{border:1px solid var(--line);border-radius:.9rem;background:var(--card);padding:1.2rem;margin:1rem 0}
  .case-head{display:flex;flex-wrap:wrap;gap:.6rem;align-items:baseline;justify-content:space-between;
    border-bottom:1px solid var(--line);padding-bottom:.7rem;margin-bottom:.9rem}
  .tag{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.7rem;font-weight:700;
    padding:.15rem .5rem;border-radius:.35rem;border:1px solid var(--accent-line);background:var(--accent-bg);
    color:var(--accent)}
  .pill{font-size:.75rem;font-weight:700;padding:.2rem .6rem;border-radius:999px;white-space:nowrap}
  .pill.ok{color:var(--ok);background:var(--ok-bg);border:1px solid var(--ok-line)}
  .pill.bad{color:var(--bad);background:var(--bad-bg);border:1px solid var(--bad-line)}
  .pill.warn{color:var(--note);background:var(--note-bg);border:1px solid var(--note-line)}
  .pills{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center}
  .q{font-weight:600;margin:0 0 .8rem}
  .cols{display:grid;grid-template-columns:1fr;gap:.9rem;align-items:start}
  @media(min-width:52rem){.cols{grid-template-columns:var(--cols,5fr 6fr)}}
  table.findings th:nth-child(1){width:29%} table.findings th:nth-child(2){width:16%}
  table.findings th:nth-child(4){width:12%}
  table.legal th:nth-child(1){width:13%} table.legal th:nth-child(2){width:33%}
  .panel{border-radius:.6rem;padding:.8rem .95rem;font-size:.83rem}
  .panel.before{border:1px solid var(--bad-line);background:var(--bad-bg)}
  .panel.after{border:1px solid var(--ok-line);background:var(--ok-bg)}
  .panel .hd{font-weight:700;font-size:.75rem;text-transform:uppercase;letter-spacing:.06em;margin-bottom:.5rem}
  .panel.before .hd{color:var(--bad)} .panel.after .hd{color:var(--ok)}
  .answer{line-height:1.6}
  mark.ev{background:var(--ok-mark);color:inherit;border-radius:.15rem;padding:0 .05rem;
    -webkit-box-decoration-break:clone;box-decoration-break:clone}
  sup.evn{color:var(--ok);font-weight:700;font-size:.66em;margin-left:.12em}
  .meta{font-size:.74rem;color:var(--muted);margin-top:.55rem;display:flex;flex-wrap:wrap;gap:.2rem .9rem;
    padding-top:.4rem;border-top:1px dashed var(--ok-line)}
  .meta strong{color:var(--fg);font-size:.66rem;text-transform:uppercase;letter-spacing:.04em;margin-right:.2rem}
  .pt{margin:.55rem 0;line-height:1.45}
  .pt b{font-weight:600}
  .pn{display:inline-block;min-width:1.2rem;height:1.2rem;border-radius:50%;background:var(--ok);color:#fff;
    font-size:.68rem;font-weight:700;text-align:center;line-height:1.2rem;margin-right:.4rem}
  .tg{display:inline-block;font-size:.6rem;font-weight:700;letter-spacing:.03em;text-transform:uppercase;
    padding:.04rem .32rem;border-radius:.25rem;margin-right:.4rem;vertical-align:.08em;background:var(--card)}
  .tg.def{color:var(--bad);border:1px solid var(--bad-line)}
  .tg.prc,.tg.part{color:var(--note);border:1px solid var(--note-line)}
  .tg.met{color:var(--ok);border:1px solid var(--ok-line)}
  .remark{color:var(--muted);font-size:.8rem;display:block;margin-top:.15rem}
  .hd2{display:inline-block;max-width:100%;font-weight:600;text-transform:none;letter-spacing:0;font-size:.68rem;
    color:var(--muted);margin-left:.4rem;vertical-align:top}
  .res{color:var(--ok);font-weight:600;font-size:.76rem}
  .res.nb{white-space:nowrap}
  .note{font-size:.8rem;color:var(--muted);margin:.8rem 0 0;padding-top:.6rem;border-top:1px dashed var(--line)}
  .note strong{color:var(--fg)}
  .fine{font-size:.8rem;color:var(--muted)}
  .update{border:1px solid var(--accent-line);background:var(--accent-bg);border-radius:.9rem;
    padding:1.1rem 1.25rem;margin:1.3rem 0}
  .update h2{margin:0 0 .6rem}
  .update table{background:var(--card);border-radius:.5rem}
  .kind{display:inline-block;margin-bottom:.15rem;font-size:.62rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--ok);
    border:1px solid var(--ok-line);background:var(--card);border-radius:.25rem;padding:.05rem .32rem}
  @page{size:A4;margin:13mm 12mm 15mm;
    @bottom-left{content:"Antifragile AI \00B7  Regenold EU AI Act Q&A Challenge \00B7  expert review appendix \00B7  __DATE__";
      font:7.5pt "Segoe UI",Arial,sans-serif;color:#6b645d}
    @bottom-right{content:"Page " counter(page) " of " counter(pages);font:7.5pt "Segoe UI",Arial,sans-serif;color:#6b645d}}
  @media print{
    html{font-size:11.5px;-webkit-print-color-adjust:exact;print-color-adjust:exact}
    body{font-size:11.5px;background:#fff}
    .wrap{padding:0;max-width:none}
    header{padding-bottom:.8rem;margin-bottom:.7rem}
    h2{margin-top:1.4rem}
    .cols{grid-template-columns:var(--cols,5fr 6fr);gap:.6rem}
    thead{display:table-header-group}
    tr,.panel,.case-head,.pt,.note{break-inside:avoid}
    h2,h3,.case-head,.q,.part{break-after:avoid}
    h2.sec-answers{break-before:page;margin-top:0}
    .part{margin:.9rem 0 .4rem}
    ul.steps li{margin:.3rem 0}
    .case{break-inside:avoid;padding:.7rem .75rem;margin:.5rem 0}
    .case-head{padding-bottom:.5rem;margin-bottom:.55rem}
    .q{margin-bottom:.55rem}
    .update{break-inside:avoid;padding:.8rem 1rem;margin:.8rem 0}
    .panel{padding:.55rem .7rem}
    .answer{line-height:1.5}
    .pt{margin:.38rem 0;line-height:1.4}
    th,td{padding:.24rem .5rem}
  }
"""


def build(no_pdf: bool, out_dir: Path) -> None:
    r472 = load_r472()
    out_html, out_pdf = out_dir / f"{OUT_NAME}.html", out_dir / f"{OUT_NAME}.pdf"

    # -- the runs ----------------------------------------------------------------------------------
    before_rows = {r["id"]: r for r in load(R467 / "sept29_answers.json")["rows"]}
    oct23_rows = {r["id"]: r for r in load(R467 / "expert_review_rerun_r467d.json")["rows"]}
    oct26 = load(R472 / "expert_review_rerun.json")
    oct26_rows = {r["id"]: r for r in oct26["rows"]}
    live = load(HERE / "expert_review_rerun.json")
    live_rows = {r["id"]: r for r in live["rows"]}
    if any("error" in r for r in live["rows"]) or live["commit"] != live["commit_after"]:
        raise SystemExit("the live run has errors or the deployment changed during it")
    if live["commit"] == oct26["commit"]:
        print("note: production serves the same build as on 26 October")
    ids = [c["id"] for c in r472.CASES]
    if set(ids) != set(live_rows) or len(ids) != 10:
        raise SystemExit("the live run does not hold the ten reviewed questions")
    for cid in ids:
        if live_rows[cid]["answer"] != oct26_rows[cid]["answer"] or live_rows[cid]["references"] != oct26_rows[cid]["references"]:
            raise SystemExit(f"{cid}: today's answer differs from 26 October; re-read the text before building")
    changed23 = [cid for cid in ids if live_rows[cid]["answer"] != oct23_rows[cid]["answer"]]
    if any(live_rows[cid]["references"] != oct23_rows[cid]["references"] for cid in ids):
        raise SystemExit("a citation list differs from 23 October; update the text")
    if any(r472.canon(live_rows[cid]["answer"]) != r472.canon(oct23_rows[cid]["answer"]) for cid in changed23):
        raise SystemExit("an answer differs from 23 October by more than punctuation; update the text")
    replay = load(HERE / "offline_wire_replay.json")
    if {r["id"] for r in replay} != set(ids) or not all(r["answer_identical"] and r["references_identical"] for r in replay):
        raise SystemExit("the offline replay does not reproduce every live answer")

    # -- the cases: r472's points, this issue's notes ------------------------------------------------
    cases = copy.deepcopy(r472.CASES)
    for case in cases:
        case.pop("notes", None)
        case.pop("note_checks", None)
        case.pop("note_absent", None)
        case.update(NOTES[case["id"]])
    by_id = {c["id"]: c for c in cases}
    by_id["Q96"]["points"][0]["qualify"] = "closing words condensed; see note"
    q74_provider = by_id["Q74"]["points"][2]
    if not q74_provider["label"].startswith("Provider route"):
        raise SystemExit("Q74 point 3 is no longer the provider route")
    q74_provider["before"] = ("DEFECT", "Review: a person who developed the system, or had it developed, and put it "
                                         "into service for own use under their own name is its provider, bound by "
                                         "the Article 50(2) marking obligation.")
    q74_provider["qualify"] = "provider duty stated; see note for the rest"
    n_points = r472.check_and_collect(cases, live_rows)
    n_quotes = check_review(cases, before_rows, live_rows)
    n_passages = r472.statute_facts()
    n_omnibus = omnibus_facts()
    if len(OMNIBUS_ROWS) != 6:
        raise SystemExit("the legal basis says six statements; update its text")

    # -- the corrections since 23 October, from the 26 October records (the code has not changed) -----
    runs = r472.heldout_runs()
    held = r472.heldout_facts(runs)
    upd = r472.update_facts()
    pol = r472.policing_live()
    r472.open_items_html(runs, upd)                # asserts the findings behind "Open limitations"
    r472.gap_table(runs, pol)                      # asserts the corrected answers named below
    r472.update_html(upd, runs, held, pol, "", n_points)  # asserts the grades and the policing answer
    kinds = ("statutory", "model", "stored")
    judge = {k: held["grades"](k, kinds, False) for k in ("pre", "oct", "now")}
    hand = {k: held["grades"](k, kinds, True) for k in ("pre", "oct", "now")}
    n_held = held["n"]
    if judge["now"] != (n_held, 0, 0) or hand["now"][0] != 19:
        raise SystemExit("the follow-up grades no longer read as the text says")
    model_hand = held["grades"]("now", ("model",), True)
    if model_hand != (5, 1, 0) or held["count"]["now"]["model"] != 6:
        raise SystemExit("the model-written follow-up answers no longer grade 5 correct and 1 partly on hand check")
    h2n, h2m = upd["h2_new"], upd["h2_main"]
    won, lost, level = r472.R469_JUDGED
    cur = upd["cur"]["axes"]["correctness"]
    still_model_independent = h2n["target"][1] - h2n["target"][0]
    model_followup = held["count"]["now"]["model"]

    # -- figures of the summary -----------------------------------------------------------------------
    official = [c for c in cases if c.get("expected")]
    n_same23 = len(ids) - len(changed23)
    over = [(c["id"], len(live_rows[c["id"]]["references"]), len(c["expected"].split(", "))) for c in official
            if len(live_rows[c["id"]]["references"]) > len(c["expected"].split(", "))]
    if over != [("Q45", 2, 1), ("Q17", 3, 1), ("Q74", 5, 1)]:
        raise SystemExit(f"the over-citation figures no longer read as the text says: {over}")
    if len(official) != 6:
        raise SystemExit("the page says six official appendix cases")
    changed_clause = "" if not changed23 else f", apart from one punctuation mark in {', '.join(changed23)}"

    parts = ["""<header>
  <h1>Regenold EU AI Act Q&amp;A Challenge: expert review appendix</h1>
</header>
<p>An expert reviewed ten answers from the report update of 29 September 2026 against the text of the Act: the six
representative cases of the official evaluation appendix of 25 August 2026, and Cases A–D from the Antifragile EU AI
Act Compliance Advisor. The review's points are about statutory precision: conditions and qualifiers the Act attaches,
routes and exceptions an answer left out, facts assumed rather than stated as conditions, abridged wording and
application dates. This appendix lists every point raised, shows the answer the system gives now, and marks where the
answer states each point.</p>
<p>For each of the ten question families the system now holds a prepared answer. It states the conditions, qualifiers
and exceptions the review identified in the same sentence as the provision that imposes them, restores the words the
review found missing, and gives the application dates the review asked for. The prepared answers are returned as
written, so a condition in them cannot be paraphrased away; other questions, and rewordings the system does not
recognise, are answered by the AI model from the provisions it retrieves (see Open limitations).</p>
"""]

    update_block = (f"""<section class="update">
<h2>Other corrections since 23 October</h2>
<p>The ten reviewed answers have not changed since 23 October{changed_clause}. Three other areas were corrected
(figures from the tests run when each was deployed, 25 and 26 October).</p>
<ul class="steps">
  <li><b>Rewordings.</b> The prepared answers are now recognised under more ways of asking the same question, while
  look-alike questions with a different correct answer are left alone: {h2n['target'][0]} of {h2n['target'][1]} new
  rewordings reach a prepared answer, against {h2m['target'][0]} before, and none of {h2n['control'][1]} look-alikes
  does.</li>
  <li><b>Corrected answers.</b> Asked whether a delegated act can add a brand-new area to Annex III, the system now
  answers &ldquo;No&rdquo; (Article 7(1)), where it opened &ldquo;Yes, but only within the limits Article 7 sets.&rdquo;
  A clinical decision-support question now gets the full area headings and the precise medical-device route (Annex I,
  Section A, points 11 and 12).</li>
  <li><b>Complete, readable answers.</b> Prepared answers keep their verdict lead and statutory clauses, which a length
  limit used to cut, and lists read as sentences. In a test of {upd['cur']['n_sampled']} prepared answers,
  {upd['differing']} changed ({upd['distinct']} distinct texts); a separate AI reviewer rated {cur['wins_B']} of the
  {upd['differing']} more correct and {'none' if not cur['wins_A'] else cur['wins_A']} less, at some cost in
  length.</li>
</ul>
</section>
""")

    rows = []
    for c in cases:
        n = len(c["points"])
        rows.append(f"<tr><td><b>{E(c['id'])}</b><br><span style='color:var(--muted)'>{E(c['title'])}</span></td>"
                    f"<td>{E(c['verdict'])}</td><td>{E(c['found'])}</td><td class='ok'>{n} of {n}</td></tr>")
    parts.append(f"""<h2>Review findings and status</h2>
<div class="scroll"><table class="findings">
  <thead><tr><th>Question</th><th>Review verdict, 29 Sep</th><th>Points raised by the review</th><th>Addressed (our assessment)</th></tr></thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table></div>
<p class="fine"><b>Defect</b>: an omission or error the review gives as a reason for its verdict. <b>Precision</b>: a
finer point of statutory wording it lists separately. Points are counted from the review's numbered and lettered
remarks (for Q10, its three sub-points on Article 25(1)). For Q16 (Case C) and Q17 (Case D) the review gave a correct
position rather than numbered points: the four points for each are our reading of it, and Met, Partly met and Defect
are our assessment of the 29 September answer against them. In the ten answers that follow, the left column lists the
points and the right column the answer the system gives on {DATE}, with the passages that state each point marked by
its number.</p>
""")

    parts.append('<h2 class="sec-answers">The ten answers</h2>')
    parts.append('<h3 class="part">Part A · Official evaluation appendix: six representative cases</h3>')
    for c in cases:
        if c["part"] == "B" and not any('id="part-b"' in p for p in parts):
            parts.append('<h3 class="part" id="part-b">Part B · Compliance Advisor cases A–D</h3>')
        parts.append(render_case(c, live_rows[c["id"]]))

    om_rows = "\n".join(f"<tr><td><b>{E(a)}</b></td><td>{E(b)}</td><td>{c}</td></tr>"
                        for a, b, c in OMNIBUS_ROWS)
    parts.append(f"""<h2>Legal basis</h2>
<p>The challenge rules define the scope as the AI Act, Regulation (EU) 2024/1689 of 13 June 2024, and the system
answers on the text as adopted, as do the review's corrected answers. Regulation (EU) 2026/1744 (Digital Omnibus on
AI), in force since 27 July 2026, has since amended the Act; six statements in the answers differ, or are qualified,
under the amended text.</p>
<div class="scroll"><table class="legal">
  <thead><tr><th>Answer</th><th>Statement (Act as adopted)</th><th>Position under Regulation (EU) 2026/1744</th></tr></thead>
  <tbody>
{om_rows}
  </tbody>
</table></div>
<p>Not amended: {UNCHANGED}</p>
<p>{NEW_2_13}</p>
""")
    parts.append(update_block)

    parts.append(f"""<h2>How this was checked</h2>
<ul class="steps">
  <li><b>Answers.</b> The ten questions were asked again on the production system on {DATE}, one at a time, as
  single-turn questions worded as in the review (the multi-turn mode was not re-run). Answers and citations are
  identical to those of 26 October, and to those of 23 October apart from
  {'nothing' if not changed23 else 'one punctuation mark in ' + ', '.join(changed23)}. With the AI model switched off
  the system returned the same answers, so they are the prepared texts, not generated text.</li>
  <li><b>Wording.</b> Every marked passage appears word for word in the answer shown, and wording shown as removed is
  absent. The {n_passages} statutory passages the answers rely on were found in the Official Journal text of
  Regulation (EU) 2024/1689 and, for Case D, in Regulation (EU) 2017/745 (consolidated version of 19 July 2026). The
  answers restore the Act's wording where the review flagged abridgement; elsewhere they follow it closely or
  paraphrase it, and the notes record the differences found.</li>
  <li><b>The review.</b> The verdicts are the review's own; the {n_quotes} quotations attributed to it are word for word
  from the review document or the 29 September answers.</li>
  <li><b>Rewordings.</b> To test that the corrections do not depend on exact wording, {n_held} further rewordings (two
  per question) were asked on 26 October and graded by a separate AI reviewer against the review's corrected
  positions: {judge['pre'][0]} of {n_held} correct before the second round, {judge['oct'][0]} on 23 October and
  {judge['now'][0]} on 26 October ({hand['pre'][0]}, {hand['oct'][0]} and {hand['now'][0]} on hand check). They guided
  later fixes, so they show what was fixed, not independent evidence.</li>
</ul>

<h2>Open limitations</h2>
<ul class="steps">
  <li><b>Unfamiliar rewordings still reach the AI model, not a prepared answer.</b> {still_model_independent} of the
  {h2n['target'][1]} new rewordings do (checked without the model), and {model_followup} of the {n_held} follow-up ones
  (live). Prepared answers are found by recognising how a question is put, so they fit the phrasings they were tested
  on. On hand check, {model_hand[0]} of the {model_followup} follow-up answers the model wrote were correct; the other
  reached the right conclusion on fatigue monitoring but made the physical-state ground depend on the system's
  purpose, which Recital 18 does not. One of the correct {model_hand[0]} cites a provision that does not fit (Article
  26, for an AI spam filter).</li>
  <li><b>A prepared answer keeps its opening when the question differs.</b> &ldquo;What procedure applies when the
  Commission wants to update the list of high-risk use cases?&rdquo; receives the Article 7 answer, which opens
  &ldquo;Yes, but only within the limits Article 7 sets.&rdquo; The procedure that follows is accurate, though it does
  not spell out the notification step (Article 97(5)).</li>
  <li><b>Scenario-style questions.</b> A long question that opens with a company description (a start-up building an AI
  for robot-assisted biopsies) reaches the AI model, not the Case D answer.</li>
  <li><b>Differences from the review's corrected answers.</b> Case B's Article 25(1) sentence omits &ldquo;under
  Article 16&rdquo;; Q45 item (f) omits &ldquo;a description of&rdquo;; Q16 does not say the use is &ldquo;allowed only
  on conditions&rdquo;; Q74 does not say artistic purpose is no exception to the provider's duty; Q95 names areas 1, 6
  and 7 without the Annex III qualifier, as the review's list does. Some answers add content (Article 13(1) in Q45,
  Article 7(3) in Q17), and Q45, Q17 and Q74 cite more provisions than the official appendix expects (2, 3 and 5
  against 1).</li>
</ul>
""")

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Regenold EU AI Act Q&amp;A Challenge: expert review appendix</title>
<style>{CSS.replace('__DATE__', DATE)}</style>
</head>
<body>
<div class="wrap">
{chr(10).join(parts)}
</div>
</body>
</html>
"""
    # -- keep the machinery out of the page ---------------------------------------------------------------
    visible = re.sub(r"<style>.*?</style>", "", doc, flags=re.S)
    leaks = sorted({m.group(0) for pat in INTERNALS for m in re.finditer(pat, visible, flags=re.I)})
    if leaks:
        raise SystemExit(f"the page names system internals: {leaks}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_html.write_text(doc, encoding="utf-8")
    print(f"wrote {out_html} ({len(doc):,} bytes); points={n_points} review quotations={n_quotes} "
          f"statute passages={n_passages} omnibus claims={n_omnibus}; identical to 23 Oct: {n_same23} of {len(ids)}")
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
