/**
 * MediExtract — Screen 07: The Intelligence & Export Hub
 * Filtering, Descriptive Charts, Report Builder, Privacy & Authentic Export
 */

export function applyExportFilters(records, filters) {
  return records.filter((r) => {
    if (filters.sex !== "ALL" && String(r.Sex || "") !== filters.sex) return false;
    if (filters.diagnosis !== "ALL" && String(r.Diagnosis1 || "") !== filters.diagnosis) return false;
    if (filters.facility !== "ALL" && String(r.Facility_Code || "") !== filters.facility) return false;
    if (filters.ageMin !== "" && !Number.isNaN(Number(filters.ageMin))) {
      const a = Number(r.Age);
      if (Number.isNaN(a) || a < Number(filters.ageMin)) return false;
    }
    if (filters.ageMax !== "" && !Number.isNaN(Number(filters.ageMax))) {
      const a = Number(r.Age);
      if (Number.isNaN(a) || a > Number(filters.ageMax)) return false;
    }
    return true;
  });
}

export function buildAnonymisedCopy(records, anonConfig) {
  return records.map((rec, idx) => {
    const copy = { ...rec };
    if (anonConfig.pseudonymiseIds && copy.Respondent_ID !== undefined) {
      copy.Respondent_ID = `ANON-${String(idx + 1).padStart(4, "0")}`;
    } else if (anonConfig.removeDirectIds) {
      delete copy.Respondent_ID;
      delete copy.sourceClerk;
    }
    if (anonConfig.excludeNotes) {
      delete copy.Encounter_Date;
    }
    return copy;
  });
}

export function generateCsvContent(records, variables, includeLabels) {
  const cols = variables.filter((v) => records.some((r) => v.name in r));
  const header = cols.map((c) => `"${c.name}"`).join(",");
  const lines = [header];
  for (const r of records) {
    const row = cols.map((v) => {
      let val = r[v.name] ?? "";
      if (includeLabels && v.valueLabels && v.valueLabels[String(val)]) {
        val = v.valueLabels[String(val)];
      }
      return `"${String(val).replace(/"/g, '""')}"`;
    });
    lines.push(row.join(","));
  }
  return lines.join("\r\n");
}

export function generateSpsSyntax(variables, datasetName) {
  const lines = [
    `* MediExtract SPSS Syntax (.sps) — Generated ${new Date().toISOString()}.`,
    `* Dataset: ${datasetName}.`,
    "",
    "VARIABLE LABELS"
  ];
  for (const v of variables) {
    lines.push(`  ${v.name} "${v.label.replace(/"/g, "'")}"`);
  }
  lines.push(".");
  lines.push("");
  for (const v of variables) {
    if (v.valueLabels) {
      const pairs = Object.entries(v.valueLabels)
        .map(([k, lbl]) => `${Number.isNaN(Number(k)) ? `'${k}'` : k} '${lbl.replace(/'/g, "''")}'`)
        .join(" ");
      lines.push(`VALUE LABELS ${v.name} ${pairs}.`);
    }
  }
  lines.push("");
  for (const v of variables) {
    lines.push(`VARIABLE LEVEL ${v.name} (${v.measure.toUpperCase()}).`);
  }
  return lines.join("\r\n");
}

