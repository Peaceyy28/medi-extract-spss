/**
 * Screen 02: Paper Intake (The Receiving Desk)
 * Implements Project -> Batch -> Documents -> Pages hierarchy,
 * magic-byte validation, SHA-256 content fingerprinting, duplicate resolution,
 * batch creation, and the paginated Intake Ledger.
 */

import { formatBytes } from "./upload.js";

export const INTAKE_PAGE_SIZE = 15;

export function generateBatchReference(existingBatches) {
  const year = new Date().getFullYear();
  const nextNum = existingBatches.length + 1;
  return `BATCH-${year}-${String(nextNum).padStart(4, "0")}`;
}

export function generateDocumentReference(docCount) {
  return `DOC-${String(docCount + 1).padStart(4, "0")}`;
}

/**
 * Validate file magic bytes rather than trusting filename extensions alone.
 */
export async function validateFileMagicBytes(file) {
  try {
    const headerBuf = await file.slice(0, 8).arrayBuffer();
    const bytes = new Uint8Array(headerBuf);

    // PDF: %PDF- (0x25 0x50 0x44 0x46 0x2D)
    const isPdfHeader =
      bytes[0] === 0x25 &&
      bytes[1] === 0x50 &&
      bytes[2] === 0x44 &&
      bytes[3] === 0x46 &&
      bytes[4] === 0x2d;

    // JPEG: FF D8 FF
    const isJpegHeader = bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;

    // PNG: 89 50 4E 47 0D 0A 1A 0A
    const isPngHeader =
      bytes[0] === 0x89 &&
      bytes[1] === 0x50 &&
      bytes[2] === 0x4e &&
      bytes[3] === 0x47;

    if (isPdfHeader) return { valid: true, detectedFormat: "PDF" };
    if (isJpegHeader) return { valid: true, detectedFormat: "JPG" };
    if (isPngHeader) return { valid: true, detectedFormat: "PNG" };

    return {
      valid: false,
      error: "File signature does not match a valid PDF, JPG, or PNG document."
    };
  } catch {
    return {
      valid: false,
      error: "Unable to read file header bytes."
    };
  }
}

/**
 * Compute real SHA-256 content fingerprint in browser using Web Crypto API.
 */
