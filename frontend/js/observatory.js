/**
 * MediExtract — Screen 05: The Quality Observatory
 * Clinical Validation, Prescription Audit (VR-04-RX) & Dataset Readiness
 */

export const QO_PAGE_SIZE = 10;

const VALID_DIAGNOSIS_CODES = new Set(["I10", "J06", "O80", "O99", "M25.5", "K29", "E11", "1.0", "13.0", "266.0"]);

const OBSTETRIC_CODES = new Set(["O80", "O99"]);

const RX_AUDIT_PAIRS = [
  {
    diag: "I10",
    diagLabel: "Essential Hypertension (I10)",
    treat: "Amoxicillin",
    rationale: "Rule VR-04-RX: Antibiotic (Amoxicillin) paired with Essential Hypertension (I10) without a documented infectious diagnosis. Flagged for qualified clinical review."
  },
  {
    diag: "J06",
    diagLabel: "Acute Upper Respiratory Infection (J06)",
    treat: "Insulin",
    rationale: "Rule VR-04-RX: Hypoglycemic agent (Insulin) paired with Acute URI (J06) without a documented endocrine diagnosis. Flagged for qualified clinical review."
  },
  {
    diag: "M25.5",
    diagLabel: "Joint / Wrist Pain (M25.5)",
    treat: "Metformin",
    rationale: "Rule VR-04-RX: Antidiabetic agent (Metformin) paired with musculoskeletal pain (M25.5). Flagged for qualified clinical review."
  }
];

