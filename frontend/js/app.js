/**
 * MediExtract — Receiving Desk & Evidence Review Workstation
 * Unified State: Project -> Batch -> Documents -> Pages -> Review Queue
 */

import {
  checkBackendConnection,
  uploadFilesToBackend,
  submitDecisionToBackend,
  inspectMergeFilesOnBackend,
  executeMasterMergeOnBackend,
  runQualityValidationOnBackend
} from "./api.js";
import { validateUploadFile, inspectLocalFile } from "./upload.js";
import { renderProjectIndex } from "./project-index.js";
import { validateSavMagicBytes, renderMergerScreen } from "./merger.js";
import { runQualityValidation, renderObservatoryScreen } from "./observatory.js";
import {
  generateBatchReference,
  generateDocumentReference,
  validateFileMagicBytes,
  computeSha256Fingerprint,
  buildPageRecords,
  renderIntakeOverview,
  renderIntakeLedger,
  openDocumentDetailModal
} from "./intake.js";
import { renderBatchSummary, renderQueueTable, filterQueueItems } from "./queue.js";
import {
  initViewerControls,
  renderEvidenceSplit,
  openEditDrawer,
  setZoom,
  viewerState,
  confirmDiscardUnsavedChanges
} from "./evidence-split.js";

const appState = {
  view: "home", // "home" | "intake" | "queue" | "split" | "merger" | "analytics" | "settings"
  backendConnected: false,
  syntheticMode: false,
  projectsLoading: false,
  projectsError: null,
  merger: {
    activeSubTab: "sources",
    sources: [],
    variableMappings: [],
    codebookMappings: [],
    selectedCodebookId: null,
    conflicts: [],
    conflictFilters: { severity: "ALL", type: "ALL" },
    duplicateCandidatesCount: 0,
    mergeCompleted: false
  },
  projects: [
    {
      id: "proj_oyshia_default",
      reference: "PRJ-OYSHIA-2026",
      name: "OYSHIA Encounter Forms",
      description: "Primary encounter record intake and verification workspace for participating facilities.",
      setupMode: "SPSS Template",
      templateName: null,
      requiresFacility: true,
      facilities: []
    }
  ],
  activeProjectId: "proj_oyshia_default",
  batches: [],
  activeBatchId: null,
  documents: [],
  queueItems: [],
  pendingDuplicate: null,
  selectedDocIds: new Set(),
  expandedDocIds: new Set(),
  activeIssueId: null,
  activeDirectDocId: null,
  intakeFilters: {
    search: "",
    status: "ALL",
    facility: "ALL",
    sort: "date_desc"
  },
  intakePagination: { page: 1 },
  filters: {
    statusTab: "NEEDS_REVIEW",
    reasonFilter: "ALL_UNRESOLVED",
    searchQuery: "",
    sortBy: "SEVERITY_DESC"
  },
  pagination: { page: 1 },
  observatory: {
    validationStatus: "NOT_STARTED",
    records: [],
    issues: [],
    selectedIssueId: null,
    supervisorApproved: false,
    approvedAt: null,
    filters: {
      statusTab: "ALL",
      category: "ALL",
      field: "ALL",
      sortBy: "SEV_DESC",
      search: ""
    },
    pagination: { page: 1 }
  }
};

document.addEventListener("DOMContentLoaded", async () => {
  initViewerControls();
  bindNavigation();
  bindProjectAndBatchControls();
  bindIntakeUploadControls();
  bindIntakeLedgerControls();
  bindMergerControls();
  bindObservatoryControls();
  bindQueueFilters();
  bindKeyboardShortcuts();
  bindSyntheticDevPreview();

  await refreshBackendStatus();
  renderAll();
});

async function refreshBackendStatus() {
  const status = await checkBackendConnection();
  appState.backendConnected = Boolean(status.connected);
  const pill = document.getElementById("backend-boundary-pill");
  const text = document.getElementById("backend-boundary-text");

  if (status.connected) {
    pill.classList.add("connected");
    text.textContent = "Processing Service: Connected";
  } else {
    pill.classList.remove("connected");
    text.textContent = "Processing Service: Offline (Local Boundary)";
  }
}

function bindNavigation() {
  document.getElementById("brand-home-link").addEventListener("click", () => switchView("home"));
  document.getElementById("btn-crumb-home").addEventListener("click", () => switchView("home"));
  document.getElementById("nav-home").addEventListener("click", () => switchView("home"));
  document.getElementById("nav-projects").addEventListener("click", () => {
    switchView("home");
    document.getElementById("pi-projects-anchor")?.scrollIntoView({ behavior: "smooth" });
  });
  document.getElementById("nav-intake").addEventListener("click", () => switchView("intake"));
  document.getElementById("nav-queue").addEventListener("click", () => switchView("queue"));
  document.getElementById("nav-merger").addEventListener("click", () => switchView("merger"));
  document.getElementById("nav-analytics").addEventListener("click", () => switchView("analytics"));
  document.getElementById("nav-settings").addEventListener("click", () => switchView("settings"));
  document.getElementById("nav-split").addEventListener("click", () => {
    if (appState.activeIssueId || appState.activeDirectDocId) {
      switchView("split");
    }
  });

  document.getElementById("wf-stage-receive").addEventListener("click", () => switchView("intake"));
  document.getElementById("wf-stage-verify").addEventListener("click", () => switchView("queue"));
  document.getElementById("btn-hero-create-project").addEventListener("click", () => openProjectModal("sav"));
  document.getElementById("btn-notifications").addEventListener("click", () => {
    const unresolved = appState.queueItems.filter((i) => i.reviewStatus !== "VERIFIED").length;
    showToast(unresolved > 0 ? `${unresolved} review item(s) awaiting attention.` : "No unread workstation alerts.");
  });

  document.getElementById("btn-go-review-from-intake").addEventListener("click", () => switchView("queue"));
  document.getElementById("btn-back-to-queue").addEventListener("click", () => switchView("queue"));

  document.getElementById("btn-open-next-issue").addEventListener("click", () => {
    const unresolved = filterQueueItems(appState.queueItems, {
      statusTab: "NEEDS_REVIEW",
      reasonFilter: "ALL_UNRESOLVED",
      searchQuery: ""
    });
    if (unresolved.length > 0) {
      openIssueInSplit(unresolved[0].id);
    }
  });

  document.getElementById("btn-prev-issue").addEventListener("click", () => navigateIssue(-1));
  document.getElementById("btn-next-issue").addEventListener("click", () => navigateIssue(1));
}

function switchView(viewName) {
  if (appState.view === "split" && viewName !== "split" && !confirmDiscardUnsavedChanges()) {
    return;
  }
  appState.view = viewName;
  ["home", "intake", "queue", "split", "merger", "analytics", "settings"].forEach((v) => {
    const el = document.getElementById("view-" + v);
    if (el) el.hidden = v !== viewName;
    const nav = document.getElementById("nav-" + v);
    if (nav) nav.classList.toggle("active", v === viewName);
  });
  document.getElementById("nav-projects").classList.remove("active");

  // Show project/batch hierarchy breadcrumb inside workflow screens
  const showCrumb =
    viewName === "intake" || viewName === "queue" || viewName === "split" || viewName === "merger";
  document.getElementById("hierarchy-breadcrumb-bar").hidden = !showCrumb;
  window.scrollTo({ top: 0, behavior: "instant" });

  if (viewName !== "split") {
    renderAll();
  }
}

/* ==========================================================================
   Project & Batch Hierarchy Controls
   ========================================================================== */
