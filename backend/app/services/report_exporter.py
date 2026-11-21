"""PDF and Multi-Sheet Excel (.xlsx) Exporters for Data Analyst Validation Reports."""

from __future__ import annotations

import os
import textwrap
import uuid
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
import pymupdf

from app.schemas import ValidationReportResponse


def _atomic_temp_path(output_path: Path) -> Path:
    return output_path.with_name(
        f".{output_path.stem}.{uuid.uuid4().hex[:8]}.tmp{output_path.suffix}"
    )


def export_validation_report_pdf(
    report: ValidationReportResponse,
    project_name: str,
    output_path: Path,
) -> Path:
    """Render a multi-section Data Analyst Validation Audit Report to PDF via PyMuPDF."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    tmp_path = _atomic_temp_path(output_path)

    try:
        page = doc.new_page(width=595, height=842)
        y = 50.0

        def _ensure_space(needed: float = 20.0) -> None:
            nonlocal page, y
            if y + needed > 790.0:
                page = doc.new_page(width=595, height=842)
                y = 50.0

        def _write_line(
            text: str, size: float = 10.0, bold: bool = False, indent: float = 45.0
        ) -> None:
            nonlocal y
            font = "hebo" if bold else "helv"
            wrapped = textwrap.wrap(text, width=92) or [""]
            for chunk in wrapped:
                _ensure_space(size + 6.0)
                page.insert_text((indent, y), chunk, fontsize=size, fontname=font)
                y += size + 5.0

        _write_line("MediExtract SPSS - Data Analyst Validation Audit Report", size=14.0, bold=True)
        _write_line(f"Project: {project_name} ({report.project_id})", size=10.0)
        _write_line(f"Schema Version: {report.schema_version} | Filters: {report.filters_applied}", size=9.0)
        y += 8.0

        _write_line("1. Executive Quality Summary", size=11.5, bold=True)
        s = report.summary
        _write_line(
            f"Cases Evaluated: {s.total_cases_evaluated} | Clean Cases: {s.clean_cases_count} "
            f"| Clean Rate: {s.clean_rate_pct}% | Flagged: {s.flagged_cases_count} "
            f"| Duplicates Prevented: {s.duplicates_prevented}",
            size=10.0,
        )
        if report.narrative_summary:
            _write_line(report.narrative_summary, size=9.5, indent=50.0)
        y += 6.0

        _write_line("2. Demographics & Digit-Preference Audit", size=11.5, bold=True)
        d = report.demographics_audit
        _write_line(
            f"Age Mean: {d.age_mean} | Median: {d.age_median} | Min/Max: {d.age_min}/{d.age_max} "
            f"| Outliers: {d.age_outliers_count} | Whipple Index: {d.digit_preference_whipple_index}",
            size=10.0,
        )
        _write_line(f"Sex Distribution: {d.sex_distribution}", size=10.0)
        y += 6.0

        _write_line("3. Variable Missingness Audit", size=11.5, bold=True)
        if not report.missingness_audit:
            _write_line("No missing values detected in audited variables.", size=9.5)
        else:
            for item in report.missingness_audit:
                _write_line(
                    f"- {item.variable}: {item.missing_count} missing ({item.missing_pct}%) [{item.severity.value}]",
                    size=9.5,
                    indent=55.0,
                )
        y += 6.0

        _write_line("4. Leading Morbidities & Polypharmacy", size=11.5, bold=True)
        _write_line(f"Mean Prescribed Drugs per Encounter: {report.clinical_audit.mean_drugs_per_encounter}", size=10.0)
        for dx in report.clinical_audit.top_diagnoses[:10]:
            _write_line(
                f"- [{int(dx.code)}] {dx.label}: {dx.count} ({dx.pct}%)",
                size=9.5,
                indent=55.0,
            )
        y += 6.0

        _write_line("5. Clinical Contradictions & VR-04-RX Prescription Audit", size=11.5, bold=True)
        if not report.clinical_audit.contradictions_found:
            _write_line("No rule contradictions or VR-04-RX mismatches detected.", size=9.5)
        else:
            for c in report.clinical_audit.contradictions_found[:100]:
                _write_line(
                    f"- Case #{c.case_index} [{c.rule_id}]: {c.description}",
                    size=9.0,
                    indent=55.0,
                )
        y += 6.0

        _write_line("6. Health Facility Clean-Data Ranking", size=11.5, bold=True)
        for fac in report.facility_ranking:
            _write_line(
                f"- {fac.facility}: {fac.cases} cases | Clean Rate: {fac.clean_rate_pct}%",
                size=9.5,
                indent=55.0,
            )

        doc.save(str(tmp_path))
        doc.close()
        os.replace(tmp_path, output_path)
    except Exception:
        doc.close()
        tmp_path.unlink(missing_ok=True)
        raise
    return output_path


_HEADER_FILL = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_WRAP_ALIGN = Alignment(vertical="center", wrap_text=True)
_BLOCKER_FILL = PatternFill(start_color="FDE2E1", end_color="FDE2E1", fill_type="solid")
_BLOCKER_FONT = Font(bold=True, color="991B1B")
_WARNING_FILL = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
_WARNING_FONT = Font(color="92400E")


def _style_worksheet(ws: openpyxl.worksheet.worksheet.Worksheet) -> None:
    """Apply dark slate header bar, freeze panes, wrap text, and auto-fit column widths."""
    ws.freeze_panes = "A2"
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _WRAP_ALIGN

    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for idx, cell in enumerate(col):
            if idx > 0:
                cell.alignment = _WRAP_ALIGN
            text = "" if cell.value is None else str(cell.value)
            longest_line = max((len(part) for part in text.splitlines()), default=0)
            if longest_line > max_len:
                max_len = longest_line
        ws.column_dimensions[col_letter].width = min(60, max(12, max_len + 4))


def export_validation_report_xlsx(
    report: ValidationReportResponse,
    project_name: str,
    output_path: Path,
) -> Path:
    """Export Validation Audit Report into a styled 5-sheet Excel workbook."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()

    ws_sum = wb.active
    ws_sum.title = "Summary"
    ws_sum.append(["Metric", "Value"])
    ws_sum.append(["Project ID", report.project_id])
    ws_sum.append(["Project Name", project_name])
    ws_sum.append(["Filters Applied", str(report.filters_applied)])
    ws_sum.append(["Total Cases Evaluated", report.summary.total_cases_evaluated])
    ws_sum.append(["Clean Cases", report.summary.clean_cases_count])
    ws_sum.append(["Clean Rate (%)", report.summary.clean_rate_pct])
    ws_sum.append(["Flagged Cases", report.summary.flagged_cases_count])
    ws_sum.append(["Duplicates Prevented", report.summary.duplicates_prevented])
    ws_sum.append(["Age Mean", report.demographics_audit.age_mean])
    ws_sum.append(["Age Median", report.demographics_audit.age_median])
    ws_sum.append(["Age Outliers", report.demographics_audit.age_outliers_count])
    ws_sum.append(["Whipple Digit-Preference Index", report.demographics_audit.digit_preference_whipple_index])
    ws_sum.append(["Mean Drugs per Encounter", report.clinical_audit.mean_drugs_per_encounter])
    if report.narrative_summary:
        ws_sum.append(["Narrative Summary", report.narrative_summary])

    ws_miss = wb.create_sheet("Missingness")
    ws_miss.append(["Variable", "Missing Count", "Missing (%)", "Severity"])
    for m in report.missingness_audit:
        ws_miss.append([m.variable, m.missing_count, m.missing_pct, m.severity.value])
        sev_cell = ws_miss.cell(row=ws_miss.max_row, column=4)
        if m.severity.value == "BLOCKER":
            sev_cell.fill = _BLOCKER_FILL
            sev_cell.font = _BLOCKER_FONT
        elif m.severity.value == "WARNING":
            sev_cell.fill = _WARNING_FILL
            sev_cell.font = _WARNING_FONT

    ws_dx = wb.create_sheet("Top_Diagnoses")
    ws_dx.append(["Code", "Diagnosis Label", "Count", "Pct (%)"])
    for d in report.clinical_audit.top_diagnoses:
        ws_dx.append([d.code, d.label, d.count, d.pct])

    ws_con = wb.create_sheet("Contradictions_Audit")
    ws_con.append(["Case Index", "Rule ID", "Description"])
    for c in report.clinical_audit.contradictions_found:
        ws_con.append([c.case_index, c.rule_id, c.description])

    ws_fac = wb.create_sheet("Facility_Ranking")
    ws_fac.append(["Facility", "Cases", "Clean Rate (%)"])
    for f in report.facility_ranking:
        ws_fac.append([f.facility, f.cases, f.clean_rate_pct])

    for sheet in (ws_sum, ws_miss, ws_dx, ws_con, ws_fac):
        _style_worksheet(sheet)

    tmp_path = _atomic_temp_path(output_path)
    try:
        wb.save(str(tmp_path))
        os.replace(tmp_path, output_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return output_path