export function runQualityValidation(records, rulesConfig) {
  const issues = [];
  let seq = 1;

  const pushIssue = (data) => {
    issues.push({
      id: `qo_${seq++}`,
      resolutionStatus: "UNRESOLVED", // UNRESOLVED | RESOLVED | DISMISSED | ESCALATED
      correctedValue: undefined,
      auditHistory: [],
      ...data
    });
  };

  // Track duplicates without mutating source records
  const exactMap = new Map();
  const possibleMap = new Map();

  for (const rec of records) {
    // 1. Value validation
    if (rulesConfig.value) {
      // Required fields
      for (const reqField of ["Respondent_ID", "Sex", "Diagnosis1"]) {
        const val = rec[reqField];
        if (val === undefined || val === null || String(val).trim() === "") {
          pushIssue({
            category: "MISSING_VALUES",
            categoryLabel: "Missing values",
            severity: "WARNING",
            ruleId: "VR-02-REQ",
            variable: reqField,
            recordId: rec.Respondent_ID || `Row #${rec.originalRowNumber}`,
            originalValue: "(Empty)",
            expectedCondition: `${reqField} is required and must not be empty`,
            description: `Required field ${reqField} is missing on row ${rec.originalRowNumber}.`,
            sourceFile: rec.sourceFile,
            sourceClerk: rec.sourceClerk,
            originalRowNumber: rec.originalRowNumber,
            linkedIssueId: rec.linkedIssueId || null,
            linkedDocId: rec.linkedDocId || null
          });
        }
      }

      // Age 0-115 & numeric type check
      if (rec.Age !== undefined && rec.Age !== null && String(rec.Age).trim() !== "") {
        const ageNum = Number(rec.Age);
        if (Number.isNaN(ageNum)) {
          pushIssue({
            category: "INVALID_VALUES",
            categoryLabel: "Invalid values",
            severity: "ERROR",
            ruleId: "VR-03-TYPE",
            variable: "Age",
            recordId: rec.Respondent_ID || `Row #${rec.originalRowNumber}`,
            originalValue: String(rec.Age),
            expectedCondition: "Numeric integer/float (F8.0) within 0–115",
            description: `Age value "${rec.Age}" is non-numeric and violates expected numeric storage type.`,
            sourceFile: rec.sourceFile,
            sourceClerk: rec.sourceClerk,
            originalRowNumber: rec.originalRowNumber,
            linkedIssueId: rec.linkedIssueId || null,
            linkedDocId: rec.linkedDocId || null
          });
        } else if (ageNum < 0 || ageNum > 115) {
          pushIssue({
            category: "INVALID_VALUES",
            categoryLabel: "Invalid values",
            severity: "ERROR",
            ruleId: "VR-01-AGE",
            variable: "Age",
            recordId: rec.Respondent_ID || `Row #${rec.originalRowNumber}`,
            originalValue: String(rec.Age),
            expectedCondition: "0 <= Age <= 115",
            description: `Age ${rec.Age} falls outside the valid clinical range of 0–115 years.`,
            sourceFile: rec.sourceFile,
            sourceClerk: rec.sourceClerk,
            originalRowNumber: rec.originalRowNumber,
            linkedIssueId: rec.linkedIssueId || null,
            linkedDocId: rec.linkedDocId || null
          });
        }
      }

      // Unmapped diagnosis code check
      if (rec.Diagnosis1 && !VALID_DIAGNOSIS_CODES.has(String(rec.Diagnosis1).trim())) {
        pushIssue({
          category: "UNMAPPED_CODES",
          categoryLabel: "Unmapped codes",
          severity: "WARNING",
          ruleId: "VR-03-CODE",
          variable: "Diagnosis1",
          recordId: rec.Respondent_ID || `Row #${rec.originalRowNumber}`,
          originalValue: String(rec.Diagnosis1),
          expectedCondition: "Code present in project Diagnosis1 codebook",
          description: `Diagnosis1 code "${rec.Diagnosis1}" is not mapped to the approved project codebook.`,
          sourceFile: rec.sourceFile,
          sourceClerk: rec.sourceClerk,
          originalRowNumber: rec.originalRowNumber,
          linkedIssueId: rec.linkedIssueId || null,
          linkedDocId: rec.linkedDocId || null
        });
      }
    }

    // 2. Logical validation (explicit sex/diagnosis rule)
    if (rulesConfig.logical) {
      if (
        String(rec.Sex || "").toLowerCase() === "male" &&
        OBSTETRIC_CODES.has(String(rec.Diagnosis1 || "").trim())
      ) {
        pushIssue({
          category: "LOGICAL_INCONSISTENCIES",
          categoryLabel: "Logical inconsistencies",
          severity: "ERROR",
          ruleId: "VR-05-SEX-DIAG",
          variable: "Diagnosis1",
          recordId: rec.Respondent_ID || `Row #${rec.originalRowNumber}`,
          originalValue: `Sex=${rec.Sex} · Diagnosis1=${rec.Diagnosis1}`,
          expectedCondition: "Obstetric diagnosis codes (O80–O99) require Sex ≠ Male per rule VR-05-SEX-DIAG",
          description: `Sex (${rec.Sex}) conflicts with obstetric diagnosis (${rec.Diagnosis1}).`,
          sourceFile: rec.sourceFile,
          sourceClerk: rec.sourceClerk,
          originalRowNumber: rec.originalRowNumber,
          linkedIssueId: rec.linkedIssueId || null,
          linkedDocId: rec.linkedDocId || null
        });
      }
    }

    // 3. Duplicate detection (never auto-deletes)
    if (rulesConfig.duplicates && rec.Respondent_ID) {
      const exactKey = `${rec.Respondent_ID}|${rec.Encounter_Date || ""}|${rec.Diagnosis1 || ""}`;
      if (exactMap.has(exactKey)) {
        const first = exactMap.get(exactKey);
        pushIssue({
          category: "DUPLICATE_RECORDS",
          categoryLabel: "Duplicate records",
          severity: "WARNING",
          ruleId: "VR-06-DUP-EXACT",
          variable: "Respondent_ID",
          recordId: rec.Respondent_ID,
          originalValue: `${rec.Respondent_ID} (${rec.Encounter_Date || "No date"})`,
          expectedCondition: `Exact match with row ${first.originalRowNumber} in ${first.sourceFile}`,
          description: `Confirmed exact duplicate on Respondent_ID, Encounter_Date, and Diagnosis1. Original records preserved.`,
          sourceFile: rec.sourceFile,
          sourceClerk: rec.sourceClerk,
          originalRowNumber: rec.originalRowNumber,
          linkedIssueId: rec.linkedIssueId || null,
          linkedDocId: rec.linkedDocId || null
        });
      } else {
        exactMap.set(exactKey, rec);
        const possKey = `${rec.Respondent_ID}|${rec.Facility_Code || ""}`;
        if (possibleMap.has(possKey)) {
          const first = possibleMap.get(possKey);
          pushIssue({
            category: "DUPLICATE_RECORDS",
            categoryLabel: "Duplicate records",
            severity: "WARNING",
            ruleId: "VR-06-DUP-POSSIBLE",
            variable: "Respondent_ID",
            recordId: rec.Respondent_ID,
            originalValue: `${rec.Respondent_ID} · ${rec.Facility_Code || ""}`,
            expectedCondition: `Possible duplicate with row ${first.originalRowNumber} (${first.sourceClerk})`,
            description: `Possible duplicate respondent at same facility with differing encounter fields. Review before exclusion.`,
            sourceFile: rec.sourceFile,
            sourceClerk: rec.sourceClerk,
            originalRowNumber: rec.originalRowNumber,
            linkedIssueId: rec.linkedIssueId || null,
            linkedDocId: rec.linkedDocId || null
          });
        } else {
          possibleMap.set(possKey, rec);
        }
      }
    }

    // 4. Prescription audit (VR-04-RX — Clinical Review Flag only)
    if (rulesConfig.prescription && rec.Diagnosis1 && rec.Treatment1) {
      const rxMatch = RX_AUDIT_PAIRS.find(
        (p) =>
          p.diag === String(rec.Diagnosis1).trim() &&
          p.treat.toLowerCase() === String(rec.Treatment1).trim().toLowerCase()
      );
      if (rxMatch) {
        pushIssue({
          category: "PRESCRIPTION_AUDIT",
          categoryLabel: "Prescription audit flags",
          severity: "CLINICAL_REVIEW",
          ruleId: "VR-04-RX",
          variable: "Treatment1",
          recordId: rec.Respondent_ID || `Row #${rec.originalRowNumber}`,
          originalValue: `Diagnosis1=${rxMatch.diagLabel} · Treatment1=${rec.Treatment1}`,
          expectedCondition: "Qualified clinician/supervisor review of diagnosis–treatment pairing",
          description: rxMatch.rationale,
          diagnosisContext: rxMatch.diagLabel,
          treatmentContext: rec.Treatment1,
          sourceFile: rec.sourceFile,
          sourceClerk: rec.sourceClerk,
          originalRowNumber: rec.originalRowNumber,
          linkedIssueId: rec.linkedIssueId || null,
          linkedDocId: rec.linkedDocId || null
        });
      }
    }
  }

  return issues;
}

