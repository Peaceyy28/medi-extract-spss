/**
 * MediExtract — Evidence Review Workstation Application State & Orchestration
 */

import { checkBackendConnection, uploadFilesToBackend, submitDecisionToBackend } from "./api.js";
import { validateUploadFile, inspectLocalFile, renderUploadedFileList } from "./upload.js";
import { renderBatchSummary, renderQueueTable, filterQueueItems } from "./queue.js";
import { initViewerControls, renderEvidenceSplit, openEditDrawer, setZoom, viewerState } from "./evidence-split.js";

const appState = {
  view: "queue", // "queue" | "split"
  syntheticMode: false,
  batch: null,
  documents: [],
  queueItems: [],
  activeIssueId: null,
  activeDirectDocId: null,
  filters: {
    statusTab: "NEEDS_REVIEW",
    reasonFilter: "ALL_UNRESOLVED",
    searchQuery: ""
  },
  pagination: {
    page: 1
  }
};

document.addEventListener("DOMContentLoaded", async () => {
  initViewerControls();
  bindNavigation();
  bindUploadControls();
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
    text.textContent = "Backend API: Connected";
  } else {
    pill.classList.remove("connected");
    text.textContent = "Backend API: Offline (Local Boundary)";
  }
}

function bindNavigation() {
  document.getElementById("nav-queue").addEventListener("click", () => switchView("queue"));
  document.getElementById("nav-split").addEventListener("click", () => {
    if (appState.activeIssueId || appState.activeDirectDocId) {
      switchView("split");
    }
  });
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
  document.getElementById("view-queue").hidden = viewName !== "queue";
  document.getElementById("view-split").hidden = viewName !== "split";

  document.getElementById("nav-queue").classList.toggle("active", viewName === "queue");
  document.getElementById("nav-split").classList.toggle("active", viewName === "split");

  if (viewName === "queue") {
    renderAll();
  }
}

function bindUploadControls() {
  const dropzone = document.getElementById("upload-dropzone");
  const fileInput = document.getElementById("file-upload-input");

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
      handleFilesSelected(Array.from(e.dataTransfer.files));
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files?.length) {
      handleFilesSelected(Array.from(e.target.files));
      fileInput.value = "";
    }
  });
}

