/**
 * Screen 03: The Master Merger (The Reconciliation Bench)
 * Manages .sav Source Register, Variable Alignment, SVG Codebook Reconciliation,
 * Conflict Register, and Merge Preview / Execution Gate.
 */

import { formatBytes } from "./upload.js";

/**
 * Verify genuine IBM SPSS .sav binary magic bytes ($FL2 or $FL3).
 */
export async function validateSavMagicBytes(file) {
  const lower = (file.name || "").toLowerCase();
  if (!lower.endsWith(".sav")) {
    return { valid: false, error: "Only IBM SPSS (.sav) files are supported in Master Merger." };
  }
  if (file.size < 64) {
    return { valid: false, error: "File is too small to be a valid SPSS .sav dataset." };
  }
  try {
    const buf = await file.slice(0, 4).arrayBuffer();
    const text = new TextDecoder("ascii").decode(buf);
    if (text === "$FL2" || text === "$FL3") {
      return { valid: true, header: text };
    }
    return {
      valid: false,
      error: `Invalid .sav binary header "${text}". Expected $FL2 or $FL3.`
    };
  } catch {
    return { valid: false, error: "Unable to read .sav file header." };
  }
}

export function renderMergerScreen(state, callbacks) {
  const project = state.projects.find((p) => p.id === state.activeProjectId) || null;
  const merger = state.merger;

  document.getElementById("mm-project-name").textContent = project ? project.name : "No Project Selected";

  const unresolvedMandatory = merger.conflicts.filter(
    (c) => c.severity === "MANDATORY" && c.status !== "RESOLVED"
  ).length;

  const badge = document.getElementById("mm-status-badge");
  if (merger.sources.length === 0) {
    badge.className = "status-badge mm-awaiting";
    badge.textContent = "◷ Awaiting .SAV Sources";
  } else if (unresolvedMandatory > 0) {
    badge.className = "status-badge failed";
    badge.textContent = `! ${unresolvedMandatory} Mandatory Conflict(s)`;
  } else if (merger.mergeCompleted) {
    badge.className = "status-badge verified";
    badge.textContent = "✓ Master .SAV Generated";
  } else {
    badge.className = "status-badge verified";
    badge.textContent = "✓ Ready for Merge Review";
  }

  // Sub-tab switching
  ["sources", "variables", "codebook", "conflicts", "preview"].forEach((tab) => {
    const btn = document.getElementById("mm-subbtn-" + tab);
    const pane = document.getElementById("mm-pane-" + tab);
    const isActive = merger.activeSubTab === tab;
    if (btn) {
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-selected", String(isActive));
    }
    if (pane) pane.hidden = !isActive;
  });

  document.getElementById("mm-count-sources").textContent = String(merger.sources.length);
  document.getElementById("mm-count-vars").textContent = String(merger.variableMappings.length);
  document.getElementById("mm-count-cb").textContent = String(merger.codebookMappings.length);
  document.getElementById("mm-count-conflicts").textContent = String(
    merger.conflicts.filter((c) => c.status !== "RESOLVED").length
  );

  renderSourceRegister(merger, callbacks);
  renderVariableAlignment(merger, callbacks);
  renderCodebookBench(merger, callbacks);
  renderConflictRegister(merger, callbacks);
  renderMergePreview(state, merger, callbacks);
}