export function filterObservatoryIssues(issues, filters) {
  const q = (filters.search || "").trim().toLowerCase();
  const filtered = issues.filter((iss) => {
    if (filters.statusTab === "ERROR" && iss.severity !== "ERROR") return false;
    if (filters.statusTab === "WARNING" && iss.severity !== "WARNING") return false;
    if (filters.statusTab === "CLINICAL_REVIEW" && iss.severity !== "CLINICAL_REVIEW") return false;
    if (
      filters.statusTab === "RESOLVED" &&
      iss.resolutionStatus !== "RESOLVED" &&
      iss.resolutionStatus !== "DISMISSED"
    ) {
      return false;
    }
    if (
      filters.statusTab === "UNRESOLVED" &&
      iss.resolutionStatus !== "UNRESOLVED" &&
      iss.resolutionStatus !== "ESCALATED"
    ) {
      return false;
    }

    if (filters.category !== "ALL" && iss.category !== filters.category) return false;
    if (filters.field !== "ALL" && iss.variable !== filters.field) return false;

    if (q) {
      const hay = `${iss.recordId} ${iss.variable} ${iss.ruleId} ${iss.description} ${iss.sourceFile} ${iss.sourceClerk}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const sevRank = { ERROR: 3, CLINICAL_REVIEW: 2, WARNING: 1 };
  return filtered.sort((a, b) => {
    if (filters.sortBy === "FIELD_ASC") return String(a.variable).localeCompare(String(b.variable));
    if (filters.sortBy === "ROW_ASC") return (a.originalRowNumber || 0) - (b.originalRowNumber || 0);
    return (sevRank[b.severity] || 0) - (sevRank[a.severity] || 0);
  });
}

export function renderObservatoryScreen(state, callbacks) {
  const qo = state.observatory;
  const project = state.projects.find((p) => p.id === state.activeProjectId) || null;
  const batch = state.batches.find((b) => b.id === state.activeBatchId) || null;

  document.getElementById("qo-project-name").textContent = project ? project.name : "No Project Selected";
  document.getElementById("qo-dataset-ref").textContent = batch
    ? `${batch.reference} · ${qo.records.length} record(s)`
    : `${qo.records.length} record(s) in session`;

  // Validation status badge (never claims Completed unless validation actually ran)
  const unresolvedCount = qo.issues.filter(
    (i) => i.resolutionStatus === "UNRESOLVED" || i.resolutionStatus === "ESCALATED"
  ).length;

  let derivedStatus = qo.validationStatus;
  if (qo.validationStatus === "COMPLETED" && unresolvedCount > 0) {
    derivedStatus = "REQUIRES_ATTENTION";
  }

  const badge = document.getElementById("qo-status-badge");
  const statusLabels = {
    NOT_STARTED: { cls: "qo-status-pill", text: "◷ Not started" },
    RUNNING: { cls: "qo-status-pill running", text: "◌ Running validation…" },
    COMPLETED: { cls: "qo-status-pill completed", text: "✓ Completed" },
    FAILED: { cls: "qo-status-pill attention", text: "✕ Validation failed" },
    REQUIRES_ATTENTION: { cls: "qo-status-pill attention", text: `! Requires attention (${unresolvedCount})` }
  };
  const st = statusLabels[derivedStatus] || statusLabels.NOT_STARTED;
  badge.className = st.cls;
  badge.textContent = st.text;

  // Quality Landscape
  renderLandscape(qo, callbacks);

  // Resolution Progress
  const total = qo.issues.length;
  const resolved = qo.issues.filter((i) => i.resolutionStatus === "RESOLVED").length;
  const dismissed = qo.issues.filter((i) => i.resolutionStatus === "DISMISSED").length;
  const escalated = qo.issues.filter((i) => i.resolutionStatus === "ESCALATED").length;
  const unresolved = qo.issues.filter((i) => i.resolutionStatus === "UNRESOLVED").length;

  document.getElementById("qo-prog-total").textContent = String(total);
  document.getElementById("qo-prog-unresolved").textContent = String(unresolved);
  document.getElementById("qo-prog-resolved").textContent = String(resolved);
  document.getElementById("qo-prog-dismissed").textContent = String(dismissed);
  document.getElementById("qo-prog-escalated").textContent = String(escalated);

  // Active landscape filter chip
  const chipWrap = document.getElementById("qo-active-filter-chip");
  if (qo.filters.category !== "ALL" || qo.filters.field !== "ALL") {
    chipWrap.hidden = false;
    const parts = [];
    if (qo.filters.category !== "ALL") parts.push(`Category: ${qo.filters.category.replace(/_/g, " ")}`);
    if (qo.filters.field !== "ALL") parts.push(`Field: ${qo.filters.field}`);
    document.getElementById("qo-active-filter-text").textContent = parts.join(" · ");
  } else {
    chipWrap.hidden = true;
  }

  // Issue Register Table
  const filtered = filterObservatoryIssues(qo.issues, qo.filters);
  const maxPage = Math.max(1, Math.ceil(filtered.length / QO_PAGE_SIZE));
  if (qo.pagination.page > maxPage) qo.pagination.page = maxPage;
  const startIdx = (qo.pagination.page - 1) * QO_PAGE_SIZE;
  const slice = filtered.slice(startIdx, startIdx + QO_PAGE_SIZE);

  const emptyEl = document.getElementById("qo-register-empty");
  const tableWrap = document.getElementById("qo-register-table-wrap");
  const tbody = document.getElementById("qo-register-tbody");

  if (qo.validationStatus === "NOT_STARTED") {
    tableWrap.hidden = true;
    emptyEl.hidden = false;
    emptyEl.innerHTML =
      qo.records.length > 0
        ? `<h3>Validation not yet executed</h3><p>${qo.records.length} record(s) loaded in session. Click <strong>Run validation</strong> above to inspect value ranges, duplicates, logical rules, and prescription audit flags.</p>`
        : `<h3>No dataset records loaded</h3><p>Connect the FastAPI/pyreadstat backend or load the isolated <strong>Dev Preview: Synthetic Fixture</strong> to inspect validation rules on synthetic clinical rows.</p>`;
  } else if (filtered.length === 0) {
    tableWrap.hidden = true;
    emptyEl.hidden = false;
    emptyEl.innerHTML =
      qo.issues.length === 0
        ? `<h3>No quality issues detected</h3><p>Validation ran on ${qo.records.length} record(s) and found 0 violations under the active rule set.</p>`
        : `<h3>No matching issues</h3><p>No issues match the current severity tab, landscape filter, or search query.</p>`;
  } else {
    emptyEl.hidden = true;
    tableWrap.hidden = false;
    tbody.innerHTML = "";

    for (const iss of slice) {
      const tr = document.createElement("tr");
      tr.className = `qo-issue-row ${qo.selectedIssueId === iss.id ? "selected" : ""}`;
      tr.innerHTML = `
        <td><span class="mono-tag">${escapeHtml(iss.ruleId)}</span><div style="font-size:12px; color:var(--ink-secondary);">${escapeHtml(iss.categoryLabel)}</div></td>
        <td>${formatSeverityBadge(iss.severity)}</td>
        <td><strong>${escapeHtml(iss.variable)}</strong></td>
        <td class="mono-tag">${escapeHtml(iss.recordId)}</td>
        <td style="max-width:240px;">${escapeHtml(iss.description)}</td>
        <td>${formatResolutionBadge(iss.resolutionStatus)}</td>
      `;
      tr.addEventListener("click", () => callbacks.onSelectIssue(iss.id));
      tbody.appendChild(tr);
    }

    const endIdx = Math.min(startIdx + QO_PAGE_SIZE, filtered.length);
    document.getElementById("qo-page-info").textContent = `Showing ${startIdx + 1}–${endIdx} of ${filtered.length}`;
    document.getElementById("qo-prev-page").disabled = qo.pagination.page <= 1;
    document.getElementById("qo-next-page").disabled = qo.pagination.page >= maxPage;
  }

  // Focused Issue Investigation Panel
  renderInspector(qo, callbacks);

  // Dataset Readiness Gate
  renderReadinessGate(qo, unresolvedCount, callbacks);
}

function renderLandscape(qo, callbacks) {
  const catContainer = document.getElementById("qo-cat-grid");
  const fieldContainer = document.getElementById("qo-field-map");

  if (qo.validationStatus === "NOT_STARTED") {
    catContainer.innerHTML = `<div style="grid-column:1/-1; padding:18px; border:1px dashed var(--rule-strong); border-radius:var(--radius-sm); color:var(--ink-secondary); font-size:13px;">Run validation to generate real category counts. MediExtract never invents issue counts or percentages before validation executes.</div>`;
    fieldContainer.innerHTML = `<div style="padding:18px; border:1px dashed var(--rule-strong); border-radius:var(--radius-sm); color:var(--ink-secondary); font-size:13px;">Field-Quality Map will populate after validation executes.</div>`;
    return;
  }

  const categories = [
    { key: "MISSING_VALUES", label: "Missing values", barCls: "" },
    { key: "INVALID_VALUES", label: "Invalid values", barCls: "coral" },
    { key: "DUPLICATE_RECORDS", label: "Duplicate records", barCls: "" },
    { key: "LOGICAL_INCONSISTENCIES", label: "Logical inconsistencies", barCls: "coral" },
    { key: "UNMAPPED_CODES", label: "Unmapped codes", barCls: "" },
    { key: "PRESCRIPTION_AUDIT", label: "Prescription audit flags", barCls: "forest" }
  ];

  const maxCat = Math.max(1, ...categories.map((c) => qo.issues.filter((i) => i.category === c.key).length));
  catContainer.innerHTML = "";
  for (const cat of categories) {
    const count = qo.issues.filter((i) => i.category === cat.key).length;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `qo-cat-card ${qo.filters.category === cat.key ? "active" : ""}`;
    btn.innerHTML = `
      <div class="mono-tag">${escapeHtml(cat.label)}</div>
      <div class="qo-cat-count">${count}</div>
      <div class="qo-cat-bar"><div class="qo-cat-bar-fill ${cat.barCls}" style="width:${Math.round((count / maxCat) * 100)}%"></div></div>
    `;
    btn.addEventListener("click", () => callbacks.onToggleCategory(cat.key));
    catContainer.appendChild(btn);
  }

  const fields = ["Age", "Sex", "Diagnosis1", "Treatment1", "Respondent_ID"];
  fieldContainer.innerHTML = "";
  for (const fld of fields) {
    const fldIssues = qo.issues.filter((i) => i.variable === fld);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `qo-field-row ${qo.filters.field === fld ? "active" : ""}`;
    const dots = fldIssues.length
      ? fldIssues
          .map((i) => {
            const cls =
              i.resolutionStatus === "RESOLVED" || i.resolutionStatus === "DISMISSED"
                ? "resolved"
                : i.severity === "ERROR"
                  ? "error"
                  : i.severity === "CLINICAL_REVIEW"
                    ? "clinical"
                    : "warning";
            return `<span class="qo-dot ${cls}" title="${escapeHtml(i.ruleId)}"></span>`;
          })
          .join("")
      : `<span class="mono-tag" style="color:var(--ink-muted);">0 issues</span>`;
    btn.innerHTML = `
      <span class="mono-tag" style="font-weight:600; color:var(--ink-main);">${escapeHtml(fld)}</span>
      <span class="qo-field-dots">${dots}</span>
      <span class="mono-tag">${fldIssues.length}</span>
    `;
    btn.addEventListener("click", () => callbacks.onToggleField(fld));
    fieldContainer.appendChild(btn);
  }
}

function renderInspector(qo, callbacks) {
  const emptyEl = document.getElementById("qo-inspector-empty");
  const bodyEl = document.getElementById("qo-inspector-body");
  const iss = qo.issues.find((i) => i.id === qo.selectedIssueId) || null;

  if (!iss) {
    emptyEl.hidden = false;
    bodyEl.hidden = true;
    return;
  }

  emptyEl.hidden = true;
  bodyEl.hidden = false;

  document.getElementById("qo-insp-title").textContent = `${iss.variable} · ${iss.recordId}`;
  document.getElementById("qo-insp-sev").innerHTML = formatSeverityBadge(iss.severity);
  document.getElementById("qo-insp-res").innerHTML = formatResolutionBadge(iss.resolutionStatus);
  document.getElementById("qo-insp-desc").textContent = iss.description;
  document.getElementById("qo-insp-rule").textContent = `${iss.ruleId} — ${iss.expectedCondition}`;
  document.getElementById("qo-insp-orig").textContent = iss.originalValue;
  document.getElementById("qo-insp-corr").textContent =
    iss.correctedValue !== undefined ? iss.correctedValue : "Unmodified (original preserved)";
  document.getElementById("qo-insp-file").textContent = iss.sourceFile || "—";
  document.getElementById("qo-insp-clerk").textContent = iss.sourceClerk || "—";
  document.getElementById("qo-insp-row").textContent = iss.originalRowNumber ? `Row #${iss.originalRowNumber}` : "—";

  const rxBox = document.getElementById("qo-insp-rx-box");
  if (iss.severity === "CLINICAL_REVIEW") {
    rxBox.hidden = false;
    rxBox.innerHTML = `<strong>Clinical Review Flag (VR-04-RX):</strong> Diagnosis <em>${escapeHtml(iss.diagnosisContext || "")}</em> + Treatment <em>${escapeHtml(iss.treatmentContext || "")}</em>. This is a prompt for qualified human judgment, not an assertion of medical error.`;
  } else {
    rxBox.hidden = true;
  }

  const evBtn = document.getElementById("qo-btn-jump-evidence");
  if (iss.linkedIssueId) {
    evBtn.hidden = false;
    evBtn.onclick = () => callbacks.onJumpToEvidence(iss.linkedIssueId);
  } else {
    evBtn.hidden = true;
  }

  const auditEl = document.getElementById("qo-insp-audit");
  if (iss.auditHistory && iss.auditHistory.length > 0) {
    auditEl.innerHTML =
      "<strong>Audit Trail:</strong><br/>" +
      iss.auditHistory
        .map(
          (a) =>
            `<span class="mono-tag">${escapeHtml(a.timestamp)}</span> — <strong>${escapeHtml(a.action)}</strong> (${escapeHtml(a.reviewer)})${a.reason ? `: ${escapeHtml(a.reason)}` : ""}`
        )
        .join("<br/>");
  } else {
    auditEl.innerHTML = "<strong>Audit Trail:</strong> No resolution actions recorded yet.";
  }

  document.getElementById("qo-action-val").value =
    iss.correctedValue !== undefined ? iss.correctedValue : iss.originalValue;
  document.getElementById("qo-action-reason").value = "";

  document.getElementById("qo-btn-correct").onclick = () => {
    const newVal = document.getElementById("qo-action-val").value.trim();
    const reason = document.getElementById("qo-action-reason").value.trim();
    if (!newVal || !reason) {
      alert("Both a corrected value and a reason are required to record a correction.");
      return;
    }
    callbacks.onResolveIssue(iss.id, "RESOLVED", { correctedValue: newVal, reason, actionLabel: `Corrected "${iss.originalValue}" → "${newVal}"` });
  };

  document.getElementById("qo-btn-reviewed").onclick = () => {
    const reason = document.getElementById("qo-action-reason").value.trim();
    callbacks.onResolveIssue(iss.id, "RESOLVED", { reason: reason || "Confirmed after review", actionLabel: "Marked as reviewed" });
  };

  document.getElementById("qo-btn-dismiss").onclick = () => {
    const reason = document.getElementById("qo-action-reason").value.trim();
    if (!reason) {
      alert("Please provide a reason before dismissing this issue.");
      return;
    }
    callbacks.onResolveIssue(iss.id, "DISMISSED", { reason, actionLabel: "Dismissed with reason" });
  };

  document.getElementById("qo-btn-escalate").onclick = () => {
    const reason = document.getElementById("qo-action-reason").value.trim();
    callbacks.onResolveIssue(iss.id, "ESCALATED", { reason: reason || "Escalated for supervisor review", actionLabel: "Escalated for supervisor review" });
  };
}

function renderReadinessGate(qo, unresolvedCount, callbacks) {
  const card = document.getElementById("qo-readiness-card");
  const label = document.getElementById("qo-readiness-state");
  const desc = document.getElementById("qo-readiness-desc");
  const approveBtn = document.getElementById("qo-btn-approve-dataset");

  card.classList.remove("ready");
  if (qo.validationStatus === "NOT_STARTED") {
    label.textContent = "Validation not run";
    desc.textContent = "Run dataset validation before supervisor approval can be considered.";
    approveBtn.disabled = true;
  } else if (qo.validationStatus === "RUNNING") {
    label.textContent = "Validation in progress";
    desc.textContent = "Evaluating validation rules against loaded records…";
    approveBtn.disabled = true;
  } else if (unresolvedCount > 0) {
    label.textContent = "Issues require attention";
    desc.textContent = `${unresolvedCount} unresolved or escalated issue(s) remain. Resolving issues improves completeness but does not replace clinical oversight.`;
    approveBtn.disabled = true;
  } else if (qo.supervisorApproved) {
    card.classList.add("ready");
    label.textContent = "Approved for analysis";
    desc.textContent = `Supervisor approved (${qo.approvedAt}). All identified issues were reviewed and source records remain immutable.`;
    approveBtn.disabled = true;
  } else {
    card.classList.add("ready");
    label.textContent = "Ready for supervisor approval";
    desc.textContent = "All identified validation issues have been reviewed, corrected, or dismissed with audit trails.";
    approveBtn.disabled = false;
  }

  approveBtn.onclick = () => callbacks.onApproveDataset();
}

function formatSeverityBadge(sev) {
  if (sev === "ERROR") return `<span class="qo-sev-badge qo-sev-error">✕ Error</span>`;
  if (sev === "CLINICAL_REVIEW") return `<span class="qo-sev-badge qo-sev-clinical">⚕ Clinical review</span>`;
  return `<span class="qo-sev-badge qo-sev-warning">! Warning</span>`;
}

function formatResolutionBadge(status) {
  switch (status) {
    case "RESOLVED":
      return `<span class="status-badge verified">✓ Resolved</span>`;
    case "DISMISSED":
      return `<span class="status-badge">Dismissed</span>`;
    case "ESCALATED":
      return `<span class="status-badge amber">⚑ Escalated</span>`;
    case "UNRESOLVED":
    default:
      return `<span class="status-badge oxide">◷ Unresolved</span>`;
  }
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
