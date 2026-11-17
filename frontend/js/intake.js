/**
 * Screen 02: The Receiving Desk (Paper Intake)
 * Implements Project -> Batch -> Documents -> Pages hierarchy,
 * magic-byte validation, SHA-256 content fingerprinting, duplicate resolution,
 * batch lifecycle tracking, lazy thumbnails, expandable details, and the Intake Ledger.
 */

import { formatBytes } from "./upload.js";

export const INTAKE_PAGE_SIZE = 15;

const BATCH_LIFECYCLE_STEPS = [
  "DRAFT",
  "RECEIVING",
  "QUEUED",
  "PROCESSING",
  "REVIEW_REQUIRED",
  "PROCESSING_COMPLETE",
  "CLOSED"
];

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

    const isPdfHeader =
      bytes[0] === 0x25 &&
      bytes[1] === 0x50 &&
      bytes[2] === 0x44 &&
      bytes[3] === 0x46 &&
      bytes[4] === 0x2d;

    const isJpegHeader = bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
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

  // Breadcrumb: Projects / [Project name] / [Current Screen]
  const screenLabel =
    state.view === "queue"
      ? "Review Queue"
      : state.view === "split"
        ? "Evidence Split"
        : state.view === "merger"
          ? "Master Merger"
          : state.view === "analytics"
            ? "Quality Observatory"
            : state.view === "studio"
              ? "Analysis Studio"
              : state.view === "export"
                ? "Export Hub"
                : "Paper Intake";
  document.getElementById("crumb-project").textContent = project ? project.name : "No Project";
  document.getElementById("crumb-batch").textContent = batch
    ? `${screenLabel} · ${batch.reference}`
    : screenLabel;

  // Deep Forest Batch Context Card
  const emptyCard = document.getElementById("rd-batch-empty");
  const activeCard = document.getElementById("rd-batch-active");

  if (!batch) {
    emptyCard.hidden = false;
    activeCard.hidden = true;
  } else {
    emptyCard.hidden = true;
    activeCard.hidden = false;
    document.getElementById("bi-ref").textContent = batch.reference;
    document.getElementById("bi-name").textContent = batch.name;
    document.getElementById("bi-facility").textContent = batch.facility || "—";
    document.getElementById("bi-period").textContent = batch.reportingPeriod || "Unspecified";
    document.getElementById("bi-created").textContent = new Date(batch.createdAt).toLocaleDateString();
    document.getElementById("bi-status").innerHTML = formatBatchStatusBadge(batch.lifecycleStatus);
  }

  // Lifecycle Stepper Bar
  const lcBar = document.getElementById("rd-lifecycle-bar");
  const currentStep = batch?.lifecycleStatus || "DRAFT";
  lcBar.innerHTML =
    `<span class="mono-tag" style="margin-right:4px;">BATCH LIFECYCLE:</span>` +
    BATCH_LIFECYCLE_STEPS.map((step) => {
      const label = step.replace("_", " ");
      const cls = step === currentStep ? "rd-lc-step current" : "rd-lc-step";
      return `<span class="${cls}">${label}</span>`;
    }).join("<span>→</span>");

  // Distinct Batch Measurements (Document counts != Page counts; Processing != Verification)
  const batchDocs = batch ? state.documents.filter((d) => d.batchId === batch.id) : [];
  const docCount = batchDocs.length;
  const totalPages = batchDocs.reduce((sum, d) => sum + (d.pageCount || 0), 0);
  const uploadedFiles = batchDocs.filter((d) => d.uploadStatus === "SERVER_UPLOADED").length;
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
  dropzone.classList.toggle("compact", batchDocs.length > 0);
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
      <p>Return to the Project Index to select or create a workspace before receiving encounter form batches.</p>
    `;
    return;
  }

  if (!batch) {
    tableWrap.hidden = true;
    emptyEl.hidden = false;
    emptyEl.innerHTML = `
      <h3>No batch selected</h3>
      <p>Create a new batch in <strong>${escapeHtml(project.name)}</strong> to begin receiving and tracking scanned encounter forms.</p>
      <button type="button" class="btn btn-electric" id="btn-empty-create-batch">+ Create New Batch</button>
    `;
    document.getElementById("btn-empty-create-batch")?.addEventListener("click", callbacks.onOpenBatchModal);
    return;
  }

  const batchDocs = state.documents.filter((d) => d.batchId === batch.id);
  if (batchDocs.length === 0) {
    tableWrap.hidden = true;
    emptyEl.hidden = false;
    emptyEl.innerHTML = `
      <h3>Ready to receive documents</h3>
      <p>Batch <strong>${escapeHtml(batch.name)}</strong> (${escapeHtml(batch.reference)}) has 0 documents. Drag and drop JPG, PNG, or PDF scans above.</p>
    `;
    return;
  }

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
      <p>Clear your search query or switch the status filter back to All Statuses.</p>
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
    if (doc.justArrived) {
      tr.className = "doc-arrived";
      doc.justArrived = false;
    }

    const isChecked = state.selectedDocIds.has(doc.id);
    const isExpanded = state.expandedDocIds.has(doc.id);
    const thumbHtml = buildLazyThumbnailHtml(doc);

    tr.innerHTML = `
      <td><input type="checkbox" class="doc-row-check" ${isChecked ? "checked" : ""} aria-label="Select ${escapeHtml(doc.name)}" /></td>
      <td>
        <div class="rd-doc-cell">
          <div class="rd-thumb-wrap" title="Click View to inspect full document">${thumbHtml}</div>
          <div>
            <div style="font-weight:600;">${escapeHtml(doc.name)}</div>
            <div class="mono-tag">${escapeHtml(doc.docRef)} · ${escapeHtml(doc.detectedFormat || (doc.isPdf ? "PDF" : "IMG"))}</div>
          </div>
        </div>
      </td>
      <td>${escapeHtml(doc.facility || batch.facility || "—")}</td>
      <td class="mono-tag">${doc.pageCount != null ? doc.pageCount : "Unknown"}</td>
      <td class="mono-tag">${formatBytes(doc.sizeBytes)}</td>
      <td class="mono-tag">${new Date(doc.uploadedAt).toLocaleString()}</td>
      <td>
        ${formatDocStatusBadge(doc)}
        ${doc.duplicateOfRef ? `<div class="mono-tag" style="color:var(--signal-amber-ink); margin-top:2px;">Explicit copy of ${escapeHtml(doc.duplicateOfRef)}</div>` : ""}
      </td>
      <td style="text-align:right; white-space:nowrap;">
        <button type="button" class="btn btn-sm btn-expand">${isExpanded ? "Hide History" : "History"}</button>
        <button type="button" class="btn btn-sm btn-inspect">View</button>
        ${doc.uploadStatus === "UPLOAD_FAILED" || doc.uploadStatus === "LOCAL_SESSION" || doc.processingStatus === "FAILED" ? `<button type="button" class="btn btn-sm btn-retry">Retry</button>` : ""}
        <button type="button" class="btn btn-sm btn-oxide btn-del">Remove</button>
      </td>
    `;

    tr.querySelector(".doc-row-check").addEventListener("change", (e) => {
      callbacks.onToggleSelect(doc.id, e.target.checked);
    });
    tr.querySelector(".btn-expand").addEventListener("click", () => callbacks.onToggleExpand(doc.id));
    tr.querySelector(".btn-inspect").addEventListener("click", () => callbacks.onInspectDoc(doc));
    tr.querySelector(".btn-retry")?.addEventListener("click", () => callbacks.onRetryDoc(doc));
    tr.querySelector(".btn-del").addEventListener("click", () => callbacks.onDeleteDoc(doc));

    tbody.appendChild(tr);

    // Inline Expandable Document Details & Processing History
    if (isExpanded) {
      const expTr = document.createElement("tr");
      expTr.className = "rd-expand-row";
      const pageSummary = (doc.pages || [])
        .slice(0, 6)
        .map((pg) => `<span class="status-badge">p.${pg.pageNumber}: ${escapeHtml(pg.processingStatus)}</span>`)
        .join(" ");
      const histHtml = (doc.history || [])
        .map((h) => `<div><span class="mono-tag">${escapeHtml(h.timestamp)}</span> — ${escapeHtml(h.event)}</div>`)
        .join("");

      expTr.innerHTML = `
        <td colspan="8">
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px;">
            <div>
              <div class="mono-tag" style="margin-bottom:6px;">PAGE RECORDS (${(doc.pages || []).length} TOTAL) · SHA-256: ${doc.sha256 ? doc.sha256.slice(0, 14) + "…" : "N/A"}</div>
              <div style="display:flex; gap:6px; flex-wrap:wrap;">${pageSummary}</div>
            </div>
            <div>
              <div class="mono-tag" style="margin-bottom:6px;">DOCUMENT PROCESSING HISTORY</div>
              <div style="font-size:12.5px;">${histHtml || "No events recorded."}</div>
            </div>
          </div>
        </td>
      `;
      tbody.appendChild(expTr);
    }
  }

  const end = Math.min(start + INTAKE_PAGE_SIZE, total);
  document.getElementById("intake-pagination-info").textContent = `Showing ${start + 1}–${end} of ${total} document(s)`;
  document.getElementById("btn-intake-prev").disabled = state.intakePagination.page <= 1;
  document.getElementById("btn-intake-next").disabled = state.intakePagination.page >= maxPage;
}

function buildLazyThumbnailHtml(doc) {
  const src = doc.objectUrl || doc.syntheticSvgUrl;
  if (!doc.isPdf && src) {
    return `<img src="${src}" alt="Thumbnail for ${escapeHtml(doc.name)}" loading="lazy" />`;
  }
  return `<span class="mono-tag" style="font-weight:600; color:var(--accent-blue);">${doc.isPdf ? "PDF" : "DOC"}</span>`;
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
    return `<span class="status-badge verified" style="background:var(--accent-lime); color:#183B35; border-color:#183B35;">✓ ${escapeHtml(status.replace("_", " "))}</span>`;
  }
  if (status === "REVIEW_REQUIRED") {
    return `<span class="status-badge amber">⚑ Review Required</span>`;
  }
  return `<span class="status-badge" style="background:rgba(255,255,255,0.14); color:#FFFFFF; border-color:rgba(255,255,255,0.28);">● ${escapeHtml(status.replace("_", " "))}</span>`;
}

function formatDocStatusBadge(doc) {
  if (doc.uploadStatus === "UPLOAD_FAILED") {
    return `<span class="status-badge failed">✕ Upload Failed</span>`;
  }
  if (doc.uploadStatus === "LOCAL_SESSION") {
    return `<span class="status-badge amber">◷ Local Session (Pending Server)</span>`;
  }
  if (doc.processingStatus === "COMPLETED") {
    return `<span class="status-badge verified">✓ Completed</span>`;
  }
  if (doc.processingStatus === "FAILED") {
    return `<span class="status-badge failed">✕ Failed</span>`;
  }
  if (doc.processingStatus === "NEEDS_ATTENTION" || doc.processingStatus === "REVIEW_REQUIRED") {
    return `<span class="status-badge amber">⚑ Review Required</span>`;
  }
  if (doc.processingStatus === "PROCESSING") {
    return `<span class="status-badge">● Processing</span>`;
  }
  return `<span class="status-badge">◷ Received · ${escapeHtml(doc.processingStatus || "QUEUED")}</span>`;
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