export async function computeSha256Fingerprint(file) {
  if (!window.crypto?.subtle) return null;
  try {
    const buffer = await file.arrayBuffer();
    const hashBuffer = await window.crypto.subtle.digest("SHA-256", buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
  } catch {
    return null;
  }
}

export function buildPageRecords(docId, pageCount) {
  const count = pageCount && pageCount > 0 ? pageCount : 1;
  const pages = [];
  for (let p = 1; p <= count; p++) {
    pages.push({
      pageNumber: p,
      sourceDocumentId: docId,
      processingStatus: "QUEUED",
      extractionStatus: "NOT_STARTED",
      validationStatus: "NOT_EVALUATED",
      extractedFieldsCount: 0
    });
  }
  return pages;
}

export function renderIntakeOverview(state) {
  const project = state.projects.find((p) => p.id === state.activeProjectId) || null;
  const batch = state.batches.find((b) => b.id === state.activeBatchId) || null;

  // Breadcrumb
  document.getElementById("crumb-project").textContent = project ? project.name : "No Project";
  document.getElementById("crumb-batch").textContent = batch ? `${batch.name} (${batch.reference})` : "No Batch Selected";

  // Batch Info Strip
  const infoStrip = document.getElementById("intake-batch-strip");
  if (!batch) {
    infoStrip.hidden = true;
  } else {
    infoStrip.hidden = false;
    document.getElementById("bi-name").textContent = batch.name;
    document.getElementById("bi-ref").textContent = batch.reference;
    document.getElementById("bi-facility").textContent = batch.facility || "—";
    document.getElementById("bi-period").textContent = batch.reportingPeriod || "Unspecified";
    document.getElementById("bi-created").textContent = new Date(batch.createdAt).toLocaleDateString();
    document.getElementById("bi-status").innerHTML = formatBatchStatusBadge(batch.lifecycleStatus);
  }

  // Distinct Batch Measurements (Document count != Page count; Processing != Verification)
  const batchDocs = batch ? state.documents.filter((d) => d.batchId === batch.id) : [];
  const docCount = batchDocs.length;
  const totalPages = batchDocs.reduce((sum, d) => sum + (d.pageCount || 0), 0);
  const uploadedFiles = batchDocs.filter((d) => d.uploadStatus === "UPLOADED").length;
  const queuedFiles = batchDocs.filter((d) => d.processingStatus === "QUEUED").length;

  let processingPages = 0;
  let completedPages = 0;
  let reviewPages = 0;
  let failedPages = 0;

  for (const d of batchDocs) {
    for (const pg of d.pages || []) {
      if (pg.processingStatus === "PROCESSING") processingPages++;
      else if (pg.processingStatus === "COMPLETED") completedPages++;
      else if (pg.processingStatus === "FAILED") failedPages++;

      if (pg.validationStatus === "NEEDS_REVIEW" || pg.extractionStatus === "NEEDS_REVIEW") {
        reviewPages++;
      }
    }
  }

  document.getElementById("im-docs").textContent = String(docCount);
  document.getElementById("im-pages").textContent = String(totalPages);
  document.getElementById("im-uploaded").textContent = String(uploadedFiles);
  document.getElementById("im-queued").textContent = String(queuedFiles);
  document.getElementById("im-proc-pages").textContent = String(processingPages);
  document.getElementById("im-done-pages").textContent = String(completedPages);
  document.getElementById("im-review-pages").textContent = String(reviewPages);
  document.getElementById("im-failed-pages").textContent = String(failedPages);

  // Compact dropzone once documents exist in the active batch
  const dropzone = document.getElementById("intake-dropzone");
  if (batchDocs.length > 0) {
    dropzone.classList.add("compact");
  } else {
    dropzone.classList.remove("compact");
  }
}

export function renderIntakeLedger(state, callbacks) {
  const project = state.projects.find((p) => p.id === state.activeProjectId) || null;
  const batch = state.batches.find((b) => b.id === state.activeBatchId) || null;

  const emptyEl = document.getElementById("intake-empty-state");
  const tableWrap = document.getElementById("intake-table-wrap");
  const tbody = document.getElementById("intake-tbody");

  if (!project) {
    tableWrap.hidden = true;
    emptyEl.hidden = false;
    emptyEl.innerHTML = `
      <h3>No project selected</h3>
      <p>Select or create a project workspace before receiving encounter form batches.</p>
    `;
    return;
  }

  if (!batch) {
    tableWrap.hidden = true;
    emptyEl.hidden = false;
    emptyEl.innerHTML = `
      <h3>No batch selected</h3>
      <p>Create a new batch or select an existing batch in <strong>${escapeHtml(project.name)}</strong> to begin uploading scanned forms.</p>
      <button type="button" class="btn btn-primary" id="btn-empty-create-batch">+ Create New Batch</button>
    `;
    document.getElementById("btn-empty-create-batch")?.addEventListener("click", callbacks.onOpenBatchModal);
    return;
  }

  const batchDocs = state.documents.filter((d) => d.batchId === batch.id);
  if (batchDocs.length === 0) {
    tableWrap.hidden = true;
    emptyEl.hidden = false;
    emptyEl.innerHTML = `
      <h3>This batch is ready for its first document</h3>
      <p>Batch <strong>${escapeHtml(batch.name)}</strong> (${escapeHtml(batch.reference)}) currently has 0 documents. Drag and drop JPG, PNG, or multi-page PDF scans above.</p>
    `;
    return;
  }

  // Filter & Sort
  const q = (state.intakeFilters.search || "").trim().toLowerCase();
  const statusF = state.intakeFilters.status || "ALL";
  const facilityF = state.intakeFilters.facility || "ALL";

  let filtered = batchDocs.filter((d) => {
    if (statusF !== "ALL" && d.processingStatus !== statusF && d.uploadStatus !== statusF) return false;
    if (facilityF !== "ALL" && (d.facility || batch.facility) !== facilityF) return false;
    if (q) {
      const hay = `${d.name} ${d.docRef} ${d.facility || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const sortBy = state.intakeFilters.sort || "date_desc";
  filtered.sort((a, b) => {
    if (sortBy === "name_asc") return a.name.localeCompare(b.name);
    if (sortBy === "pages_desc") return (b.pageCount || 0) - (a.pageCount || 0);
    if (sortBy === "size_desc") return (b.sizeBytes || 0) - (a.sizeBytes || 0);
    return new Date(b.uploadedAt) - new Date(a.uploadedAt);
  });

  if (filtered.length === 0) {
    tableWrap.hidden = true;
    emptyEl.hidden = false;
    emptyEl.innerHTML = `
      <h3>No documents match the current filters</h3>
      <p>Try clearing your search text or switching the status filter back to All.</p>
    `;
    return;
  }

  emptyEl.hidden = true;
  tableWrap.hidden = false;

  const total = filtered.length;
  const maxPage = Math.max(1, Math.ceil(total / INTAKE_PAGE_SIZE));
  if (state.intakePagination.page > maxPage) state.intakePagination.page = maxPage;

  const start = (state.intakePagination.page - 1) * INTAKE_PAGE_SIZE;
  const slice = filtered.slice(start, start + INTAKE_PAGE_SIZE);

  tbody.innerHTML = "";
  for (const doc of slice) {
    const tr = document.createElement("tr");
    const isChecked = state.selectedDocIds.has(doc.id);

    tr.innerHTML = `
      <td><input type="checkbox" class="doc-row-check" ${isChecked ? "checked" : ""} aria-label="Select ${escapeHtml(doc.name)}" /></td>
      <td>
        <div style="font-weight:600;">${escapeHtml(doc.name)}</div>
        <div class="mono-tag">${escapeHtml(doc.docRef)} · ${escapeHtml(doc.detectedFormat || (doc.isPdf ? "PDF" : "IMG"))}</div>
      </td>
      <td>${escapeHtml(doc.facility || batch.facility || "—")}</td>
      <td class="mono-tag">${doc.pageCount != null ? doc.pageCount : "Unknown"}</td>
      <td class="mono-tag">${formatBytes(doc.sizeBytes)}</td>
      <td class="mono-tag">${new Date(doc.uploadedAt).toLocaleString()}</td>
      <td>
        ${formatDocStatusBadge(doc)}
        ${doc.duplicateOfRef ? `<div class="mono-tag" style="color:var(--signal-amber-ink); margin-top:2px;">Explicit duplicate of ${escapeHtml(doc.duplicateOfRef)}</div>` : ""}
      </td>
      <td style="text-align:right; white-space:nowrap;">
        <button type="button" class="btn btn-sm btn-detail">Details</button>
        <button type="button" class="btn btn-sm btn-inspect">View</button>
        ${doc.uploadStatus === "UPLOAD_FAILED" || doc.processingStatus === "FAILED" ? `<button type="button" class="btn btn-sm btn-retry">Retry</button>` : ""}
        <button type="button" class="btn btn-sm btn-oxide btn-del">Delete</button>
      </td>
    `;

    tr.querySelector(".doc-row-check").addEventListener("change", (e) => {
      callbacks.onToggleSelect(doc.id, e.target.checked);
    });
    tr.querySelector(".btn-detail").addEventListener("click", () => callbacks.onOpenDetail(doc));
    tr.querySelector(".btn-inspect").addEventListener("click", () => callbacks.onInspectDoc(doc));
    tr.querySelector(".btn-retry")?.addEventListener("click", () => callbacks.onRetryDoc(doc));
    tr.querySelector(".btn-del").addEventListener("click", () => callbacks.onDeleteDoc(doc));

    tbody.appendChild(tr);
  }

  const end = Math.min(start + INTAKE_PAGE_SIZE, total);
  document.getElementById("intake-pagination-info").textContent = `Showing ${start + 1}–${end} of ${total} document(s)`;
  document.getElementById("btn-intake-prev").disabled = state.intakePagination.page <= 1;
  document.getElementById("btn-intake-next").disabled = state.intakePagination.page >= maxPage;
}

export function openDocumentDetailModal(doc) {
  const modal = document.getElementById("doc-detail-modal");
  document.getElementById("dd-title").textContent = `${doc.name} (${doc.docRef})`;
  document.getElementById("dd-meta").textContent =
    `Format: ${doc.detectedFormat || "Unknown"} · Size: ${formatBytes(doc.sizeBytes)} · Pages: ${doc.pageCount || "?"} · SHA-256: ${doc.sha256 ? doc.sha256.slice(0, 16) + "…" : "Unavailable"}`;

  const pageBody = document.getElementById("dd-pages-tbody");
  pageBody.innerHTML = "";
  for (const pg of doc.pages || []) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="mono-tag">Page ${pg.pageNumber}</td>
      <td><span class="status-badge">${escapeHtml(pg.processingStatus)}</span></td>
      <td class="mono-tag">${escapeHtml(pg.extractionStatus)}</td>
      <td class="mono-tag">${escapeHtml(pg.validationStatus)}</td>
    `;
    pageBody.appendChild(tr);
  }

  const histEl = document.getElementById("dd-history");
  histEl.innerHTML = (doc.history || [])
    .map((h) => `<div><span class="mono-tag">${escapeHtml(h.timestamp)}</span> — ${escapeHtml(h.event)}</div>`)
    .join("");

  modal.hidden = false;
}

function formatBatchStatusBadge(status) {
  if (status === "PROCESSING_COMPLETE" || status === "CLOSED") {
    return `<span class="status-badge verified">✓ ${escapeHtml(status.replace("_", " "))}</span>`;
  }
  if (status === "REVIEW_REQUIRED") {
    return `<span class="status-badge amber">⚑ Review Required</span>`;
  }
  return `<span class="status-badge">● ${escapeHtml(status.replace("_", " "))}</span>`;
}

function formatDocStatusBadge(doc) {
  if (doc.uploadStatus === "UPLOAD_FAILED") {
    return `<span class="status-badge failed">✕ Upload Failed</span>`;
  }
  if (doc.uploadStatus === "VALIDATING" || doc.uploadStatus === "UPLOADING") {
    return `<span class="status-badge amber">◷ ${escapeHtml(doc.uploadStatus)}</span>`;
  }
  if (doc.processingStatus === "COMPLETED") {
    return `<span class="status-badge verified">✓ Processed</span>`;
  }
  if (doc.processingStatus === "FAILED") {
    return `<span class="status-badge failed">✕ Processing Failed</span>`;
  }
  if (doc.processingStatus === "NEEDS_ATTENTION") {
    return `<span class="status-badge amber">⚑ Needs Attention</span>`;
  }
  return `<span class="status-badge amber">◷ Uploaded · ${escapeHtml(doc.processingStatus || "QUEUED")}</span>`;
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