function bindProjectAndBatchControls() {
  const projSelect = document.getElementById("select-project");
  const batchSelect = document.getElementById("select-batch");

  projSelect.addEventListener("change", (e) => {
    appState.activeProjectId = e.target.value;
    const projBatches = appState.batches.filter((b) => b.projectId === appState.activeProjectId);
    appState.activeBatchId = projBatches[0]?.id || null;
    appState.selectedDocIds.clear();
    renderAll();
  });

  batchSelect.addEventListener("change", (e) => {
    appState.activeBatchId = e.target.value || null;
    appState.selectedDocIds.clear();
    appState.intakePagination.page = 1;
    renderAll();
  });

  document.getElementById("btn-new-batch").addEventListener("click", openBatchModal);
  document.getElementById("btn-intake-create-batch").addEventListener("click", openBatchModal);
  document.getElementById("btn-close-batch-modal").addEventListener("click", closeBatchModal);
  document.getElementById("btn-cancel-batch-modal").addEventListener("click", closeBatchModal);
  document.getElementById("btn-close-project-modal").addEventListener("click", closeProjectModal);
  document.getElementById("btn-cancel-project-modal").addEventListener("click", closeProjectModal);
  document.getElementById("btn-close-doc-detail").addEventListener("click", () => {
    document.getElementById("doc-detail-modal").hidden = true;
  });

  document.getElementById("project-create-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = document.getElementById("pf-name").value.trim();
    const desc = document.getElementById("pf-desc").value.trim();
    const mode = document.getElementById("pf-setup-mode").value;
    const fileInput = document.getElementById("pf-template-file");
    const tplFile = fileInput.files?.[0] || null;
    if (!name) return;

    const newProj = {
      id: `proj_${Date.now()}`,
      reference: `PRJ-${new Date().getFullYear()}-${String(appState.projects.length + 1).padStart(3, "0")}`,
      name,
      description: desc || "Clinical encounter data processing workspace.",
      setupMode: mode === "sav" ? "SPSS Template (.sav)" : "Questionnaire PDF",
      templateName: tplFile ? tplFile.name : null,
      requiresFacility: true,
      facilities: []
    };

    appState.projects.unshift(newProj);
    appState.activeProjectId = newProj.id;
    appState.activeBatchId = null;
    closeProjectModal();
    renderAll();
    showToast(`Created project ${newProj.reference}: ${newProj.name}`);
  });

  document.getElementById("batch-create-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const proj = appState.projects.find((p) => p.id === appState.activeProjectId);
    if (!proj) return;

    const name = document.getElementById("bf-name").value.trim();
    const facility = document.getElementById("bf-facility").value.trim();
    const period = document.getElementById("bf-period").value.trim();
    const desc = document.getElementById("bf-desc").value.trim();

    if (!name || (proj.requiresFacility && !facility)) return;

    const newBatch = {
      id: `batch_${Date.now()}`,
      reference: generateBatchReference(appState.batches),
      name,
      projectId: proj.id,
      projectName: proj.name,
      facility,
      reportingPeriod: period,
      description: desc,
      createdAt: new Date().toISOString(),
      createdBy: "Local Workstation Session",
      lifecycleStatus: "RECEIVING",
      activityHistory: [{ timestamp: new Date().toLocaleTimeString(), event: "Batch created" }]
    };

    appState.batches.unshift(newBatch);
    appState.activeBatchId = newBatch.id;
    if (facility && !proj.facilities.includes(facility)) {
      proj.facilities.push(facility);
    }

    closeBatchModal();
    renderAll();
    showToast(`Created batch ${newBatch.reference}: ${newBatch.name}`);
  });
}

function openProjectModal(defaultMode = "sav") {
  document.getElementById("pf-name").value = "";
  document.getElementById("pf-desc").value = "";
  document.getElementById("pf-setup-mode").value = defaultMode;
  document.getElementById("pf-template-file").value = "";
  document.getElementById("project-modal").hidden = false;
  document.getElementById("pf-name").focus();
}

function closeProjectModal() {
  document.getElementById("project-modal").hidden = true;
}

function openBatchModal() {
  const proj = appState.projects.find((p) => p.id === appState.activeProjectId);
  document.getElementById("bf-project").value = proj ? proj.name : "No Project Selected";
  document.getElementById("bf-name").value = "";
  document.getElementById("bf-facility").value = "";
  document.getElementById("bf-period").value = "";
  document.getElementById("bf-desc").value = "";
  document.getElementById("batch-modal").hidden = false;
  document.getElementById("bf-name").focus();
}

function closeBatchModal() {
  document.getElementById("batch-modal").hidden = true;
}

/* ==========================================================================
   Paper Intake Upload, Magic-Byte Validation & SHA-256 Duplicate Detection
   ========================================================================== */
function bindIntakeUploadControls() {
  const dropzone = document.getElementById("intake-dropzone");
  const fileInput = document.getElementById("intake-file-input");

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("drag-over");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("drag-over");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag-over");
    if (e.dataTransfer?.files?.length) {
      handleIntakeFiles(Array.from(e.dataTransfer.files));
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files?.length) {
      handleIntakeFiles(Array.from(e.target.files));
      fileInput.value = "";
    }
  });

  document.getElementById("btn-dup-skip").addEventListener("click", () => {
    appState.pendingDuplicate = null;
    document.getElementById("duplicate-alert").hidden = true;
    showToast("Retained existing document; duplicate upload skipped.");
  });

  document.getElementById("btn-dup-inspect").addEventListener("click", () => {
    if (appState.pendingDuplicate?.existingDoc) {
      openDocumentDetailModal(appState.pendingDuplicate.existingDoc);
    }
  });

  document.getElementById("btn-dup-keep-both").addEventListener("click", async () => {
    if (!appState.pendingDuplicate) return;
    const { inspected, existingDoc } = appState.pendingDuplicate;
    inspected.duplicateOfRef = existingDoc.docRef;
    appState.pendingDuplicate = null;
    document.getElementById("duplicate-alert").hidden = true;
    await commitUploadedDocument(inspected);
  });
}

async function handleIntakeFiles(files) {
  if (appState.syntheticMode) {
    exitSyntheticMode();
  }

  // Require an active batch before receiving documents
  if (!appState.activeBatchId) {
    showToast("Please create or select a batch first before uploading documents.");
    openBatchModal();
    return;
  }

  for (const file of files) {
    const extCheck = validateUploadFile(file);
    if (!extCheck.valid) {
      showToast(`${file.name}: ${extCheck.error}`);
      continue;
    }

    const magicCheck = await validateFileMagicBytes(file);
    if (!magicCheck.valid) {
      showToast(`${file.name}: ${magicCheck.error}`);
      continue;
    }

    const sha256 = await computeSha256Fingerprint(file);
    const inspected = await inspectLocalFile(file);
    inspected.detectedFormat = magicCheck.detectedFormat;
    inspected.sha256 = sha256;

    // Duplicate content check against active batch/project
    if (sha256) {
      const existing = appState.documents.find(
        (d) => d.sha256 === sha256 && d.batchId === appState.activeBatchId
      );
      if (existing) {
        appState.pendingDuplicate = { inspected, existingDoc: existing };
        document.getElementById("duplicate-msg").textContent =
          `"${file.name}" has an identical SHA-256 content fingerprint to existing document "${existing.name}" (${existing.docRef}).`;
        document.getElementById("duplicate-alert").hidden = false;
        continue;
      }
    }

    await commitUploadedDocument(inspected);
  }
}