export function renderExportHubScreen(state, callbacks) {
  const eh = state.exportHub;
  const project = state.projects.find((p) => p.id === state.activeProjectId) || null;
  const batch = state.batches.find((b) => b.id === state.activeBatchId) || null;
  const records = state.observatory.records || [];
  const variables = state.studio.variables;

  const filtered = applyExportFilters(records, eh.filters);

  // Header metadata
  document.getElementById("eh-project-name").textContent = project ? project.name : "No Project Selected";
  document.getElementById("eh-dataset-name").textContent = batch ? `${batch.reference} — ${batch.name}` : "Local Session Dataset";
  document.getElementById("eh-rec-count").textContent = String(records.length);
  document.getElementById("eh-var-count").textContent = String(variables.length);
  document.getElementById("eh-val-status").textContent = state.observatory.validationStatus.replace(/_/g, " ");
  document.getElementById("eh-approval-status").textContent = state.observatory.supervisorApproved
    ? "Approved for analysis"
    : "Draft / Unapproved";

  // Populate dynamic filter dropdowns from actual records
  populateFilterSelect("eh-filter-sex", records.map((r) => r.Sex).filter(Boolean), eh.filters.sex, "All Sex Values");
  populateFilterSelect("eh-filter-diag", records.map((r) => r.Diagnosis1).filter(Boolean), eh.filters.diagnosis, "All Diagnoses");
  populateFilterSelect("eh-filter-fac", records.map((r) => r.Facility_Code).filter(Boolean), eh.filters.facility, "All Facilities");

  document.getElementById("eh-subset-count").textContent =
    `Original: ${records.length} record(s) · Filtered Subset: ${filtered.length} record(s)`;

  // Charts
  renderCharts(filtered, variables);

  // Report Preview
  renderReportPreview(state, project, batch, records, filtered, eh);

  // Export Readiness & Anonymisation Preview
  renderExportReadiness(state, records, filtered, eh);

  // Export History
  renderExportHistory(eh.history);
}

function populateFilterSelect(id, values, currentVal, allLabel) {
  const sel = document.getElementById(id);
  const uniq = Array.from(new Set(values)).sort();
  sel.innerHTML =
    `<option value="ALL">${escapeHtml(allLabel)}</option>` +
    uniq.map((v) => `<option value="${escapeHtml(v)}" ${v === currentVal ? "selected" : ""}>${escapeHtml(v)}</option>`).join("");
}

function renderCharts(filtered, variables) {
  const container = document.getElementById("eh-charts-grid");
  if (filtered.length === 0) {
    container.innerHTML = `<div style="grid-column:1/-1; padding:18px; border:1px dashed var(--rule-strong); border-radius:var(--radius-sm); color:var(--ink-secondary); font-size:13px;">No matching records available for descriptive charts. Load records or adjust filters.</div>`;
    return;
  }

  const diagChart = buildFreqChartHtml("Primary Diagnosis (Diagnosis1)", filtered, "Diagnosis1", variables.find((v) => v.name === "Diagnosis1"));
  const treatChart = buildFreqChartHtml("Primary Treatment (Treatment1)", filtered, "Treatment1", null);
  const sexChart = buildFreqChartHtml("Sex Distribution (Sex)", filtered, "Sex", variables.find((v) => v.name === "Sex"));
  const ageChart = buildAgeHistogramHtml(filtered);

  container.innerHTML = diagChart + treatChart + sexChart + ageChart;
}

function buildFreqChartHtml(title, records, field, varDef) {
  const counts = new Map();
  for (const r of records) {
    const raw = r[field] !== undefined && String(r[field]).trim() !== "" ? String(r[field]) : "(Missing)";
    const label = varDef?.valueLabels?.[raw] || raw;
    counts.set(label, (counts.get(label) || 0) + 1);
  }
  const sorted = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const maxVal = Math.max(1, ...sorted.map((x) => x[1]));

  return `
    <div class="eh-chart-card">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <strong style="font-size:13px;">${escapeHtml(title)}</strong>
        <span class="mono-tag">n=${records.length}</span>
      </div>
      ${sorted
        .map(
          ([lbl, c]) => `
        <div class="eh-bar-row" title="${escapeHtml(lbl)}: ${c}">
          <span class="eh-bar-label">${escapeHtml(lbl)}</span>
          <div class="eh-bar-track"><div class="eh-bar-fill" style="width:${Math.round((c / maxVal) * 100)}%"></div></div>
          <span class="mono-tag" style="text-align:right;">${c}</span>
        </div>`
        )
        .join("")}
    </div>
  `;
}

