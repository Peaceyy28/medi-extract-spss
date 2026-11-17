/**
 * MediExtract — Screen 06: The Analysis Studio (Dual-View Web SPSS)
 * Data View (Windowed/Virtualized Grid), Variable View, Dataset Overview,
 * Provenance Inspector & Preparation Tools (Auto-Recode)
 */

export const ST_PAGE_SIZE = 50;

export const DEFAULT_STUDIO_VARIABLES = [
  {
    name: "Respondent_ID",
    label: "Unique Encounter / Respondent Identifier",
    type: "String",
    width: 16,
    decimals: 0,
    valueLabels: null,
    missingDef: "None",
    measure: "Nominal",
    role: "ID"
  },
  {
    name: "Age",
    label: "Age of respondent (years)",
    type: "Numeric",
    width: 8,
    decimals: 0,
    valueLabels: null,
    missingDef: "-1, 999",
    measure: "Scale",
    role: "Input"
  },
  {
    name: "Sex",
    label: "Sex of respondent",
    type: "Numeric",
    width: 8,
    decimals: 0,
    valueLabels: { "1": "Male", "2": "Female" },
    missingDef: "9",
    measure: "Nominal",
    role: "Input"
  },
  {
    name: "Diagnosis1",
    label: "Primary clinical diagnosis",
    type: "String",
    width: 24,
    decimals: 0,
    valueLabels: {
      I10: "Essential Hypertension (I10)",
      J06: "Acute Upper Respiratory Infection (J06)",
      O80: "Single Spontaneous Delivery (O80)",
      "M25.5": "Joint / Wrist Pain (M25.5)",
      "1.0": "MSS OF THE WRIST",
      "266.0": "Costochondritis (Musculoskeletal)"
    },
    missingDef: "None",
    measure: "Nominal",
    role: "Input"
  },
  {
    name: "Treatment1",
    label: "Primary prescribed treatment",
    type: "String",
    width: 32,
    decimals: 0,
    valueLabels: null,
    missingDef: "None",
    measure: "Nominal",
    role: "Input"
  },
  {
    name: "Facility_Code",
    label: "Reporting health facility",
    type: "String",
    width: 16,
    decimals: 0,
    valueLabels: {
      "PHC-01": "Regional PHC",
      "PHC-02": "District Annex",
      "PHC-03": "Mobile Outreach"
    },
    missingDef: "None",
    measure: "Nominal",
    role: "Input"
  },
  {
    name: "Encounter_Date",
    label: "Clinical encounter date",
    type: "Date",
    width: 10,
    decimals: 0,
    valueLabels: null,
    missingDef: "None",
    measure: "Scale",
    role: "Input"
  }
];

export const PLANNED_AUTO_RECODES = [
  {
    target: "Age_Group",
    sources: "Age",
    definition: "RECODE Age (0 thru 14 = 1) (15 thru 24 = 2) (25 thru 49 = 3) (50 thru 115 = 4)",
    labels: "1=Pediatric (0–14), 2=Youth (15–24), 3=Adult (25–49), 4=Older Adult (50+)"
  },
  {
    target: "Primary_Disease_Category",
    sources: "Diagnosis1",
    definition: "ICD-10 / OYSHIA Codebook Grouping → NCD, Infectious, Maternal, Musculoskeletal",
    labels: "1=NCD, 2=Infectious, 3=Maternal, 4=Musculoskeletal, 9=Other/Unmapped"
  },
  {
    target: "Comorbidity_Count",
    sources: "Diagnosis1, Diagnosis2",
    definition: "COUNT non-empty distinct diagnosis fields per encounter",
    labels: "0=None, 1=Single Diagnosis, 2=Multiple Diagnoses"
  },
  {
    target: "Polypharmacy_Count",
    sources: "Treatment1, Treatment2",
    definition: "COUNT non-empty prescribed treatment fields per encounter",
    labels: "0=None, 1=Monotherapy, 2+=Multi-drug"
  }
];