function renderSourceRegister(merger, callbacks) {
  const emptyEl = document.getElementById("mm-sources-empty");
  const tableWrap = document.getElementById("mm-sources-table-wrap");
  const tbody = document.getElementById("mm-sources-tbody");

  if (merger.sources.length === 0) {
    tableWrap.hidden = true;
    emptyEl.hidden = false;
    return;
  }

  emptyEl.hidden = true;
  tableWrap.hidden = false;
  tbody.innerHTML = "";

  for (const src of merger.sources) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>
        <div style="font-weight:600;">${escapeHtml(src.filename)}</div>
        <div class="mono-tag">${escapeHtml(formatBytes(src.sizeBytes))} · ${escapeHtml(src.header || "$FL2")}</div>
      </td>
      <td><strong>${escapeHtml(src.clerkIdentity)}</strong></td>
      <td class="mono-tag">${src.recordCount != null ? src.recordCount.toLocaleString() : "Pending API"}</td>
      <td class="mono-tag">${src.variableCount != null ? src.variableCount : "Pending API"}</td>
      <td><span class="status-badge ${src.importStatus === "SERVER_PARSED" ? "verified" : "amber"}">${escapeHtml(src.importStatus)}</span></td>
      <td class="mono-tag">${escapeHtml(src.schemaStatus)}</td>
      <td class="mono-tag">${escapeHtml(src.reconciliationStatus)}</td>
      <td class="mono-tag">${new Date(src.importedAt).toLocaleDateString()}</td>
      <td style="text-align:right; white-space:nowrap;">
        <button type="button" class="btn btn-sm btn-src-meta">Metadata</button>
        <button type="button" class="btn btn-sm btn-oxide btn-src-remove">Remove</button>
      </td>
    `;
    tr.querySelector(".btn-src-meta").addEventListener("click", () => callbacks.onInspectSource(src));
    tr.querySelector(".btn-src-remove").addEventListener("click", () => callbacks.onRemoveSource(src.id));
    tbody.appendChild(tr);
  }
}

function renderVariableAlignment(merger, callbacks) {
  const emptyEl = document.getElementById("mm-vars-empty");
  const tableWrap = document.getElementById("mm-vars-table-wrap");
  const tbody = document.getElementById("mm-vars-tbody");

  if (merger.variableMappings.length === 0) {
    tableWrap.hidden = true;
    emptyEl.hidden = false;
    return;
  }

  emptyEl.hidden = true;
  tableWrap.hidden = false;
  tbody.innerHTML = "";

  for (const vm of merger.variableMappings) {
    const tr = document.createElement("tr");
    const clsMap = {
      EXACT_MATCH: "match-exact",
      STRONG_SUGGESTION: "match-strong",
      POSSIBLE_MATCH: "match-possible",
      NO_MATCH: "match-none",
      INCOMPATIBLE: "match-incompatible"
    };
    const matchCls = clsMap[vm.matchClass] || "match-possible";

    tr.innerHTML = `
      <td>
        <div style="font-weight:600;"><code>${escapeHtml(vm.sourceVar)}</code></div>
        <div class="mono-tag">${escapeHtml(vm.sourceFile)} · ${escapeHtml(vm.sourceType)} · ${escapeHtml(vm.sourceMeasure)}</div>
        <div style="font-size:12px; color:var(--ink-secondary);">${escapeHtml(vm.sourceLabel || "No label")}</div>
      </td>
      <td>
        <span class="match-badge ${matchCls}">${escapeHtml(vm.matchClass.replace("_", " "))}</span>
        <div style="font-size:12px; color:var(--ink-secondary); margin-top:4px;">${escapeHtml(vm.rationale)}</div>
        <div class="mono-tag">${vm.affectedRecords.toLocaleString()} records affected</div>
      </td>
      <td>
        <select class="input-control vm-target-select" style="width:100%;">
          ${vm.targetOptions.map((opt) => `<option value="${escapeHtml(opt)}" ${opt === vm.targetVar ? "selected" : ""}>${escapeHtml(opt)}</option>`).join("")}
        </select>
        <div class="mono-tag" style="margin-top:4px;">${escapeHtml(vm.targetSpec || "")}</div>
      </td>
      <td>
        ${vm.excluded
          ? `<span class="status-badge failed">✕ Excluded (${escapeHtml(vm.excludeReason || "Intentional")})</span>`
          : vm.approved
            ? `<span class="status-badge verified">✓ Approved</span>`
            : `<span class="status-badge amber">◷ Needs Approval</span>`}
      </td>
      <td style="text-align:right; white-space:nowrap;">
        <button type="button" class="btn btn-sm btn-verified btn-vm-accept">${vm.approved ? "Approved" : "Accept"}</button>
        <button type="button" class="btn btn-sm btn-vm-new">+ New Master Var</button>
        <button type="button" class="btn btn-sm btn-oxide btn-vm-exclude">Exclude</button>
      </td>
    `;

    tr.querySelector(".vm-target-select").addEventListener("change", (e) => {
      callbacks.onChangeVarTarget(vm.id, e.target.value);
    });
    tr.querySelector(".btn-vm-accept").addEventListener("click", () => callbacks.onApproveVar(vm.id));
    tr.querySelector(".btn-vm-new").addEventListener("click", () => callbacks.onCreateMasterVar(vm.id));
    tr.querySelector(".btn-vm-exclude").addEventListener("click", () => callbacks.onExcludeVar(vm.id));
    tbody.appendChild(tr);
  }
}

function renderCodebookBench(merger, callbacks) {
  const emptyEl = document.getElementById("mm-cb-empty");
  const benchEl = document.getElementById("mm-cb-bench-wrap");
  if (merger.codebookMappings.length === 0) {
    benchEl.hidden = true;
    emptyEl.hidden = false;
    return;
  }

  emptyEl.hidden = true;
  benchEl.hidden = false;

  const srcCol = document.getElementById("cb-source-list");
  const svgEl = document.getElementById("cb-svg-lines");
  const mstCol = document.getElementById("cb-master-list");
  const detailBox = document.getElementById("cb-selected-detail");

  srcCol.innerHTML = "";
  mstCol.innerHTML = "";

  const activeId = merger.selectedCodebookId || merger.codebookMappings[0].id;
  const rows = merger.codebookMappings;

  rows.forEach((cb, idx) => {
    const isSel = cb.id === activeId;
    const statusCls = cb.approved ? "approved" : cb.hasCollision ? "conflict" : "";

    const sCard = document.createElement("div");
    sCard.className = `cb-item-card ${statusCls} ${isSel ? "selected" : ""}`;
    sCard.innerHTML = `
      <div>
        <span class="mono-tag">${escapeHtml(cb.sourceClerk)} · ${escapeHtml(cb.variableName)}</span>
        <div style="font-weight:600; margin-top:2px;"><code>${escapeHtml(cb.sourceCode)}</code> = ${escapeHtml(cb.sourceLabel)}</div>
      </div>
      <span class="mono-tag">${cb.affectedRecords.toLocaleString()} rows</span>
    `;
    sCard.addEventListener("click", () => callbacks.onSelectCodebook(cb.id));
    srcCol.appendChild(sCard);

    const mCard = document.createElement("div");
    mCard.className = `cb-item-card ${statusCls} ${isSel ? "selected" : ""}`;
    mCard.innerHTML = `
      <div>
        <span class="mono-tag">MASTER CODEBOOK</span>
        <div style="font-weight:600; margin-top:2px;"><code>${escapeHtml(cb.masterCode)}</code> = ${escapeHtml(cb.masterLabel)}</div>
      </div>
      <span class="status-badge ${cb.approved ? "verified" : "amber"}">${cb.approved ? "✓ Approved" : "Review"}</span>
    `;
    mCard.addEventListener("click", () => callbacks.onSelectCodebook(cb.id));
    mstCol.appendChild(mCard);

    if (isSel) {
      detailBox.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; gap:14px; flex-wrap:wrap;">
          <div>
            <span class="mono-tag">MAPPING RATIONALE (${escapeHtml(cb.variableName)})</span>
            <div style="font-weight:600; margin-top:2px;">
              ${escapeHtml(cb.sourceClerk)}: <code>${escapeHtml(cb.sourceCode)} (${escapeHtml(cb.sourceLabel)})</code> → Master: <code>${escapeHtml(cb.masterCode)} (${escapeHtml(cb.masterLabel)})</code>
            </div>
            <div style="font-size:12.5px; color:var(--ink-secondary); margin-top:2px;">${escapeHtml(cb.rationale)} · Affects ${cb.affectedRecords.toLocaleString()} records.</div>
          </div>
          <div style="display:flex; gap:8px;">
            <button type="button" class="btn btn-sm btn-verified" id="btn-cb-approve">${cb.approved ? "✓ Approved" : "Approve Mapping"}</button>
          </div>
        </div>
      `;
      detailBox.querySelector("#btn-cb-approve").addEventListener("click", () => callbacks.onApproveCodebook(cb.id));
    }
  });

  // Draw SVG connecting lines between Source and Master items
  const h = Math.max(180, rows.length * 76);
  svgEl.setAttribute("viewBox", `0 0 120 ${h}`);
  svgEl.style.height = `${h}px`;
  svgEl.innerHTML = rows
    .map((cb, idx) => {
      const y = 38 + idx * 76;
      const cls = cb.id === activeId ? "cb-line-active" : cb.approved ? "cb-line-approved" : "cb-line-conflict";
      return `
        <path d="M 4 ${y} C 45 ${y}, 75 ${y}, 116 ${y}" class="${cls}" fill="none" />
        <circle cx="6" cy="${y}" r="3.5" fill="#477FF5" />
        <circle cx="114" cy="${y}" r="3.5" fill="${cb.approved ? "#183B35" : "#FF785E"}" />
      `;
    })
    .join("");
}