function buildAgeHistogramHtml(records) {
  const buckets = [
    { label: "0–14 yrs", count: 0 },
    { label: "15–24 yrs", count: 0 },
    { label: "25–49 yrs", count: 0 },
    { label: "50–115 yrs", count: 0 },
    { label: "Out of range / NA", count: 0 }
  ];
  for (const r of records) {
    const a = Number(r.Age);
    if (r.Age === undefined || r.Age === "" || Number.isNaN(a) || a < 0 || a > 115) {
      buckets[4].count++;
    } else if (a <= 14) buckets[0].count++;
    else if (a <= 24) buckets[1].count++;
    else if (a <= 49) buckets[2].count++;
    else buckets[3].count++;
  }
  const maxVal = Math.max(1, ...buckets.map((b) => b.count));

  return `
    <div class="eh-chart-card">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <strong style="font-size:13px;">Age Distribution (Age)</strong>
        <span class="mono-tag">n=${records.length}</span>
      </div>
      ${buckets
        .map(
          (b) => `
        <div class="eh-bar-row">
          <span class="eh-bar-label">${escapeHtml(b.label)}</span>
          <div class="eh-bar-track"><div class="eh-bar-fill" style="width:${Math.round((b.count / maxVal) * 100)}%; background:var(--bg-forest);"></div></div>
          <span class="mono-tag" style="text-align:right;">${b.count}</span>
        </div>`
        )
        .join("")}
    </div>
  `;
}

function renderReportPreview(state, project, batch, records, filtered, eh) {
  const sheet = document.getElementById("eh-report-preview");
  if (!eh.reportGenerated) {
    sheet.innerHTML = `<span class="mono-tag" style="color:var(--ink-muted);">Select report sections above and click <strong>Generate Report Preview</strong> to compile descriptive tables from actual records.</span>`;
    return;
  }

  const sections = [];
  if (eh.sections.profile) {
    sections.push(`
      <div style="margin-bottom:14px;">
        <h4 style="margin:0 0 4px;">1. Dataset Profile</h4>
        <p style="margin:0; font-size:13px; color:var(--ink-secondary);">
          Total source records: <strong>${records.length}</strong> · Filtered subset: <strong>${filtered.length}</strong> · Variables: <strong>${state.studio.variables.length}</strong>.
        </p>
      </div>`);
  }
  if (eh.sections.demographic) {
    const males = filtered.filter((r) => String(r.Sex || "").toLowerCase() === "male").length;
    const females = filtered.filter((r) => String(r.Sex || "").toLowerCase() === "female").length;
    sections.push(`
      <div style="margin-bottom:14px;">
        <h4 style="margin:0 0 4px;">2. Demographic Overview</h4>
        <p style="margin:0; font-size:13px; color:var(--ink-secondary);">
          Female: <strong>${females}</strong> · Male: <strong>${males}</strong> · Unspecified/Other: <strong>${Math.max(0, filtered.length - males - females)}</strong> (descriptive counts only).
        </p>
      </div>`);
  }
  if (eh.sections.clinical) {
    const uniqDiag = new Set(filtered.map((r) => r.Diagnosis1).filter(Boolean)).size;
    const uniqTreat = new Set(filtered.map((r) => r.Treatment1).filter(Boolean)).size;
    sections.push(`
      <div style="margin-bottom:14px;">
        <h4 style="margin:0 0 4px;">3. Clinical Overview</h4>
        <p style="margin:0; font-size:13px; color:var(--ink-secondary);">
          Distinct primary diagnoses observed: <strong>${uniqDiag}</strong> · Distinct primary treatments observed: <strong>${uniqTreat}</strong>. No clinical causality inferred.
        </p>
      </div>`);
  }
  if (eh.sections.geographic) {
    const facs = Array.from(new Set(filtered.map((r) => r.Facility_Code).filter(Boolean))).join(", ") || "None";
    sections.push(`
      <div style="margin-bottom:14px;">
        <h4 style="margin:0 0 4px;">4. Geographic / Facility Overview</h4>
        <p style="margin:0; font-size:13px; color:var(--ink-secondary);">Reporting facilities in subset: <strong>${escapeHtml(facs)}</strong>.</p>
      </div>`);
  }
  if (eh.sections.quality) {
    const unresolved = state.observatory.issues.filter((i) => i.resolutionStatus === "UNRESOLVED").length;
    sections.push(`
      <div style="margin-bottom:14px;">
        <h4 style="margin:0 0 4px;">5. Data Quality Summary</h4>
        <p style="margin:0; font-size:13px; color:var(--ink-secondary);">
          Validation status: <strong>${escapeHtml(state.observatory.validationStatus)}</strong> · Total flagged issues: <strong>${state.observatory.issues.length}</strong> · Unresolved: <strong>${unresolved}</strong>.
        </p>
      </div>`);
  }

  sheet.innerHTML = `
    <div class="eh-report-header">
      <span class="mono-tag">INSTITUTIONAL DESCRIPTIVE REPORT</span>
      <h3 style="margin:4px 0 2px; font-family:var(--font-display); font-size:22px;">${escapeHtml(project?.name || "MediExtract Dataset")} — Analytical Summary</h3>
      <span class="mono-tag">${escapeHtml(batch?.reference || "Local Session")} · Generated ${new Date().toLocaleString()}</span>
    </div>
    ${sections.join("") || "<p>No report sections selected.</p>"}
  `;
}

