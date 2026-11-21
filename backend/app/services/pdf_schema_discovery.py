"""Mode B: Auto-discover draft SPSS Variable View schemas from blank questionnaire PDFs."""

from __future__ import annotations

import re

import pymupdf

from app.schemas import MeasureLevel, VariableSchema, VariableType

_CHECKBOX_SPLIT_RE = re.compile(r"(?:\[\s*\]|\(\s*\)|☐|□|○|◯)")
_LEADING_NUM_RE = re.compile(r"^(?:Q?\d{1,2}[.)]\s*)", re.IGNORECASE)
_BLANK_UNDERSCORE_RE = re.compile(r"[_\u2014\u2013-]{3,}|/+")
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")

_DATE_KW_RE = re.compile(r"\b(date|dob|birth|visit_date|encounter_date)\b", re.IGNORECASE)
_SCALE_KW_RE = re.compile(
    r"\b(age|year|month|day|count|score|weight|height|bmi|temp|temperature|pulse|bp|sys|dia|amount|fee|cost)\b",
    re.IGNORECASE,
)
_CODED_NOMINAL_KW_RE = re.compile(
    r"\b(sex|gender|lga|diagnosis|treatment|medication|drug|investigation|lab|test|referral|employer|marital|outcome|status)\b",
    re.IGNORECASE,
)


def validate_pdf_magic_bytes(data: bytes) -> bool:
    """Return True if byte payload starts with the %PDF- magic header."""
    return len(data) >= 5 and data[:5] == b"%PDF-"


def _sanitize_var_name(raw_label: str, used_names: set[str]) -> str:
    cleaned = _LEADING_NUM_RE.sub("", raw_label).strip()
    cleaned = _NON_ALNUM_RE.sub("_", cleaned).strip("_")
    if not cleaned:
        cleaned = "Field"
    if cleaned[0].isdigit():
        cleaned = f"V_{cleaned}"
    base = cleaned[:58]

    candidate = base
    suffix = 2
    while candidate.lower() in used_names:
        candidate = f"{base[:54]}_{suffix}"
        suffix += 1
    used_names.add(candidate.lower())
    return candidate


def _infer_variable_profile(
    label: str, has_options: bool
) -> tuple[VariableType, int, int, MeasureLevel]:
    if has_options:
        return VariableType.NUMERIC, 8, 0, MeasureLevel.NOMINAL
    if _DATE_KW_RE.search(label):
        return VariableType.DATE, 11, 0, MeasureLevel.SCALE
    if _SCALE_KW_RE.search(label):
        return VariableType.NUMERIC, 8, 0, MeasureLevel.SCALE
    if _CODED_NOMINAL_KW_RE.search(label):
        return VariableType.NUMERIC, 8, 0, MeasureLevel.NOMINAL
    return VariableType.STRING, 64, 0, MeasureLevel.NOMINAL


def _extract_checkbox_options(text: str) -> list[str]:
    parts = [p.strip(" :;,-._\t") for p in _CHECKBOX_SPLIT_RE.split(text)]
    options = [p for p in parts if p and len(p) <= 60]
    return options


def discover_schema_from_blank_pdf(pdf_bytes: bytes) -> list[VariableSchema]:
    """Parse a blank questionnaire PDF into a draft SPSS Variable View schema."""
    if not validate_pdf_magic_bytes(pdf_bytes):
        raise ValueError("Invalid PDF signature: file must start with %PDF-")

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    discovered: list[VariableSchema] = []
    used_names: set[str] = set()
    seen_labels: set[str] = set()

    try:
        for page in doc:
            raw_text = page.get_text("text") or ""
            for raw_line in raw_text.splitlines():
                line = " ".join(raw_line.split()).strip()
                if not line or len(line) > 140:
                    continue

                # Skip pure separator lines or page footers
                if re.fullmatch(r"[-_=.\s/]+", line) or re.match(r"^page\s+\d+", line, re.I):
                    continue

                has_checkbox = bool(_CHECKBOX_SPLIT_RE.search(line))
                label_text = ""
                options: list[str] = []

                if ":" in line:
                    head, tail = line.split(":", 1)
                    head_clean = _LEADING_NUM_RE.sub("", head).strip()
                    if not head_clean or len(head_clean) > 64:
                        continue
                    label_text = head_clean
                    if has_checkbox:
                        options = _extract_checkbox_options(tail)
                elif has_checkbox:
                    first_box = _CHECKBOX_SPLIT_RE.search(line)
                    if first_box and first_box.start() > 1:
                        label_text = _LEADING_NUM_RE.sub("", line[: first_box.start()]).strip(" :-")
                        options = _extract_checkbox_options(line[first_box.start() :])
                elif _LEADING_NUM_RE.match(line):
                    cleaned = _LEADING_NUM_RE.sub("", line)
                    cleaned = _BLANK_UNDERSCORE_RE.sub("", cleaned).strip(" :-.")
                    if 2 <= len(cleaned) <= 64:
                        label_text = cleaned

                if not label_text:
                    continue

                norm_label = label_text.lower()
                if norm_label in seen_labels:
                    continue
                seen_labels.add(norm_label)

                var_name = _sanitize_var_name(label_text, used_names)
                var_type, width, decimals, measure = _infer_variable_profile(
                    label_text, has_options=bool(options)
                )
                value_labels = (
                    {f"{float(i + 1)}": opt for i, opt in enumerate(options)}
                    if options
                    else {}
                )

                discovered.append(
                    VariableSchema(
                        index=len(discovered) + 1,
                        name=var_name,
                        type=var_type,
                        width=width,
                        decimals=decimals,
                        label=label_text,
                        value_labels=value_labels,
                        missing_values=[],
                        measure=measure,
                    )
                )

            # Extract structured table column headers if present
            if hasattr(page, "find_tables"):
                try:
                    tables = page.find_tables()
                    for tbl in getattr(tables, "tables", []):
                        rows = tbl.extract() or []
                        if not rows:
                            continue
                        header_row = rows[0] or []
                        for cell in header_row:
                            if not cell:
                                continue
                            header_clean = " ".join(str(cell).split()).strip(" :-")
                            if not header_clean or len(header_clean) > 48:
                                continue
                            if header_clean.lower() in seen_labels:
                                continue
                            seen_labels.add(header_clean.lower())
                            var_name = _sanitize_var_name(header_clean, used_names)
                            var_type, width, decimals, measure = _infer_variable_profile(
                                header_clean, has_options=False
                            )
                            discovered.append(
                                VariableSchema(
                                    index=len(discovered) + 1,
                                    name=var_name,
                                    type=var_type,
                                    width=width,
                                    decimals=decimals,
                                    label=header_clean,
                                    value_labels={},
                                    missing_values=[],
                                    measure=measure,
                                )
                            )
                except Exception:
                    pass
    finally:
        doc.close()

    if not discovered:
        discovered = [
            VariableSchema(
                index=1,
                name="Patient_ID",
                type=VariableType.STRING,
                width=24,
                decimals=0,
                label="Patient / Enrollee Identifier",
                measure=MeasureLevel.NOMINAL,
            ),
            VariableSchema(
                index=2,
                name="Encounter_Date",
                type=VariableType.DATE,
                width=11,
                decimals=0,
                label="Encounter Date",
                measure=MeasureLevel.SCALE,
            ),
            VariableSchema(
                index=3,
                name="Clinical_Notes",
                type=VariableType.STRING,
                width=128,
                decimals=0,
                label="Clinical Notes / Summary",
                measure=MeasureLevel.NOMINAL,
            ),
        ]

    return discovered