async function commitUploadedDocument(doc) {
  const batch = appState.batches.find((b) => b.id === appState.activeBatchId);
  if (!batch) return;

  doc.batchId = batch.id;
  doc.facility = batch.facility;
  doc.docRef = generateDocumentReference(appState.documents.length);
  doc.uploadStatus = "LOCAL_SESSION";
  doc.processingStatus = "QUEUED";
  doc.justArrived = true;
  doc.pages = buildPageRecords(doc.id, doc.pageCount);
  doc.history = [
    {
      timestamp: new Date().toLocaleTimeString(),
      event: `Received in local session for ${batch.reference} (${doc.pageCount || 1} page(s), ${doc.detectedFormat})`
    }
  ];

  appState.documents.unshift(doc);
  renderAll();

  const res = await uploadFilesToBackend(appState.activeProjectId, [doc.file]);
  if (!res.ok) {
    doc.uploadStatus = "LOCAL_SESSION";
    doc.history.unshift({
      timestamp: new Date().toLocaleTimeString(),
      event: "Held in local browser session (Backend upload endpoint not connected)"
    });
    showToast(res.message);
  } else if (res.data?.queueItems) {
    doc.uploadStatus = "SERVER_UPLOADED";
    doc.processingStatus = "COMPLETED";
    appState.queueItems.push(...res.data.queueItems);
    doc.history.unshift({
      timestamp: new Date().toLocaleTimeString(),
      event: "Uploaded and processed by backend extraction service"
    });
    showToast(`Uploaded and processed ${doc.name}`);
  }
  renderAll();
}

function bindIntakeLedgerControls() {
  document.getElementById("intake-search").addEventListener("input", (e) => {
    appState.intakeFilters.search = e.target.value;
    appState.intakePagination.page = 1;
    renderAll();
  });

  document.getElementById("intake-status-filter").addEventListener("change", (e) => {
    appState.intakeFilters.status = e.target.value;
    appState.intakePagination.page = 1;
    renderAll();
  });

  document.getElementById("intake-facility-filter").addEventListener("change", (e) => {
    appState.intakeFilters.facility = e.target.value;
    appState.intakePagination.page = 1;
    renderAll();
  });

  document.getElementById("intake-sort").addEventListener("change", (e) => {
    appState.intakeFilters.sort = e.target.value;
    renderAll();
  });

  document.getElementById("btn-intake-prev").addEventListener("click", () => {
    appState.intakePagination.page = Math.max(1, appState.intakePagination.page - 1);
    renderAll();
  });

  document.getElementById("btn-intake-next").addEventListener("click", () => {
    appState.intakePagination.page += 1;
    renderAll();
  });

  document.getElementById("intake-select-all").addEventListener("change", (e) => {
    const batchDocs = appState.documents.filter((d) => d.batchId === appState.activeBatchId);
    if (e.target.checked) {
      batchDocs.forEach((d) => appState.selectedDocIds.add(d.id));
    } else {
      appState.selectedDocIds.clear();
    }
    renderAll();
  });

  document.getElementById("btn-bulk-delete").addEventListener("click", () => {
    const count = appState.selectedDocIds.size;
    if (count === 0) return;
    if (!confirm(`Explicitly delete ${count} selected document(s) from this batch?`)) return;

    appState.documents = appState.documents.filter((d) => !appState.selectedDocIds.has(d.id));
    appState.queueItems = appState.queueItems.filter((q) => !appState.selectedDocIds.has(q.documentId));
    appState.selectedDocIds.clear();
    renderAll();
    showToast(`Deleted ${count} document(s) from batch.`);
  });
}

function bindQueueFilters() {
  document.querySelectorAll(".filter-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      appState.filters.statusTab = btn.getAttribute("data-status-tab");
      appState.pagination.page = 1;
      renderAll();
    });
  });

  document.getElementById("reason-filter").addEventListener("change", (e) => {
    appState.filters.reasonFilter = e.target.value;
    appState.pagination.page = 1;
    renderAll();
  });

  document.getElementById("queue-search").addEventListener("input", (e) => {
    appState.filters.searchQuery = e.target.value;
    appState.pagination.page = 1;
    renderAll();
  });

  document.getElementById("queue-sort").addEventListener("change", (e) => {
    appState.filters.sortBy = e.target.value;
    appState.pagination.page = 1;
    renderAll();
  });

  document.getElementById("btn-manual-inspect-doc").addEventListener("click", () => {
    const docId = document.getElementById("er-manual-doc-select").value;
    const doc = appState.documents.find((d) => d.id === docId);
    if (doc) openDocumentDirectly(doc);
  });

  document.getElementById("btn-run-quality-sample").addEventListener("click", runSupervisorQualitySample);
}

function runSupervisorQualitySample() {
  const rule = document.getElementById("er-sample-rule").value;
  const container = document.getElementById("er-sample-results");
  const verified = appState.queueItems.filter((i) => i.reviewStatus === "VERIFIED");

  if (verified.length === 0) {
    container.innerHTML = `<span class="mono-tag" style="color:var(--ink-muted);">No verified records available to sample in this batch yet.</span>`;
    return;
  }

  let pool = verified;
  if (rule === "LOW_MARGIN") {
    pool = verified.filter((i) => typeof i.ocrConfidence === "number" && i.ocrConfidence < 0.95);
  } else if (rule === "CORRECTED_ONLY") {
    pool = verified.filter((i) => i.correctedText !== undefined && i.correctedText !== i.extractedText);
  } else if (rule === "RATE_25") {
    const take = Math.max(1, Math.ceil(verified.length * 0.25));
    pool = verified.slice(0, take);
  }

  if (pool.length === 0) {
    container.innerHTML = `<span class="mono-tag" style="color:var(--ink-muted);">No verified records match the selected sampling rule.</span>`;
    return;
  }

  container.innerHTML = "";
  for (const item of pool) {
    const row = document.createElement("div");
    row.className = "er-sample-row";
    const conf = typeof item.ocrConfidence === "number" ? `${Math.round(item.ocrConfidence * 100)}%` : "—";
    row.innerHTML = `
      <div>
        <strong>${item.fieldName}</strong>
        <span class="mono-tag" style="margin-left:8px;">${item.documentName} · p.${item.pageNumber} · OCR ${conf}</span>
        <div style="font-size:12.5px; color:var(--ink-secondary); margin-top:2px;">Accepted value: "${item.correctedText !== undefined ? item.correctedText : item.extractedText || ""}"</div>
      </div>
      <button type="button" class="btn btn-sm">Audit in Split →</button>
    `;
    row.querySelector("button").addEventListener("click", () => openIssueInSplit(item.id));
    container.appendChild(row);
  }
}

/* ==========================================================================
   Unified Render Pipeline
   ========================================================================== */