function renderConflictRegister(merger, callbacks) {
  const emptyEl = document.getElementById("mm-conf-empty");
  const wrapEl = document.getElementById("mm-conf-table-wrap");
  const tbody = document.getElementById("mm-conf-tbody");

  const sevFilter = merger.conflictFilters.severity;
  const typeFilter = merger.conflictFilters.type;

  const filtered = merger.conflicts.filter((c) => {
    if (sevFilter !== "ALL" && c.severity !== sevFilter) return false;
    if (typeFilter !== "ALL" && c.type !== typeFilter) return false;
    return true;
  });

  if (filtered.length === 0) {
    wrapEl.hidden = true;
    emptyEl.hidden = false;
    emptyEl.innerHTML =
      merger.conflicts.length === 0
        ? `<h3>No conflicts detected</h3><p>Import and inspect clerk <code>.sav</code> files to scan for variable, type, and codebook collisions.</p>`
        : `<h3>No conflicts match the active filters</h3><p>Reset your severity or conflict-type filter to view all items.</p>`;
    return;
  }

  emptyEl.hidden = true;
  wrapEl.hidden = false;
  tbody.innerHTML = "";

  for (const c of filtered) {
    const tr = document.createElement("tr");
    const sevBadge =
      c.severity === "MANDATORY"
        ? `<span class="status-badge failed">! Mandatory</span>`
        : `<span class="status-badge amber">• Warning</span>`;
    const resBadge =
      c.status === "RESOLVED"
        ? `<span class="status-badge verified">✓ Resolved</span>`
        : `<span class="status-badge amber">◷ Unresolved</span>`;

    tr.innerHTML = `
      <td>${sevBadge}</td>
      <td><strong>${escapeHtml(c.type.replace("_", " "))}</strong></td>
      <td class="mono-tag">${escapeHtml(c.sourceFiles.join(", "))}</td>
      <td><code>${escapeHtml(c.variable)}</code></td>
      <td class="mono-tag">${c.affectedRecords.toLocaleString()}</td>
      <td>${escapeHtml(c.recommendedResolution)}</td>
      <td>${resBadge}</td>
      <td style="text-align:right; white-space:nowrap;">
        <button type="button" class="btn btn-sm btn-electric btn-jump-conf">Inspect →</button>
      </td>
    `;
    tr.querySelector(".btn-jump-conf").addEventListener("click", () => callbacks.onJumpToConflict(c));
    tbody.appendChild(tr);
  }
}