async function handleFilesSelected(files) {
  if (appState.syntheticMode) {
    exitSyntheticMode();
  }

  const validFiles = [];
  for (const file of files) {
    const check = validateUploadFile(file);
    if (!check.valid) {
      appState.documents.unshift({
        id: `err_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        name: file.name,
        sizeBytes: file.size,
        isPdf: false,
        pageCount: 0,
        objectUrl: null,
        uploadProgress: 0,
        processingState: "UPLOAD_ERROR",
        errorMessage: check.error
      });
    } else {
      const inspected = await inspectLocalFile(file);
      appState.documents.unshift(inspected);
      validFiles.push(inspected);
    }
  }

  renderAll();

  if (validFiles.length > 0) {
    const res = await uploadFilesToBackend(
      "proj_default",
      validFiles.map((d) => d.file)
    );

    if (!res.ok) {
      showToast(res.message);
    } else if (res.data?.queueItems) {
      appState.batch = res.data.batch || appState.batch;
      appState.queueItems.push(...res.data.queueItems);
      validFiles.forEach((d) => (d.processingState = "PROCESSED"));
      renderAll();
      showToast(`Uploaded and processed ${validFiles.length} file(s).`);
    }
  }
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

function renderAll() {
  renderBatchSummary(appState);

  renderUploadedFileList(document.getElementById("upload-file-list"), appState.documents, {
    onInspectDoc: (doc) => openDocumentDirectly(doc),
    onRetryUpload: async (doc) => {
      if (!doc.file) return;
      const res = await uploadFilesToBackend("proj_default", [doc.file]);
      showToast(res.ok ? `Re-sent ${doc.name} to backend.` : res.message);
    }
  });

  renderQueueTable(appState, {
    onOpenIssue: (issueId) => openIssueInSplit(issueId),
    onPageChange: (newPage) => {
      appState.pagination.page = newPage;
      renderAll();
    }
  });

  const navSplit = document.getElementById("nav-split");
  navSplit.disabled = !appState.activeIssueId && !appState.activeDirectDocId;
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

  await submitDecisionToBackend("proj_default", issueId, {
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

  await submitDecisionToBackend("proj_default", issueId, editPayload);

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
  if (target) {
    openIssueInSplit(target.id);
  }
}

function bindKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    if (appState.view !== "split" || !appState.activeIssueId) return;

    // Never trigger shortcuts while typing in inputs, textareas, or selects
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
   Isolated Synthetic Dev Fixture (OFF by default; strictly for testing states)
   ========================================================================== */
function bindSyntheticDevPreview() {
  document.getElementById("btn-toggle-synthetic").addEventListener("click", () => {
    if (appState.syntheticMode) {
      exitSyntheticMode();
    } else {
      loadSyntheticDevFixture();
    }
  });

  document.getElementById("btn-exit-synthetic").addEventListener("click", exitSyntheticMode);
}

function exitSyntheticMode() {
  appState.syntheticMode = false;
  appState.batch = null;
  appState.documents = [];
  appState.queueItems = [];
  appState.activeIssueId = null;
  appState.activeDirectDocId = null;
  document.getElementById("synthetic-banner").hidden = true;
  document.getElementById("btn-toggle-synthetic").textContent = "Dev Preview: Synthetic Fixture";
  switchView("queue");
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
      <text x="32" y="340" font-family="sans-serif" font-size="12" fill="#48504B">All other fields on this synthetic sheet passed validation.</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function loadSyntheticDevFixture() {
  appState.syntheticMode = true;
  document.getElementById("synthetic-banner").hidden = false;
  document.getElementById("btn-toggle-synthetic").textContent = "Exit Synthetic Preview";

  const doc1Url = createSyntheticFormSvgUrl("SYNTH-DOC-01 · Page 2", "Mss wrist pain (?trauma)");
  const doc2Url = createSyntheticFormSvgUrl("SYNTH-DOC-02 · Page 1", "Unrecognised herbal tonic");

  appState.batch = {
    batchId: "SYNTH-TEST-01",
    projectName: "Synthetic Dev Fixture",
    batchName: "Synthetic State Verification Batch (Non-Clinical)",
    totalPages: 12,
    processedPages: 11,
    updatedAt: new Date().toISOString()
  };

  appState.documents = [
    {
      id: "SYNTH-DOC-01",
      name: "synthetic_form_01.png",
      sizeBytes: 184200,
      isPdf: false,
      pageCount: 4,
      syntheticSvgUrl: doc1Url,
      uploadProgress: 100,
      processingState: "PROCESSED"
    },
    {
      id: "SYNTH-DOC-02",
      name: "synthetic_form_02.png",
      sizeBytes: 142900,
      isPdf: false,
      pageCount: 2,
      syntheticSvgUrl: doc2Url,
      uploadProgress: 100,
      processingState: "PROCESSED"
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
        { code: "13.0", label: "MSS PAIN" },
        { code: "91.0", label: "MSS PAIN OF RIGHT KNEE" }
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
      suggestedCodebookCode: null,
      suggestedCodebookLabel: null,
      codebookOptions: [
        { code: "14.0", label: "Amlodipine" },
        { code: "88.0", label: "Diclofenac" }
      ],
      validationMessage: "OCR legibility is high (92%), but codebook similarity is 34%. Please map or mark unrecognised.",
      reviewStatus: "AWAITING_REVIEW",
      severity: "HIGH",
      bbox: { xPct: 5, yPct: 29, wPct: 84, hPct: 10 },
      auditHistory: []
    },
    {
      id: "iss_3",
      documentId: "SYNTH-DOC-MISSING",
      documentName: "missing_source_test.pdf",
      pageNumber: 1,
      totalPages: 1,
      fieldName: "Age",
      reasonCode: "VALIDATION_FAILURE",
      reasonLabel: "Validation exception",
      extractedText: "148",
      ocrConfidence: 0.87,
      codebookSimilarity: null,
      validationMessage: "Value 148 exceeds expected age bound (0–115). Flagged for human assessment.",
      missingReason: "Synthetic test case demonstrating the honest Missing Original Document state.",
      reviewStatus: "AWAITING_REVIEW",
      severity: "HIGH",
      auditHistory: []
    },
    {
      id: "iss_4",
      documentId: "SYNTH-DOC-01",
      documentName: "synthetic_form_01.png",
      pageNumber: 1,
      totalPages: 4,
      fieldName: "OYSHIA_ID",
      reasonCode: "MISSING_VALUE",
      reasonLabel: "Missing or incomplete value",
      extractedText: "",
      ocrConfidence: null,
      codebookSimilarity: null,
      validationMessage: "Mandatory identifier field appears blank on page 1.",
      reviewStatus: "FLAGGED",
      severity: "MEDIUM",
      auditHistory: [{ timestamp: "10:14:02", action: "Flagged", note: "Awaiting clinic follow-up" }]
    },
    {
      id: "iss_5",
      documentId: "SYNTH-DOC-FAIL",
      documentName: "corrupted_scan_05.pdf",
      pageNumber: 3,
      totalPages: 3,
      fieldName: "Page Extraction",
      reasonCode: "PROCESSING_FAILURE",
      reasonLabel: "Processing failure",
      extractedText: "",
      ocrConfidence: null,
      codebookSimilarity: null,
      validationMessage: "OCR worker failed to decode page 3 (image contrast too low).",
      reviewStatus: "PROCESSING_FAILED",
      severity: "HIGH",
      auditHistory: []
    }
  ];

  renderAll();
  showToast("Loaded isolated synthetic test fixture.");
}