function renderAll() {
  // Update Screen 01: The Project Index
  document.getElementById("pi-project-count-label").textContent =
    `${appState.projects.length} project${appState.projects.length === 1 ? "" : "s"} configured`;
  document.getElementById("notif-count").textContent =
    String(appState.queueItems.filter((i) => i.reviewStatus !== "VERIFIED").length);

  renderProjectIndex(appState, {
    onOpenProject: (projId) => {
      appState.activeProjectId = projId;
      const projBatches = appState.batches.filter((b) => b.projectId === projId);
      appState.activeBatchId = projBatches[0]?.id || null;
      switchView("intake");
    },
    onCreateProject: (mode) => openProjectModal(mode)
  });

  // Sync Project & Batch dropdowns
  const projSelect = document.getElementById("select-project");
  projSelect.innerHTML = appState.projects
    .map((p) => `<option value="${p.id}" ${p.id === appState.activeProjectId ? "selected" : ""}>${p.name}</option>`)
    .join("");

  const projBatches = appState.batches.filter((b) => b.projectId === appState.activeProjectId);
  const batchSelect = document.getElementById("select-batch");
  if (projBatches.length === 0) {
    batchSelect.innerHTML = `<option value="">No batches in project</option>`;
  } else {
    batchSelect.innerHTML = projBatches
      .map((b) => `<option value="${b.id}" ${b.id === appState.activeBatchId ? "selected" : ""}>${b.reference} — ${b.name}</option>`)
      .join("");
  }

  // Facility filter options
  const proj = appState.projects.find((p) => p.id === appState.activeProjectId);
  const facFilter = document.getElementById("intake-facility-filter");
  const currentFac = appState.intakeFilters.facility;
  facFilter.innerHTML = `<option value="ALL">All Facilities</option>` +
    (proj?.facilities || [])
      .map((f) => `<option value="${f}" ${f === currentFac ? "selected" : ""}>${f}</option>`)
      .join("");

  document.getElementById("btn-bulk-delete").hidden = appState.selectedDocIds.size === 0;

  // Render Screen 02: Receiving Desk
  renderIntakeOverview(appState);
  renderIntakeLedger(appState, {
    onOpenBatchModal: openBatchModal,
    onToggleSelect: (docId, checked) => {
      if (checked) appState.selectedDocIds.add(docId);
      else appState.selectedDocIds.delete(docId);
      document.getElementById("btn-bulk-delete").hidden = appState.selectedDocIds.size === 0;
    },
    onOpenDetail: (doc) => openDocumentDetailModal(doc),
    onToggleExpand: (docId) => {
      if (appState.expandedDocIds.has(docId)) appState.expandedDocIds.delete(docId);
      else appState.expandedDocIds.add(docId);
      renderAll();
    },
    onInspectDoc: (doc) => openDocumentDirectly(doc),
    onRetryDoc: async (doc) => {
      if (!doc.file) return;
      const res = await uploadFilesToBackend(appState.activeProjectId, [doc.file]);
      showToast(res.ok ? `Re-queued ${doc.name}` : res.message);
    },
    onDeleteDoc: (doc) => {
      if (!confirm(`Explicitly delete "${doc.name}" (${doc.docRef}) from this batch?`)) return;
      appState.documents = appState.documents.filter((d) => d.id !== doc.id);
      appState.queueItems = appState.queueItems.filter((q) => q.documentId !== doc.id);
      appState.selectedDocIds.delete(doc.id);
      renderAll();
      showToast(`Deleted ${doc.name}`);
    }
  });

  // Render Screen 03: Batch Review Queue
  const activeBatch = appState.batches.find((b) => b.id === appState.activeBatchId) || null;
  const activeBatchDocs = appState.documents.filter((d) => d.batchId === appState.activeBatchId);
  const batchQueueState = {
    ...appState,
    batch: activeBatch
      ? {
          batchId: activeBatch.reference,
          projectName: proj?.name || "Project",
          batchName: activeBatch.name,
          totalPages: activeBatchDocs.reduce((s, d) => s + (d.pageCount || 1), 0),
          processedPages: activeBatchDocs
            .filter((d) => d.processingStatus === "COMPLETED")
            .reduce((s, d) => s + (d.pageCount || 1), 0),
          updatedAt: activeBatch.createdAt
        }
      : null
  };

  renderBatchSummary(batchQueueState);
  renderQueueTable(appState, {
    onOpenIssue: (issueId) => openIssueInSplit(issueId),
    onPageChange: (newPage) => {
      appState.pagination.page = newPage;
      renderAll();
    }
  });

  renderMergerScreen(appState, {
    onInspectSource: (src) => {
      showToast(`${src.filename} (${src.clerkIdentity}) — ${src.importStatus}`);
    },
    onRemoveSource: (srcId) => {
      if (!confirm("Remove this .sav source file from the reconciliation bench? The original file on disk is untouched.")) return;
      appState.merger.sources = appState.merger.sources.filter((s) => s.id !== srcId);
      renderAll();
    },
    onChangeVarTarget: (vmId, newTarget) => {
      const vm = appState.merger.variableMappings.find((v) => v.id === vmId);
      if (vm) {
        vm.targetVar = newTarget;
        vm.approved = true;
        renderAll();
      }
    },
    onApproveVar: (vmId) => {
      const vm = appState.merger.variableMappings.find((v) => v.id === vmId);
      if (vm) {
        vm.approved = true;
        vm.excluded = false;
        const c = appState.merger.conflicts.find((cf) => cf.linkedId === vmId);
        if (c) c.status = "RESOLVED";
        renderAll();
        showToast(`Approved mapping: ${vm.sourceVar} → ${vm.targetVar}`);
      }
    },
    onCreateMasterVar: (vmId) => {
      const vm = appState.merger.variableMappings.find((v) => v.id === vmId);
      if (!vm) return;
      const newName = prompt("New Master Variable Name:", vm.sourceVar);
      if (!newName || !newName.trim()) return;
      vm.targetVar = newName.trim();
      if (!vm.targetOptions.includes(vm.targetVar)) vm.targetOptions.push(vm.targetVar);
      vm.approved = true;
      vm.excluded = false;
      const c = appState.merger.conflicts.find((cf) => cf.linkedId === vmId);
      if (c) c.status = "RESOLVED";
      renderAll();
      showToast(`Created master variable ${vm.targetVar}`);
    },
    onExcludeVar: (vmId) => {
      const vm = appState.merger.variableMappings.find((v) => v.id === vmId);
      if (!vm) return;
      const reason = prompt("Record reason for excluding this variable:");
      if (!reason || !reason.trim()) return;
      vm.excluded = true;
      vm.excludeReason = reason.trim();
      vm.approved = false;
      const c = appState.merger.conflicts.find((cf) => cf.linkedId === vmId);
      if (c) c.status = "RESOLVED";
      renderAll();
      showToast(`Excluded ${vm.sourceVar} (${vm.excludeReason})`);
    },
    onSelectCodebook: (cbId) => {
      appState.merger.selectedCodebookId = cbId;
      renderAll();
    },
    onApproveCodebook: (cbId) => {
      const cb = appState.merger.codebookMappings.find((x) => x.id === cbId);
      if (cb) {
        cb.approved = true;
        const c = appState.merger.conflicts.find((cf) => cf.linkedId === cbId);
        if (c) c.status = "RESOLVED";
        renderAll();
        showToast(`Approved codebook mapping: ${cb.sourceLabel} → ${cb.masterCode}`);
      }
    },
    onJumpToConflict: (c) => {
      appState.merger.activeSubTab = c.targetTab || "variables";
      if (c.linkedId && c.targetTab === "codebook") {
        appState.merger.selectedCodebookId = c.linkedId;
      }
      renderAll();
    },
    onExecuteMerge: async () => {
      const res = await executeMasterMergeOnBackend(appState.activeProjectId, {
        sources: appState.merger.sources.map((s) => s.id),
        variableMappings: appState.merger.variableMappings,
        codebookMappings: appState.merger.codebookMappings
      });
      if (!res.ok) {
        showToast(res.message);
      } else {
        appState.merger.mergeCompleted = true;
        renderAll();
        showToast("Master .SAV dataset generated successfully.");
      }
    }
  });

  renderObservatoryScreen(appState, {
    onSelectIssue: (issueId) => {
      appState.observatory.selectedIssueId = issueId;
      renderAll();
    },
    onToggleCategory: (catKey) => {
      appState.observatory.filters.category =
        appState.observatory.filters.category === catKey ? "ALL" : catKey;
      appState.observatory.pagination.page = 1;
      renderAll();
    },
    onToggleField: (fld) => {
      appState.observatory.filters.field =
        appState.observatory.filters.field === fld ? "ALL" : fld;
      appState.observatory.pagination.page = 1;
      renderAll();
    },
    onJumpToEvidence: (linkedIssueId) => {
      openIssueInSplit(linkedIssueId);
    },
    onResolveIssue: (issueId, newStatus, payload) => {
      const iss = appState.observatory.issues.find((i) => i.id === issueId);
      if (!iss) return;
      iss.resolutionStatus = newStatus;
      if (payload.correctedValue !== undefined) {
        iss.correctedValue = payload.correctedValue;
      }
      iss.auditHistory = iss.auditHistory || [];
      iss.auditHistory.unshift({
        timestamp: new Date().toLocaleTimeString(),
        reviewer: "M&E Supervisor (Local Session)",
        action: payload.actionLabel,
        reason: payload.reason || ""
      });
      appState.observatory.supervisorApproved = false;
      renderAll();
      showToast(`${iss.ruleId}: ${payload.actionLabel}`);
    },
    onApproveDataset: () => {
      appState.observatory.supervisorApproved = true;
      appState.observatory.approvedAt = new Date().toLocaleTimeString();
      renderAll();
      showToast("Dataset approved for analysis with full audit trail.");
    }
  });

  document.getElementById("nav-split").disabled = !appState.activeIssueId && !appState.activeDirectDocId;
}

