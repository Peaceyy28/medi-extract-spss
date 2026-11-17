/**
 * Genuine Browser Document Upload & Intake Handler
 * Supports JPG, PNG, and multi-page PDF. Never fabricates OCR results.
 */

const ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".pdf"];
const ALLOWED_MIMES = ["image/jpeg", "image/png", "application/pdf"];

export function validateUploadFile(file) {
  const lower = (file.name || "").toLowerCase();
  const extOk = ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext));
  const mimeOk = ALLOWED_MIMES.includes(file.type) || extOk;

  if (!mimeOk) {
    return {
      valid: false,
      error: `Unsupported format "${file.type || "unknown"}". Supported formats: JPG, PNG, multi-page PDF.`
    };
  }
  if (file.size === 0) {
    return {
      valid: false,
      error: "File is empty (0 bytes)."
    };
  }
  return { valid: true };
}

export async function inspectLocalFile(file) {
  const objectUrl = URL.createObjectURL(file);
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  let pageCount = 1;
  let pdfDoc = null;

  if (isPdf && window.pdfjsLib) {
    try {
      if (!window.pdfjsLib.GlobalWorkerOptions.workerSrc) {
        window.pdfjsLib.GlobalWorkerOptions.workerSrc =
          "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
      }
      const buffer = await file.arrayBuffer();
      pdfDoc = await window.pdfjsLib.getDocument({ data: buffer }).promise;
      pageCount = pdfDoc.numPages || 1;
    } catch {
      // Fallback: PDF uploaded, page count unknown if PDF.js worker is offline
      pageCount = null;
    }
  }

  return {
    id: `doc_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    file,
    name: file.name,
    sizeBytes: file.size,
    mimeType: isPdf ? "application/pdf" : file.type || "image/jpeg",
    isPdf,
    pageCount,
    pdfDoc,
    objectUrl,
    uploadProgress: 100,
    processingState: "PENDING_BACKEND",
    errorMessage: null,
    uploadedAt: new Date().toISOString()
  };
}

export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function renderUploadedFileList(containerEl, documents, { onInspectDoc, onRetryUpload }) {
  if (!documents.length) {
    containerEl.hidden = true;
    containerEl.innerHTML = "";
    return;
  }

  containerEl.hidden = false;
  containerEl.innerHTML = "";

  for (const doc of documents) {
    const row = document.createElement("div");
    row.className = "upload-file-row";

    const nameCol = document.createElement("div");
    nameCol.innerHTML = `<strong>${escapeHtml(doc.name)}</strong><div class="mono-tag">${formatBytes(doc.sizeBytes)} · ${doc.isPdf ? "PDF" : "Image"}</div>`;

    const pagesCol = document.createElement("div");
    pagesCol.className = "mono-tag";
    pagesCol.textContent = doc.pageCount ? `${doc.pageCount} page${doc.pageCount > 1 ? "s" : ""}` : "Pages: pending";

    const progressCol = document.createElement("div");
    progressCol.className = "mono-tag";
    progressCol.textContent = doc.errorMessage ? "Upload error" : `Loaded (${doc.uploadProgress}%)`;

    const statusCol = document.createElement("div");
    if (doc.errorMessage) {
      statusCol.innerHTML = `<span class="status-badge failed">✕ ${escapeHtml(doc.errorMessage)}</span>`;
    } else if (doc.processingState === "PROCESSED") {
      statusCol.innerHTML = `<span class="status-badge verified">✓ Extracted</span>`;
    } else {
      statusCol.innerHTML = `<span class="status-badge amber">◷ Awaiting Backend OCR</span>`;
    }

    const actionCol = document.createElement("div");
    actionCol.style.display = "flex";
    actionCol.style.gap = "6px";
    actionCol.style.justifyContent = "flex-end";

    if (doc.objectUrl && !doc.errorMessage) {
      const viewBtn = document.createElement("button");
      viewBtn.type = "button";
      viewBtn.className = "btn btn-sm";
      viewBtn.textContent = "Inspect Document";
      viewBtn.addEventListener("click", () => onInspectDoc(doc));
      actionCol.appendChild(viewBtn);
    }

    if (doc.errorMessage || doc.processingState === "PENDING_BACKEND") {
      const retryBtn = document.createElement("button");
      retryBtn.type = "button";
      retryBtn.className = "btn btn-sm";
      retryBtn.textContent = doc.errorMessage ? "Retry" : "Re-send to API";
      retryBtn.addEventListener("click", () => onRetryUpload(doc));
      actionCol.appendChild(retryBtn);
    }

    row.append(nameCol, pagesCol, progressCol, statusCol, actionCol);
    containerEl.appendChild(row);
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