function renderExportReadiness(state, records, filtered, eh) {
  const scopeRows = eh.config.scope === "FILTERED" ? filtered : records;
  const unresolved = state.observatory.issues.filter(
    (i) => i.resolutionStatus === "UNRESOLVED" || i.resolutionStatus === "ESCALATED"
  ).length;
  const approved = state.observatory.supervisorApproved;

  const badge = document.getElementById("eh-readiness-badge");
  badge.className = approved ? "status-badge verified" : "status-badge amber";
  badge.textContent = approved ? "✓ Approved Analysis Export" : "◷ Draft Export (Unapproved)";

  document.getElementById("eh-readiness-summary").textContent =
    `Scope: ${eh.config.scope === "FILTERED" ? "Filtered Subset" : "Full Dataset"} (${scopeRows.length} rows) · Format: ${eh.config.format.toUpperCase()} · Unresolved Issues: ${unresolved}`;

  const anonPreview = document.getElementById("eh-anon-preview");
  if (scopeRows.length === 0) {
    anonPreview.textContent = "No records available to preview.";
  } else {
    const sample = buildAnonymisedCopy(scopeRows.slice(0, 2), eh.config.anonymisation);
    anonPreview.textContent = JSON.stringify(sample[0], null, 2);
  }
}

function renderExportHistory(history) {
  const tbody = document.getElementById("eh-history-tbody");
  const emptyEl = document.getElementById("eh-history-empty");
  const tableWrap = document.getElementById("eh-history-table-wrap");

  if (history.length === 0) {
    tableWrap.hidden = true;
    emptyEl.hidden = false;
    return;
  }

  emptyEl.hidden = true;
  tableWrap.hidden = false;
  tbody.innerHTML = "";
  for (const h of history) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(h.filename)}</strong></td>
      <td class="mono-tag">${escapeHtml(h.format)}</td>
      <td class="mono-tag">${escapeHtml(h.scope)}</td>
      <td class="mono-tag">${escapeHtml(h.timestamp)}</td>
      <td style="font-size:12px;">${escapeHtml(h.anonSummary)}</td>
      <td>${h.ok ? `<span class="status-badge verified">✓ Generated</span>` : `<span class="status-badge failed">✕ Backend Required</span>`}</td>
      <td style="text-align:right;">
        ${
          h.ok && h.downloadUrl
            ? `<a class="btn btn-sm btn-electric" href="${h.downloadUrl}" download="${escapeHtml(h.filename)}">Download ↓</a>`
            : `<span class="mono-tag" style="color:var(--ink-muted);">${escapeHtml(h.errorNote || "Unavailable")}</span>`
        }
      </td>
    `;
    tbody.appendChild(tr);
  }
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