function openDocumentDirectly(doc) {
  appState.activeIssueId = null;
  appState.activeDirectDocId = doc.id;
  document.getElementById("nav-split").disabled = false;
  switchView("split");

  renderEvidenceSplit(
    null,
    doc,
    { positionIndex: -1, totalInView: 0 },
    { onDecision: () => {}, onEditSave: () => {} }
  );
}

function openIssueInSplit(issueId) {
  const item = appState.queueItems.find((i) => i.id === issueId);
  if (!item) return;

  appState.activeIssueId = issueId;
  appState.activeDirectDocId = null;
  document.getElementById("nav-split").disabled = false;
  switchView("split");

  const doc = appState.documents.find((d) => d.id === item.documentId) || null;
  const currentList = filterQueueItems(appState.queueItems, appState.filters);
  const posIdx = currentList.findIndex((i) => i.id === issueId);

  document.getElementById("decision-backend-note").textContent = appState.syntheticMode
    ? "Synthetic test session"
    : "Local decision log";

  renderEvidenceSplit(
    item,
    doc,
    { positionIndex: posIdx, totalInView: currentList.length },
    {
      onDecision: handleDecision,
      onEditSave: handleEditSave
    }
  );
}

async function handleDecision(issueId, newStatus) {
  const item = appState.queueItems.find((i) => i.id === issueId);
  if (!item) return;

  const prevStatus = item.reviewStatus;
  item.reviewStatus = newStatus;
  item.lastReviewer = "Records Clerk (Local Session)";
  item.auditHistory = item.auditHistory || [];
  item.auditHistory.unshift({
    timestamp: new Date().toLocaleTimeString(),
    isoTimestamp: new Date().toISOString(),
    reviewer: item.lastReviewer,
    previousStatus: prevStatus,
    newStatus,
    confidenceAtExtraction: item.ocrConfidence,
    originalValue: item.extractedText,
    action: `Marked as ${newStatus} (from ${prevStatus})`,
    note: newStatus === "VERIFIED" ? "Confirmed by reviewer" : "Flagged for investigation"
  });

  await submitDecisionToBackend(appState.activeProjectId, issueId, {
    status: newStatus,
    correctedText: item.correctedText,
    selectedCodebookCode: item.selectedCodebookCode
  });

  showToast(`Recorded: ${item.fieldName} → ${newStatus}`);
  advanceToNextUnresolved(issueId);
}

async function handleEditSave(issueId, editPayload) {
  const item = appState.queueItems.find((i) => i.id === issueId);
  if (!item) return;

  const prevStatus = item.reviewStatus;
  item.correctedText = editPayload.correctedText;
  item.selectedCodebookCode = editPayload.selectedCodebookCode;
  item.selectedCodebookLabel = editPayload.selectedCodebookLabel;
  item.markedUnreadable = editPayload.markedUnreadable;
  item.markedUnrecognised = editPayload.markedUnrecognised;
  item.lastReviewer = "Records Clerk (Local Session)";
  item.reviewStatus =
    editPayload.markedUnreadable || editPayload.markedUnrecognised ? "FLAGGED" : "VERIFIED";

  item.auditHistory = item.auditHistory || [];
  item.auditHistory.unshift({
    timestamp: new Date().toLocaleTimeString(),
    isoTimestamp: new Date().toISOString(),
    reviewer: item.lastReviewer,
    previousStatus: prevStatus,
    newStatus: item.reviewStatus,
    confidenceAtExtraction: item.ocrConfidence,
    originalValue: item.extractedText,
    correctedValue: editPayload.correctedText,
    action: `Edited (${item.reviewStatus}) · Original "${item.extractedText || "Blank"}" → "${editPayload.correctedText}"`,
    note: editPayload.note
  });

  await submitDecisionToBackend(appState.activeProjectId, issueId, editPayload);

  showToast(`Saved correction for ${item.fieldName}`);
  advanceToNextUnresolved(issueId);
}

function advanceToNextUnresolved(currentId) {
  const remaining = appState.queueItems.filter(
    (i) => i.id !== currentId && (i.reviewStatus === "AWAITING_REVIEW" || i.reviewStatus === "PROCESSING_FAILED")
  );
  if (remaining.length > 0) {
    openIssueInSplit(remaining[0].id);
  } else {
    renderAll();
    switchView("queue");
    showToast("No remaining unresolved review issues.");
  }
}

function navigateIssue(delta) {
  if (!confirmDiscardUnsavedChanges()) return;
  const currentList = filterQueueItems(appState.queueItems, appState.filters);
  const idx = currentList.findIndex((i) => i.id === appState.activeIssueId);
  if (idx === -1) return;
  const target = currentList[idx + delta];
  if (target) openIssueInSplit(target.id);
}

function bindKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    if (appState.view !== "split" || !appState.activeIssueId) return;
    const tag = document.activeElement?.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

    const item = appState.queueItems.find((i) => i.id === appState.activeIssueId);
    if (!item) return;

    if (e.key === "Enter") {
      e.preventDefault();
      handleDecision(item.id, "VERIFIED");
    } else if (e.key.toLowerCase() === "e") {
      e.preventDefault();
      openEditDrawer(item, { onDecision: handleDecision, onEditSave: handleEditSave });
    } else if (e.key.toLowerCase() === "f") {
      e.preventDefault();
      handleDecision(item.id, "FLAGGED");
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      navigateIssue(-1);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      navigateIssue(1);
    } else if (e.key === "+" || e.key === "=") {
      e.preventDefault();
      setZoom(viewerState.zoom + 0.15);
    } else if (e.key === "-") {
      e.preventDefault();
      setZoom(viewerState.zoom - 0.15);
    }
  });
}

function showToast(msg) {
  const toast = document.getElementById("feedback-toast");
  toast.textContent = msg;
  toast.hidden = false;
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => {
    toast.hidden = true;
  }, 3600);
}

