/**
 * Batch Summary & Exception-Based Review Queue
 * Uses pagination (15 items per page) so large batches never freeze the DOM.
 */

export const PAGE_SIZE = 15;

export function filterQueueItems(items, { statusTab, reasonFilter, searchQuery }) {
  const q = (searchQuery || "").trim().toLowerCase();

  return items.filter((item) => {
    // 1. Status View Tab
    if (statusTab === "NEEDS_REVIEW") {
      if (item.reviewStatus !== "AWAITING_REVIEW" && item.reviewStatus !== "PROCESSING_FAILED") {
        return false;
      }
    } else if (statusTab === "VERIFIED") {
      if (item.reviewStatus !== "VERIFIED") return false;
    } else if (statusTab === "FLAGGED") {
      if (item.reviewStatus !== "FLAGGED") return false;
    } else if (statusTab === "PROCESSING_FAILED") {
      if (item.reviewStatus !== "PROCESSING_FAILED") return false;
    }

    // 2. Reason Filter
    if (reasonFilter === "ALL_UNRESOLVED") {
      if (statusTab === "ALL" && item.reviewStatus === "VERIFIED") {
        // Under ALL tab with default filter, still keep all visible unless narrowed
      }
    } else if (reasonFilter === "FLAGGED") {
      if (item.reviewStatus !== "FLAGGED") return false;
    } else if (item.reasonCode !== reasonFilter) {
      return false;
    }

    // 3. Search Query
    if (q) {
      const hay = `${item.documentName} ${item.documentId} ${item.fieldName} ${item.extractedText || ""} ${item.reasonLabel}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }

    return true;
  });
}

export function renderBatchSummary(state) {
  const { batch, documents, queueItems } = state;

  document.getElementById("batch-project-label").textContent = batch
    ? `PROJECT: ${batch.projectName.toUpperCase()} · BATCH ${batch.batchId}`
    : "PROJECT: UNASSIGNED · LOCAL WORKSTATION";

  document.getElementById("batch-title").textContent = batch
    ? batch.batchName
    : documents.length > 0
      ? `Local Session (${documents.length} uploaded file${documents.length > 1 ? "s" : ""})`
      : "No Active Batch";

  document.getElementById("batch-timestamp").textContent = batch?.updatedAt
    ? `Updated ${new Date(batch.updatedAt).toLocaleTimeString()}`
    : "";

  const totalPages = batch
    ? batch.totalPages
    : documents.reduce((acc, d) => acc + (d.pageCount || 1), 0);

  const processedPages = batch
    ? batch.processedPages
    : documents.filter((d) => d.processingState === "PROCESSED").reduce((acc, d) => acc + (d.pageCount || 1), 0);

  const awaitingCount = queueItems.filter((i) => i.reviewStatus === "AWAITING_REVIEW").length;
  const verifiedCount = queueItems.filter((i) => i.reviewStatus === "VERIFIED").length;
  const flaggedCount = queueItems.filter((i) => i.reviewStatus === "FLAGGED").length;
  const failedCount = queueItems.filter((i) => i.reviewStatus === "PROCESSING_FAILED").length;

  document.getElementById("m-total").textContent = String(totalPages);
  document.getElementById("m-processed").textContent = String(processedPages);
  document.getElementById("m-awaiting").textContent = String(awaitingCount);
  document.getElementById("m-verified").textContent = String(verifiedCount);
  document.getElementById("m-flagged").textContent = String(flaggedCount);
  document.getElementById("m-failed").textContent = String(failedCount);

  const totalIssues = queueItems.length;
  const pctReviewed = totalIssues > 0 ? Math.round((verifiedCount / totalIssues) * 100) : 0;

  document.getElementById("progress-label").textContent = `${pctReviewed}% issues verified`;
  const bar = document.getElementById("batch-progressbar");
  bar.setAttribute("aria-valuenow", String(pctReviewed));

  const denom = Math.max(totalIssues, 1);
  document.getElementById("seg-verified").style.width = `${(verifiedCount / denom) * 100}%`;
  document.getElementById("seg-review").style.width = `${((awaitingCount + flaggedCount) / denom) * 100}%`;
  document.getElementById("seg-failed").style.width = `${(failedCount / denom) * 100}%`;
  document.getElementById("seg-pending").style.width = totalIssues === 0 && totalPages > 0 ? "100%" : "0%";

  const nextBtn = document.getElementById("btn-open-next-issue");
  nextBtn.disabled = awaitingCount + flaggedCount + failedCount === 0;
}

export function renderQueueTable(state, { onOpenIssue, onPageChange }) {
  const filtered = filterQueueItems(state.queueItems, state.filters);
  const total = filtered.length;
  const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (state.pagination.page > maxPage) state.pagination.page = maxPage;

  const startIdx = (state.pagination.page - 1) * PAGE_SIZE;
  const slice = filtered.slice(startIdx, startIdx + PAGE_SIZE);

  const emptyEl = document.getElementById("queue-empty-state");
  const tableEl = document.getElementById("queue-table-container");
  const tbody = document.getElementById("queue-tbody");

  if (total === 0) {
    tableEl.hidden = true;
    emptyEl.hidden = false;

    if (state.documents.length === 0 && !state.syntheticMode) {
      emptyEl.innerHTML = `
        <h3>Ready for document upload</h3>
        <p>No encounter forms have been uploaded to this workstation yet. Upload JPG, PNG, or multi-page PDF files above to begin extraction and exception-based review.</p>
      `;
    } else if (state.documents.length > 0 && state.queueItems.length === 0) {
      emptyEl.innerHTML = `
        <h3>Documents uploaded — awaiting backend extraction</h3>
        <p>${state.documents.length} file(s) loaded in your browser session. You can click <strong>Inspect Document</strong> above to view any uploaded file, or connect the FastAPI OCR backend to populate the review queue.</p>
      `;
    } else if (state.queueItems.length > 0 && state.filters.statusTab === "NEEDS_REVIEW") {
      emptyEl.innerHTML = `
        <h3>No remaining review issues</h3>
        <p>All outstanding extraction and validation items in this view have been resolved.</p>
      `;
    } else {
      emptyEl.innerHTML = `
        <h3>No matching items</h3>
        <p>No queue items match your current status tab, reason filter, or search query.</p>
      `;
    }
    return filtered;
  }

  emptyEl.hidden = true;
  tableEl.hidden = false;
  tbody.innerHTML = "";

  for (const item of slice) {
    const tr = document.createElement("tr");

    const confText =
      typeof item.ocrConfidence === "number"
        ? `${Math.round(item.ocrConfidence * 100)}%`
        : "—";

    const statusBadge = formatStatusBadge(item.reviewStatus);
    const severityBadge = formatSeverityBadge(item.severity);

    tr.innerHTML = `
      <td>
        <div style="font-weight:600;">${escapeHtml(item.documentName)}</div>
        <div class="mono-tag">${escapeHtml(item.documentId)}</div>
      </td>
      <td class="mono-tag">p. ${item.pageNumber}</td>
      <td>
        <strong>${escapeHtml(item.fieldName)}</strong>
        <div class="mono-tag" style="max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(item.extractedText || "Empty")}</div>
      </td>
      <td>${escapeHtml(item.reasonLabel)}</td>
      <td class="mono-tag">${confText}</td>
      <td>${statusBadge}</td>
      <td>${severityBadge}</td>
      <td style="text-align:right;">
        <button type="button" class="btn btn-sm btn-primary">Open in Evidence Split →</button>
      </td>
    `;

    tr.querySelector("button").addEventListener("click", () => onOpenIssue(item.id));
    tbody.appendChild(tr);
  }

  const endIdx = Math.min(startIdx + PAGE_SIZE, total);
  document.getElementById("pagination-info").textContent = `Showing ${startIdx + 1}–${endIdx} of ${total}`;

  const prevBtn = document.getElementById("btn-prev-page");
  const nextBtn = document.getElementById("btn-next-page");
  prevBtn.disabled = state.pagination.page <= 1;
  nextBtn.disabled = state.pagination.page >= maxPage;

  prevBtn.onclick = () => onPageChange(state.pagination.page - 1);
  nextBtn.onclick = () => onPageChange(state.pagination.page + 1);

  return filtered;
}

export function formatStatusBadge(status) {
  switch (status) {
    case "VERIFIED":
      return `<span class="status-badge verified">✓ Verified</span>`;
    case "FLAGGED":
      return `<span class="status-badge amber">⚑ Flagged</span>`;
    case "PROCESSING_FAILED":
      return `<span class="status-badge failed">✕ Processing Failed</span>`;
    case "AWAITING_REVIEW":
    default:
      return `<span class="status-badge amber">◷ Awaiting Review</span>`;
  }
}

function formatSeverityBadge(sev) {
  if (sev === "HIGH" || sev === "BLOCKER") {
    return `<span class="status-badge oxide">! High</span>`;
  }
  if (sev === "MEDIUM" || sev === "WARNING") {
    return `<span class="status-badge amber">• Medium</span>`;
  }
  return `<span class="status-badge">· Low</span>`;
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
