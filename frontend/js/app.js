/**
 * MediExtract — Receiving Desk & Evidence Review Workstation
 * Unified State: Project -> Batch -> Documents -> Pages -> Review Queue
 */

import { checkBackendConnection, uploadFilesToBackend, submitDecisionToBackend } from "./api.js";
import { validateUploadFile, inspectLocalFile } from "./upload.js";
import { renderProjectIndex } from "./project-index.js";
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
import { initViewerControls, renderEvidenceSplit, openEditDrawer, setZoom, viewerState } from "./evidence-split.js";

const appState = {
  view: "home", // "home" | "intake" | "queue" | "split" | "analytics" | "settings"
  syntheticMode: false,
  projectsLoading: false,
  projectsError: null,
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
    searchQuery: ""
  },
  pagination: { page: 1 }
};

document.addEventListener("DOMContentLoaded", async () => {
  initViewerControls();
  bindNavigation();
  bindProjectAndBatchControls();
  bindIntakeUploadControls();
  bindIntakeLedgerControls();
  bindQueueFilters();
  bindKeyboardShortcuts();
  bindSyntheticDevPreview();

  await refreshBackendStatus();
  renderAll();
});

async function refreshBackendStatus() {
  const status = await checkBackendConnection();
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
  appState.view = viewName;
  ["home", "intake", "queue", "split", "analytics", "settings"].forEach((v) => {
    const el = document.getElementById("view-" + v);
    if (el) el.hidden = v !== viewName;
    const nav = document.getElementById("nav-" + v);
    if (nav) nav.classList.toggle("active", v === viewName);
  });
  document.getElementById("nav-projects").classList.remove("active");

  // Show project/batch hierarchy breadcrumb inside workflow screens
  const showCrumb = viewName === "intake" || viewName === "queue" || viewName === "split";
  document.getElementById("hierarchy-breadcrumb-bar").hidden = !showCrumb;

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
  doc.uploadStatus = "UPLOADED";
  doc.processingStatus = "QUEUED";
  doc.pages = buildPageRecords(doc.id, doc.pageCount);
  doc.history = [
    {
      timestamp: new Date().toLocaleTimeString(),
      event: `Uploaded to ${batch.reference} (${doc.pageCount || 1} page(s), ${doc.detectedFormat})`
    }
  ];

  appState.documents.unshift(doc);
  renderAll();

  const res = await uploadFilesToBackend(appState.activeProjectId, [doc.file]);
  if (!res.ok) {
    doc.history.unshift({
      timestamp: new Date().toLocaleTimeString(),
      event: "Stored in browser session (Backend processing service unavailable)"
    });
    showToast(res.message);
  } else if (res.data?.queueItems) {
    doc.processingStatus = "COMPLETED";
    appState.queueItems.push(...res.data.queueItems);
    doc.history.unshift({
      timestamp: new Date().toLocaleTimeString(),
      event: "Processed by backend extraction service"
    });
    showToast(`Processed ${doc.name}`);
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

  item.reviewStatus = newStatus;
  item.auditHistory = item.auditHistory || [];
  item.auditHistory.unshift({
    timestamp: new Date().toLocaleTimeString(),
    action: `Marked as ${newStatus}`,
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

  item.correctedText = editPayload.correctedText;
  item.selectedCodebookCode = editPayload.selectedCodebookCode;
  item.selectedCodebookLabel = editPayload.selectedCodebookLabel;
  item.markedUnreadable = editPayload.markedUnreadable;
  item.markedUnrecognised = editPayload.markedUnrecognised;
  item.reviewStatus =
    editPayload.markedUnreadable || editPayload.markedUnrecognised ? "FLAGGED" : "VERIFIED";

  item.auditHistory = item.auditHistory || [];
  item.auditHistory.unshift({
    timestamp: new Date().toLocaleTimeString(),
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

  renderAll();
  showToast("Loaded isolated synthetic test fixture.");
}