/* ==========================================================================
   Isolated Synthetic Dev Fixture (OFF by default)
   ========================================================================== */
function bindSyntheticDevPreview() {
  document.getElementById("btn-toggle-synthetic").addEventListener("click", () => {
    if (appState.syntheticMode) exitSyntheticMode();
    else loadSyntheticDevFixture();
  });
  document.getElementById("btn-exit-synthetic").addEventListener("click", exitSyntheticMode);
}

function exitSyntheticMode() {
  appState.syntheticMode = false;
  appState.batches = appState.batches.filter((b) => !b.id.startsWith("synth_"));
  appState.activeBatchId = appState.batches[0]?.id || null;
  appState.documents = [];
  appState.queueItems = [];
  appState.selectedDocIds.clear();
  appState.activeIssueId = null;
  appState.activeDirectDocId = null;
  appState.merger.sources = [];
  appState.merger.variableMappings = [];
  appState.merger.codebookMappings = [];
  appState.merger.conflicts = [];
  appState.merger.duplicateCandidatesCount = 0;
  appState.observatory.validationStatus = "NOT_STARTED";
  appState.observatory.records = [];
  appState.observatory.issues = [];
  appState.observatory.selectedIssueId = null;
  appState.observatory.supervisorApproved = false;
  appState.observatory.approvedAt = null;
  appState.merger.activeSubTab = "sources";
  document.getElementById("synthetic-banner").hidden = true;
  document.getElementById("btn-toggle-synthetic").textContent = "Dev Preview: Synthetic Fixture";
  switchView("intake");
}