export function formatCellPresentation(rawVal, variableDef, showLabels) {
  if (rawVal === undefined || rawVal === null || String(rawVal).trim() === "") {
    return { display: "(Missing)", isMissing: true, label: null };
  }
  const str = String(rawVal);
  if (variableDef?.valueLabels) {
    const mapped = variableDef.valueLabels[str];
    if (mapped) {
      return {
        display: showLabels ? mapped : str,
        isMissing: false,
        label: mapped
      };
    }
  }
  return { display: str, isMissing: false, label: null };
}

export function renderStudioScreen(state, callbacks) {
  const st = state.studio;
  const project = state.projects.find((p) => p.id === state.activeProjectId) || null;
  const batch = state.batches.find((b) => b.id === state.activeBatchId) || null;
  const records = state.observatory.records || [];
  const variables = st.variables;

  // Header metadata
  document.getElementById("st-project-name").textContent = project ? project.name : "No Project Selected";
  document.getElementById("st-dataset-name").textContent = batch ? `${batch.reference} — ${batch.name}` : "Local Session Dataset";
  document.getElementById("st-rec-count").textContent = String(records.length);
  document.getElementById("st-var-count").textContent = String(variables.length);
  document.getElementById("st-val-status").textContent = state.observatory.validationStatus.replace(/_/g, " ");
  document.getElementById("st-updated-at").textContent = st.lastUpdated || "Session active";

  // Sub-tab switching
  ["data", "variables", "overview", "tools"].forEach((tab) => {
    const btn = document.getElementById(`st-subbtn-${tab}`);
    const pane = document.getElementById(`st-pane-${tab}`);
    if (btn) btn.classList.toggle("active", st.activeTab === tab);
    if (pane) pane.hidden = st.activeTab !== tab;
  });

  // Values / Labels toggle
  document.getElementById("st-mode-values").classList.toggle("active", !st.showLabels);
  document.getElementById("st-mode-labels").classList.toggle("active", st.showLabels);

  // Read-only honesty notice & Save button state
  document.getElementById("st-save-btn").disabled = !state.backendConnected;
  document.getElementById("st-readonly-note").textContent = state.backendConnected
    ? "Connected to FastAPI pyreadstat service"
    : "Read-only local inspection (FastAPI pyreadstat offline)";

  renderDataView(st, records, variables, callbacks);
  renderVariableView(variables);
  renderDatasetOverview(state, records, variables);
  renderPreparationTools(st, records, variables, state.backendConnected);
  renderCellInspector(st, records, variables, callbacks);
}

