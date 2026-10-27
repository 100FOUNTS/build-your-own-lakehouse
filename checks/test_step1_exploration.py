"""Step 1 — did you document what you found in the raw data?

This check cannot know whether your findings are correct (your mentor reviews that with /review 1).
It only verifies that the exploration work exists, has evidence and covers enough types of problem.
Keywords accept English and Spanish, so you can write your notes in either language.
"""

from __future__ import annotations

import re

from conftest import ROOT, ok

NOTE = ROOT / "notes" / "01_findings.md"
PLACEHOLDER = re.compile(r"TODO-(STUDENT|ALUMNO)")

# Broad categories of problems that a good exploratory analysis should touch (generic keywords)
CATEGORIES = {
    "duplicates": r"duplic",
    "units": r"unidad|unit|degf|°f|fahrenheit|\bbar\b|kpa",
    "quality": r"quality|calidad|\bbad\b|uncertain|-9999|centinela|sentinel",
    "outliers": r"pico|spike|outlier|at[ií]pic|an[oó]mal",
    "gaps": r"hueco|\bgap\b|faltan|apag[oó]n|sin datos|vac[ií]o|ausen|missing|blackout|no data|empty|absent",
    "frozen sensor": r"congel|stuck|plano|flat|constante|constant|frozen",
    "defective files": r"corrupt|trunc|ilegible|vac[ií]o|empty|no se pudo leer|unreadable|(could|can)(not| not) be read",
    "time zone / date format": r"zona|offset|utc|huso|time ?zone|formato de fecha|date format|-05:00",
    "column structure": r"orden de (las )?columnas|encabezado|header|columnas? (cambi|distint)|column order|columns? (change|differ)",
    "late arrivals / overlaps": r"tard[ií]|late|solap|overlap|reexport|re-export|fuera de orden|out of order|resend|retransmi",
}


def _findings(text: str) -> list[str]:
    parts = re.split(r"(?m)^### H\d+", text)
    return parts[1:]


def test_exists_and_is_not_the_template():
    ok(NOTE.exists(), "notes/01_findings.md does not exist")
    text = NOTE.read_text()
    ok(not PLACEHOLDER.search(text), "There are still TODO-STUDENT marks in notes/01_findings.md: replace them with your work.")


def test_findings_with_evidence_and_decision():
    findings = _findings(NOTE.read_text())
    ok(len(findings) >= 6, f"Document at least 6 findings with '### H1', '### H2'… (there are {len(findings)}).")
    no_evidence = [i + 1 for i, f in enumerate(findings) if "```" not in f]
    ok(not no_evidence, f"Findings H{no_evidence} have no evidence (a ``` block with the query or code that shows it).")
    no_decision = [i + 1 for i, f in enumerate(findings) if not re.search(r"\*\*Decisi[oó]n:\*\*[ \t]*[^\n]{20,}", f)]
    ok(not no_decision, f"Findings H{no_decision} have no '**Decision:**' with at least one sentence: what will you do about this, and in which layer?")


def test_covers_several_types_of_problem():
    text = NOTE.read_text().lower()
    found = [name for name, rx in CATEGORIES.items() if re.search(rx, text)]
    ok(len(found) >= 6, f"Your notes touch {len(found)} different types of problem and at least 6 are expected. Keep exploring: what else can go wrong in a file like this?")


def test_data_dictionary():
    text = NOTE.read_text()
    m = re.search(r"(?s)## (?:My data dictionary|Mi diccionario de datos)(.*?)(\n## |\Z)", text)
    ok(m, "The '## My data dictionary' section is missing (columns, types, units and grain of each source).")
    body = m.group(1)
    lines = [ln for ln in body.splitlines() if ln.strip() and not PLACEHOLDER.search(ln) and not ln.lstrip().startswith(">")]
    ok(len(lines) >= 6 and sum(len(ln) for ln in lines) >= 350,
       "Your data dictionary is too short: describe the 5 historian columns, the 5 sensors (with their unit) and the 2 reference tables.")