function createSyntheticFormSvgUrl(docLabel, highlightedLine) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="540" height="720" viewBox="0 0 540 720">
      <rect width="540" height="720" fill="#FCFBF7" stroke="#CBD5E1" stroke-width="2"/>
      <text x="32" y="46" font-family="monospace" font-size="13" font-weight="bold" fill="#202824">SYNTHETIC TEST FORM (NON-CLINICAL FIXTURE)</text>
      <text x="32" y="68" font-family="monospace" font-size="11" fill="#858B83">${docLabel}</text>
      <line x1="32" y1="84" x2="508" y2="84" stroke="#202824" stroke-width="1.5"/>
      <text x="32" y="130" font-family="sans-serif" font-size="13" fill="#48504B">Respondent ID: SYNTH-0041  |  Sex: [x] Female  |  Age: 44</text>
      <text x="32" y="210" font-family="sans-serif" font-size="12" fill="#858B83">FIELD UNDER REVIEW:</text>
      <text x="36" y="245" font-family="serif" font-style="italic" font-size="24" fill="#17201D">${highlightedLine}</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function loadSyntheticDevFixture() {
  appState.syntheticMode = true;
  document.getElementById("synthetic-banner").hidden = false;
  document.getElementById("btn-toggle-synthetic").textContent = "Exit Synthetic Preview";

  const synthBatchId = "synth_batch_01";
  appState.batches.unshift({
    id: synthBatchId,
    reference: "BATCH-2026-SYNTH",
    name: "Synthetic Test Batch (Non-Clinical)",
    projectId: appState.activeProjectId,
    projectName: "OYSHIA Encounter Forms",
    facility: "Synthetic Clinic A",
    reportingPeriod: "Test Cycle",
    createdAt: new Date().toISOString(),
    lifecycleStatus: "REVIEW_REQUIRED"
  });
  appState.activeBatchId = synthBatchId;

  const doc1Url = createSyntheticFormSvgUrl("SYNTH-DOC-01 · Page 2", "Mss wrist pain (?trauma)");
  const doc2Url = createSyntheticFormSvgUrl("SYNTH-DOC-02 · Page 1", "Herbal tonic");

  appState.documents = [
    {
      id: "SYNTH-DOC-01",
      docRef: "DOC-0001",
      batchId: synthBatchId,
      name: "synthetic_form_01.png",
      detectedFormat: "PNG",
      facility: "Synthetic Clinic A",
      sizeBytes: 184200,
      isPdf: false,
      pageCount: 4,
      syntheticSvgUrl: doc1Url,
      uploadStatus: "UPLOADED",
      processingStatus: "NEEDS_ATTENTION",
      uploadedAt: new Date().toISOString(),
      pages: buildPageRecords("SYNTH-DOC-01", 4).map((p, idx) => ({
        ...p,
        processingStatus: "COMPLETED",
        extractionStatus: idx === 1 ? "NEEDS_REVIEW" : "COMPLETED",
        validationStatus: idx === 1 ? "NEEDS_REVIEW" : "VALID"
      })),
      history: [{ timestamp: "10:00:00", event: "Loaded synthetic test document" }]
    },
    {
      id: "SYNTH-DOC-02",
      docRef: "DOC-0002",
      batchId: synthBatchId,
      name: "synthetic_form_02.png",
      detectedFormat: "PNG",
      facility: "Synthetic Clinic A",
      sizeBytes: 142900,
      isPdf: false,
      pageCount: 2,
      syntheticSvgUrl: doc2Url,
      uploadStatus: "UPLOADED",
      processingStatus: "NEEDS_ATTENTION",
      uploadedAt: new Date().toISOString(),
      pages: buildPageRecords("SYNTH-DOC-02", 2).map((p, idx) => ({
        ...p,
        processingStatus: "COMPLETED",
        extractionStatus: idx === 0 ? "NEEDS_REVIEW" : "COMPLETED",
        validationStatus: idx === 0 ? "NEEDS_REVIEW" : "VALID"
      })),
      history: [{ timestamp: "10:02:00", event: "Loaded synthetic test document" }]
    }
  ];

  appState.queueItems = [
    {
      id: "iss_1",
      documentId: "SYNTH-DOC-01",
      documentName: "synthetic_form_01.png",
      pageNumber: 2,
      totalPages: 4,
      fieldName: "Diagnosis2",
      reasonCode: "LOW_CONFIDENCE",
      reasonLabel: "Low-confidence extraction",
      extractedText: "Mss wrist pain (?trauma)",
      ocrConfidence: 0.68,
      codebookSimilarity: 0.91,
      suggestedCodebookCode: "1.0",
      suggestedCodebookLabel: "1.0 — MSS OF THE WRIST",
      codebookOptions: [
        { code: "1.0", label: "MSS OF THE WRIST" },
        { code: "13.0", label: "MSS PAIN" }
      ],
      validationMessage: "OCR confidence (68%) is below the 90% auto-commit threshold.",
      reviewStatus: "AWAITING_REVIEW",
      severity: "MEDIUM",
      bbox: { xPct: 5, yPct: 29, wPct: 84, hPct: 10 },
      auditHistory: []
    },
    {
      id: "iss_2",
      documentId: "SYNTH-DOC-02",
      documentName: "synthetic_form_02.png",
      pageNumber: 1,
      totalPages: 2,
      fieldName: "Treatment1",
      reasonCode: "UNRECOGNISED_TERM",
      reasonLabel: "Unrecognised clinical term",
      extractedText: "Herbal tonic",
      ocrConfidence: 0.92,
      codebookSimilarity: 0.34,
      codebookOptions: [
        { code: "14.0", label: "Amlodipine" },
        { code: "88.0", label: "Diclofenac" }
      ],
      validationMessage: "OCR legibility is high (92%), but codebook similarity is 34%.",
      reviewStatus: "AWAITING_REVIEW",
      severity: "HIGH",
      bbox: { xPct: 5, yPct: 29, wPct: 84, hPct: 10 },
      auditHistory: []
    }
  ];

  appState.merger.sources = [
    {
      id: "sav_synth_1",
      filename: "ClerkA_OYSHIA_Jan.sav",
      sizeBytes: 248320,
      header: "$FL2 (Valid SPSS)",
      clerkIdentity: "Clerk A — Regional PHC",
      recordCount: 412,
      variableCount: 28,
      importStatus: "PARSED",
      schemaStatus: "Baseline Schema",
      reconciliationStatus: "Aligned",
      importedAt: new Date().toISOString()
    },
    {
      id: "sav_synth_2",
      filename: "ClerkB_OYSHIA_Jan.sav",
      sizeBytes: 194560,
      header: "$FL2 (Valid SPSS)",
      clerkIdentity: "Clerk B — District Annex",
      recordCount: 305,
      variableCount: 27,
      importStatus: "PARSED",
      schemaStatus: "2 Drift Issues",
      reconciliationStatus: "Needs Review",
      importedAt: new Date().toISOString()
    },
    {
      id: "sav_synth_3",
      filename: "ClerkC_OYSHIA_Jan.sav",
      sizeBytes: 162880,
      header: "$FL2 (Valid SPSS)",
      clerkIdentity: "Clerk C — Mobile Outreach",
      recordCount: 218,
      variableCount: 29,
      importStatus: "PARSED",
      schemaStatus: "1 Unmapped Var",
      reconciliationStatus: "Needs Review",
      importedAt: new Date().toISOString()
    }
  ];

  appState.merger.variableMappings = [
    {
      id: "vm_1",
      sourceVar: "Sex",
      sourceFile: "ClerkA_OYSHIA_Jan.sav",
      sourceType: "Numeric (F8.0)",
      sourceMeasure: "Nominal",
      sourceLabel: "Patient biological sex",
      matchClass: "EXACT_MATCH",
      rationale: "Identical variable name, numeric storage width, and nominal scale.",
      affectedRecords: 412,
      targetVar: "Sex",
      targetOptions: ["Sex", "Patient_Sex", "Gender_Code"],
      targetSpec: "Numeric (F8.0) · Nominal",
      approved: true,
      excluded: false,
      excludeReason: ""
    },
    {
      id: "vm_2",
      sourceVar: "treatment2",
      sourceFile: "ClerkB_OYSHIA_Jan.sav",
      sourceType: "Numeric (F8.2)",
      sourceMeasure: "Nominal",
      sourceLabel: "Secondary prescribed medication",
      matchClass: "STRONG_SUGGESTION",
      rationale: "Case-insensitive name match (treatment2 → Treatment2) with identical value domain.",
      affectedRecords: 305,
      targetVar: "Treatment2",
      targetOptions: ["Treatment2", "Treatment1", "Notes_Other"],
      targetSpec: "Numeric (F8.2) · Nominal",
      approved: false,
      excluded: false,
      excludeReason: ""
    },
    {
      id: "vm_3",
      sourceVar: "Diag_Primary",
      sourceFile: "ClerkC_OYSHIA_Jan.sav",
      sourceType: "Numeric (F8.0)",
      sourceMeasure: "Nominal",
      sourceLabel: "Primary clinical diagnosis code",
      matchClass: "POSSIBLE_MATCH",
      rationale: "Semantic label overlap with master Diagnosis1 (0.84 token similarity).",
      affectedRecords: 218,
      targetVar: "Diagnosis1",
      targetOptions: ["Diagnosis1", "Diagnosis2", "Diag_Primary"],
      targetSpec: "Numeric (F8.2) · Nominal",
      approved: false,
      excluded: false,
      excludeReason: ""
    },
    {
      id: "vm_4",
      sourceVar: "Outreach_Van_ID",
      sourceFile: "ClerkC_OYSHIA_Jan.sav",
      sourceType: "String (A16)",
      sourceMeasure: "Nominal",
      sourceLabel: "Mobile unit identifier",
      matchClass: "NO_MATCH",
      rationale: "No corresponding variable in master template; create new variable or exclude.",
      affectedRecords: 218,
      targetVar: "Outreach_Van_ID",
      targetOptions: ["Outreach_Van_ID", "Facility_Code"],
      targetSpec: "String (A16) · Nominal",
      approved: false,
      excluded: false,
      excludeReason: ""
    },
    {
      id: "vm_5",
      sourceVar: "Age_Years",
      sourceFile: "ClerkB_OYSHIA_Jan.sav",
      sourceType: "String (A8)",
      sourceMeasure: "Nominal",
      sourceLabel: "Age recorded as text",
      matchClass: "INCOMPATIBLE",
      rationale: "String type (A8) cannot merge directly into master Numeric (F8.0) Age without coercion.",
      affectedRecords: 305,
      targetVar: "Age",
      targetOptions: ["Age", "Age_Text_Raw"],
      targetSpec: "Numeric (F8.0) · Scale",
      approved: false,
      excluded: false,
      excludeReason: ""
    }
  ];

  appState.merger.codebookMappings = [
    {
      id: "cb_1",
      sourceClerk: "Clerk B",
      variableName: "Sex",
      sourceCode: "0",
      sourceLabel: "Male",
      masterCode: "1",
      masterLabel: "Male",
      affectedRecords: 142,
      rationale: "Clerk B coded 0=Male instead of Master 1=Male; remap required to avoid collision.",
      hasCollision: true,
      approved: false
    },
    {
      id: "cb_2",
      sourceClerk: "Clerk B",
      variableName: "Sex",
      sourceCode: "1",
      sourceLabel: "Female",
      masterCode: "2",
      masterLabel: "Female",
      affectedRecords: 163,
      rationale: "Clerk B value 1 collides with Master 1=Male; remap 1→2 preserves Female classification.",
      hasCollision: true,
      approved: false
    },
    {
      id: "cb_3",
      sourceClerk: "Clerk C",
      variableName: "Diagnosis1",
      sourceCode: "265",
      sourceLabel: "Costochondritis",
      masterCode: "266.0",
      masterLabel: "Costochondritis (Musculoskeletal)",
      affectedRecords: 19,
      rationale: "Aligned to official OYSHIA master diagnosis codebook entry 266.0.",
      hasCollision: false,
      approved: true
    }
  ];

  appState.merger.conflicts = [
    {
      id: "cf_1",
      severity: "MANDATORY",
      type: "Value Label Collision",
      sourceFiles: ["ClerkB_OYSHIA_Jan.sav"],
      variable: "Sex",
      affectedRecords: 305,
      recommendedResolution: "Approve 0→1 (Male) and 1→2 (Female) codebook remap before merge.",
      status: "UNRESOLVED",
      targetTab: "codebook",
      linkedId: "cb_1"
    },
    {
      id: "cf_2",
      severity: "MANDATORY",
      type: "Storage Type Mismatch",
      sourceFiles: ["ClerkB_OYSHIA_Jan.sav"],
      variable: "Age_Years → Age",
      affectedRecords: 305,
      recommendedResolution: "Confirm numeric coercion to F8.0 or route to Age_Text_Raw.",
      status: "UNRESOLVED",
      targetTab: "variables",
      linkedId: "vm_5"
    },
    {
      id: "cf_3",
      severity: "WARNING",
      type: "Case / Naming Drift",
      sourceFiles: ["ClerkB_OYSHIA_Jan.sav"],
      variable: "treatment2 → Treatment2",
      affectedRecords: 305,
      recommendedResolution: "Accept STRONG_SUGGESTION alignment to Treatment2.",
      status: "UNRESOLVED",
      targetTab: "variables",
      linkedId: "vm_2"
    }
  ];

  appState.merger.duplicateCandidatesCount = 3;

  appState.observatory.validationStatus = "NOT_STARTED";
  appState.observatory.issues = [];
  appState.observatory.selectedIssueId = null;
  appState.observatory.supervisorApproved = false;
  appState.observatory.records = [
    {
      Respondent_ID: "SYNTH-1001",
      Age: 142,
      Sex: "Female",
      Diagnosis1: "I10",
      Treatment1: "Amoxicillin",
      Facility_Code: "PHC-01",
      Encounter_Date: "2026-02-04",
      sourceFile: "ClerkA_OYSHIA_Jan.sav",
      sourceClerk: "Clerk A — Regional PHC",
      originalRowNumber: 14,
      linkedIssueId: "iss_1"
    },
    {
      Respondent_ID: "SYNTH-1002",
      Age: 29,
      Sex: "Male",
      Diagnosis1: "O80",
      Treatment1: "Paracetamol",
      Facility_Code: "PHC-02",
      Encounter_Date: "2026-02-05",
      sourceFile: "ClerkB_OYSHIA_Jan.sav",
      sourceClerk: "Clerk B — District Annex",
      originalRowNumber: 38
    },
    {
      Respondent_ID: "SYNTH-1003",
      Age: 44,
      Sex: "",
      Diagnosis1: "J06",
      Treatment1: "Insulin",
      Facility_Code: "PHC-01",
      Encounter_Date: "2026-02-06",
      sourceFile: "ClerkB_OYSHIA_Jan.sav",
      sourceClerk: "Clerk B — District Annex",
      originalRowNumber: 52,
      linkedIssueId: "iss_2"
    },
    {
      Respondent_ID: "SYNTH-1004",
      Age: 36,
      Sex: "Female",
      Diagnosis1: "UNMAPPED-999",
      Treatment1: "Diclofenac",
      Facility_Code: "PHC-03",
      Encounter_Date: "2026-02-07",
      sourceFile: "ClerkC_OYSHIA_Jan.sav",
      sourceClerk: "Clerk C — Mobile Outreach",
      originalRowNumber: 71
    },
    {
      Respondent_ID: "SYNTH-1001",
      Age: 48,
      Sex: "Female",
      Diagnosis1: "I10",
      Treatment1: "Amlodipine",
      Facility_Code: "PHC-01",
      Encounter_Date: "2026-02-04",
      sourceFile: "ClerkC_OYSHIA_Jan.sav",
      sourceClerk: "Clerk C — Mobile Outreach",
      originalRowNumber: 89
    }
  ];

  renderAll();
  showToast("Loaded isolated synthetic test fixture.");
}