function renderDataView(st, records, variables, callbacks) {
  const emptyEl = document.getElementById("st-data-empty");
  const gridWrap = document.getElementById("st-data-grid-wrap");

  if (records.length === 0) {
    gridWrap.hidden = true;
    emptyEl.hidden = false;
    emptyEl.innerHTML = `
      <h3>No dataset records loaded</h3>
      <p>Connect the FastAPI/pyreadstat backend or load <strong>Dev Preview: Synthetic Fixture</strong> to inspect records in the Dual-View Web SPSS grid.</p>
    `;
    return;
  }

  emptyEl.hidden = true;
  gridWrap.hidden = false;

  const q = (st.search || "").trim().toLowerCase();
  let rows = records.map((r, idx) => ({ rec: r, idx }));
  if (q) {
    rows = rows.filter(({ rec }) =>
      variables.some((v) => String(rec[v.name] ?? "").toLowerCase().includes(q))
    );
  }
  if (st.sortCol) {
    const col = st.sortCol;
    const dir = st.sortDir === "desc" ? -1 : 1;
    rows.sort((a, b) => {
      const va = a.rec[col] ?? "";
      const vb = b.rec[col] ?? "";
      const na = Number(va);
      const nb = Number(vb);
      if (!Number.isNaN(na) && !Number.isNaN(nb) && va !== "" && vb !== "") {
        return (na - nb) * dir;
      }
      return String(va).localeCompare(String(vb)) * dir;
    });
  }

  const maxPage = Math.max(1, Math.ceil(rows.length / ST_PAGE_SIZE));
  if (st.page > maxPage) st.page = maxPage;
  const startIdx = (st.page - 1) * ST_PAGE_SIZE;
  const slice = rows.slice(startIdx, startIdx + ST_PAGE_SIZE);

  const thead = document.getElementById("st-data-thead");
  const tbody = document.getElementById("st-data-tbody");

  thead.innerHTML = "";
  const trHead = document.createElement("tr");
  const thRow = document.createElement("th");
  thRow.style.width = "52px";
  thRow.textContent = "#";
  trHead.appendChild(thRow);

  for (const v of variables) {
    const th = document.createElement("th");
    th.style.width = "140px";
    const arrow = st.sortCol === v.name ? (st.sortDir === "desc" ? " ↓" : " ↑") : "";
    th.textContent = `${v.name}${arrow}`;
    th.title = `${v.label} (${v.type} · ${v.measure})`;
    th.addEventListener("click", () => callbacks.onSortColumn(v.name));
    trHead.appendChild(th);
  }
  thead.appendChild(trHead);

  tbody.innerHTML = "";
  for (const { rec, idx } of slice) {
    const tr = document.createElement("tr");
    const tdNum = document.createElement("td");
    tdNum.className = "st-rownum";
    tdNum.textContent = String(idx + 1);
    tr.appendChild(tdNum);

    for (const v of variables) {
      const td = document.createElement("td");
      const pres = formatCellPresentation(rec[v.name], v, st.showLabels);
      td.textContent = pres.display;
      td.title = pres.display;
      if (pres.isMissing) td.style.color = "var(--ink-muted)";
      if (st.selectedCell && st.selectedCell.rowIdx === idx && st.selectedCell.varName === v.name) {
        td.classList.add("selected-cell");
      }
      td.addEventListener("click", () => callbacks.onSelectCell(idx, v.name));
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }

  const endIdx = Math.min(startIdx + ST_PAGE_SIZE, rows.length);
  document.getElementById("st-page-info").textContent = `Window ${startIdx + 1}–${endIdx} of ${rows.length} (50-row virtualization)`;
  document.getElementById("st-prev-page").disabled = st.page <= 1;
  document.getElementById("st-next-page").disabled = st.page >= maxPage;
}

function renderVariableView(variables) {
  const tbody = document.getElementById("st-var-tbody");
  tbody.innerHTML = "";
  for (const v of variables) {
    const vlText = v.valueLabels
      ? Object.entries(v.valueLabels)
          .map(([k, lbl]) => `${k} ↔ ${lbl}`)
          .join("; ")
      : "None";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(v.name)}</strong></td>
      <td>${escapeHtml(v.label)}</td>
      <td class="mono-tag">${escapeHtml(v.type)}</td>
      <td class="mono-tag">${v.width}</td>
      <td class="mono-tag">${v.decimals}</td>
      <td style="max-width:260px; font-size:12px;">${escapeHtml(vlText)}</td>
      <td class="mono-tag">${escapeHtml(v.missingDef)}</td>
      <td><span class="status-badge">${escapeHtml(v.measure)}</span></td>
      <td class="mono-tag">${escapeHtml(v.role)}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderDatasetOverview(state, records, variables) {
  const numVars = variables.filter((v) => v.type === "Numeric").length;
  const strVars = variables.filter((v) => v.type === "String").length;
  const dateVars = variables.filter((v) => v.type === "Date").length;

  let missingCells = 0;
  for (const r of records) {
    for (const v of variables) {
      if (r[v.name] === undefined || r[v.name] === null || String(r[v.name]).trim() === "") {
        missingCells++;
      }
    }
  }

  document.getElementById("st-ov-records").textContent = String(records.length);
  document.getElementById("st-ov-vars").textContent = String(variables.length);
  document.getElementById("st-ov-types").textContent = `${numVars} Numeric · ${strVars} String · ${dateVars} Date`;
  document.getElementById("st-ov-missing").textContent =
    records.length > 0 ? `${missingCells} empty cell(s)` : "No records loaded";
  document.getElementById("st-ov-measures").textContent =
    `${variables.filter((v) => v.measure === "Scale").length} Scale · ${variables.filter((v) => v.measure === "Nominal").length} Nominal`;
  document.getElementById("st-ov-approval").textContent = state.observatory.supervisorApproved
    ? "Supervisor Approved"
    : state.observatory.validationStatus.replace(/_/g, " ");
}

function renderPreparationTools(st, records, variables, backendConnected) {
  const sel = document.getElementById("st-freq-var");
  if (sel.options.length === 0) {
    sel.innerHTML = variables.map((v) => `<option value="${escapeHtml(v.name)}">${escapeHtml(v.name)} — ${escapeHtml(v.label)}</option>`).join("");
  }
  const targetVar = sel.value || variables[0]?.name;
  const varDef = variables.find((v) => v.name === targetVar);
  const freqEl = document.getElementById("st-freq-results");

  if (records.length === 0) {
    freqEl.innerHTML = `<span class="mono-tag" style="color:var(--ink-muted);">Load dataset records to compute value frequencies and missingness.</span>`;
  } else {
    const counts = new Map();
    for (const r of records) {
      const pres = formatCellPresentation(r[targetVar], varDef, true);
      const key = pres.display;
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    const maxC = Math.max(1, ...counts.values());
    freqEl.innerHTML = Array.from(counts.entries())
      .map(
        ([k, c]) => `
        <div style="margin-bottom:8px;">
          <div style="display:flex; justify-content:space-between; font-size:12.5px;">
            <span>${escapeHtml(k)}</span>
            <span class="mono-tag">${c} (${Math.round((c / records.length) * 100)}%)</span>
          </div>
          <div class="st-freq-bar"><div class="st-freq-fill" style="width:${Math.round((c / maxC) * 100)}%"></div></div>
        </div>`
      )
      .join("");
  }

  // Auto-Recode Table (honest status when backend transformation engine is unavailable)
  const recodeBody = document.getElementById("st-recode-tbody");
  recodeBody.innerHTML = PLANNED_AUTO_RECODES.map(
    (ar) => `
    <tr>
      <td><strong>${escapeHtml(ar.target)}</strong></td>
      <td class="mono-tag">${escapeHtml(ar.sources)}</td>
      <td style="font-size:12px;">${escapeHtml(ar.definition)}</td>
      <td style="font-size:12px;">${escapeHtml(ar.labels)}</td>
      <td><span class="status-badge amber">${backendConnected ? "Ready" : "Pending Backend Engine"}</span></td>
    </tr>`
  ).join("");
}

function renderCellInspector(st, records, variables, callbacks) {
  const emptyEl = document.getElementById("st-insp-empty");
  const bodyEl = document.getElementById("st-insp-body");
  if (!st.selectedCell || !records[st.selectedCell.rowIdx]) {
    emptyEl.hidden = false;
    bodyEl.hidden = true;
    return;
  }

  const rec = records[st.selectedCell.rowIdx];
  const varDef = variables.find((v) => v.name === st.selectedCell.varName) || variables[0];
  const rawVal = rec[varDef.name];
  const pres = formatCellPresentation(rawVal, varDef, true);

  emptyEl.hidden = true;
  bodyEl.hidden = false;
  document.getElementById("st-insp-var").textContent = varDef.name;
  document.getElementById("st-insp-varlabel").textContent = varDef.label;
  document.getElementById("st-insp-val").textContent = rawVal !== undefined && rawVal !== "" ? String(rawVal) : "(Missing)";
  document.getElementById("st-insp-vallabel").textContent = pres.label || "No value label mapped";
  document.getElementById("st-insp-file").textContent = rec.sourceFile || "Local Session";
  document.getElementById("st-insp-row").textContent = rec.originalRowNumber ? `Row #${rec.originalRowNumber}` : `Row #${st.selectedCell.rowIdx + 1}`;
  document.getElementById("st-insp-clerk").textContent = rec.sourceClerk || "—";

  const traceBtn = document.getElementById("st-btn-trace-evidence");
  if (rec.linkedIssueId) {
    traceBtn.hidden = false;
    traceBtn.onclick = () => callbacks.onTraceEvidence(rec.linkedIssueId);
  } else {
    traceBtn.hidden = true;
  }
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