function renderMergePreview(state, merger, callbacks) {
  const unresolvedMandatory = merger.conflicts.filter(
    (c) => c.severity === "MANDATORY" && c.status !== "RESOLVED"
  ).length;
  const resolvedCount = merger.conflicts.filter((c) => c.status === "RESOLVED").length;

  const estRows = merger.sources.reduce((s, src) => s + (src.recordCount || 0), 0);
  const masterVarCount = merger.variableMappings.filter((v) => !v.excluded).length;

  document.getElementById("mp-sources").textContent = String(merger.sources.length);
  document.getElementById("mp-records").textContent =
    merger.sources.length > 0 && estRows > 0 ? `~${estRows.toLocaleString()} (Estimate)` : "0";
  document.getElementById("mp-vars").textContent = String(masterVarCount);
  document.getElementById("mp-resolved").textContent = String(resolvedCount);
  document.getElementById("mp-unresolved").textContent = String(unresolvedMandatory);
  document.getElementById("mp-dups").textContent = String(merger.duplicateCandidatesCount || 0);

  const gateStatusBox = document.getElementById("mm-gate-status-box");
  const execBtn = document.getElementById("btn-execute-master-merge");

  if (merger.sources.length < 2) {
    gateStatusBox.className = "mm-blocker-box";
    gateStatusBox.textContent = "Import at least 2 clerk .sav files to preview and execute a master merge.";
    execBtn.disabled = true;
  } else if (unresolvedMandatory > 0) {
    gateStatusBox.className = "mm-blocker-box";
    gateStatusBox.textContent = `Merge Blocked: ${unresolvedMandatory} mandatory conflict(s) remain unresolved in Variable Alignment / Codebook Reconciliation.`;
    execBtn.disabled = true;
  } else if (!state.backendConnected) {
    gateStatusBox.className = "mm-blocker-box";
    gateStatusBox.textContent = "Merge Blocked: pyreadstat merge backend (/api/v1/projects/{id}/merge/execute) is offline. MediExtract never fabricates merged .sav files.";
    execBtn.disabled = true;
  } else {
    gateStatusBox.className = "mm-ready-box";
    gateStatusBox.textContent = "All mandatory conflicts resolved and pyreadstat backend is connected. Ready to generate immutable MASTER.sav.";
    execBtn.disabled = false;
  }

  execBtn.onclick = callbacks.onExecuteMerge;
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