function bindMergerControls() {
  document.querySelectorAll(".mm-step-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      appState.merger.activeSubTab = btn.getAttribute("data-mm-tab");
      renderAll();
    });
  });

  document.getElementById("mm-conf-sev").addEventListener("change", (e) => {
    appState.merger.conflictFilters.severity = e.target.value;
    renderAll();
  });

  document.getElementById("mm-conf-type").addEventListener("change", (e) => {
    appState.merger.conflictFilters.type = e.target.value;
    renderAll();
  });

  const dropzone = document.getElementById("mm-dropzone");
  const fileInput = document.getElementById("mm-file-input");

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("drag-over");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag-over");
    if (e.dataTransfer?.files?.length) handleMergerSavFiles(Array.from(e.dataTransfer.files));
  });
  fileInput.addEventListener("change", (e) => {
    if (e.target.files?.length) {
      handleMergerSavFiles(Array.from(e.target.files));
      fileInput.value = "";
    }
  });
}

async function handleMergerSavFiles(files) {
  const clerkName = document.getElementById("mm-clerk-input").value.trim();
  const validSavFiles = [];

  for (const file of files) {
    const check = await validateSavMagicBytes(file);
    if (!check.valid) {
      showToast(`${file.name}: ${check.error}`);
      continue;
    }

    const srcObj = {
      id: `sav_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      file,
      filename: file.name,
      sizeBytes: file.size,
      header: check.header,
      clerkIdentity: clerkName || file.name.replace(/\.sav$/i, ""),
      recordCount: null,
      variableCount: null,
      importStatus: "LOCAL_SESSION",
      schemaStatus: "Pending pyreadstat",
      reconciliationStatus: "Awaiting Inspection",
      importedAt: new Date().toISOString()
    };

    appState.merger.sources.unshift(srcObj);
    validSavFiles.push(srcObj);
  }

  renderAll();

  if (validSavFiles.length > 0) {
    const res = await inspectMergeFilesOnBackend(
      appState.activeProjectId,
      validSavFiles.map((s) => s.file)
    );
    if (!res.ok) {
      showToast(res.message);
    }
  }
}

function bindObservatoryControls() {
  document.getElementById("qo-btn-back-prev").addEventListener("click", () => switchView("queue"));

  document.getElementById("qo-btn-run-validation").addEventListener("click", async () => {
    const qo = appState.observatory;
    if (qo.records.length === 0 && !appState.backendConnected) {
      showToast("No dataset records loaded. Connect the FastAPI backend or load Synthetic Preview.");
      return;
    }

    const rulesConfig = {
      value: document.getElementById("qo-rule-value").checked,
      logical: document.getElementById("qo-rule-logical").checked,
      duplicates: document.getElementById("qo-rule-duplicates").checked,
      prescription: document.getElementById("qo-rule-rx").checked
    };

    qo.validationStatus = "RUNNING";
    renderAll();

    const backendRes = await runQualityValidationOnBackend(appState.activeProjectId, {
      batchId: appState.activeBatchId,
      rules: rulesConfig
    });

    if (backendRes.ok && Array.isArray(backendRes.data?.issues)) {
      qo.issues = backendRes.data.issues;
      qo.validationStatus = "COMPLETED";
    } else {
      qo.issues = runQualityValidation(qo.records, rulesConfig);
      qo.validationStatus = "COMPLETED";
    }

    qo.selectedIssueId = qo.issues[0]?.id || null;
    qo.supervisorApproved = false;
    qo.pagination.page = 1;
    renderAll();
    showToast(`Validation completed: ${qo.issues.length} issue(s) identified across ${qo.records.length} record(s).`);
  });

  document.querySelectorAll("[data-qo-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-qo-tab]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      appState.observatory.filters.statusTab = btn.getAttribute("data-qo-tab");
      appState.observatory.pagination.page = 1;
      renderAll();
    });
  });

  document.getElementById("qo-sort").addEventListener("change", (e) => {
    appState.observatory.filters.sortBy = e.target.value;
    appState.observatory.pagination.page = 1;
    renderAll();
  });

  document.getElementById("qo-search").addEventListener("input", (e) => {
    appState.observatory.filters.search = e.target.value;
    appState.observatory.pagination.page = 1;
    renderAll();
  });

  document.getElementById("qo-btn-clear-landscape").addEventListener("click", () => {
    appState.observatory.filters.category = "ALL";
    appState.observatory.filters.field = "ALL";
    appState.observatory.pagination.page = 1;
    renderAll();
  });

  document.getElementById("qo-prev-page").addEventListener("click", () => {
    appState.observatory.pagination.page = Math.max(1, appState.observatory.pagination.page - 1);
    renderAll();
  });

  document.getElementById("qo-next-page").addEventListener("click", () => {
    appState.observatory.pagination.page += 1;
    renderAll();
  });
}
