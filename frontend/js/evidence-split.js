/**
 * Evidence Split Workstation Controller
 * Left: Original Document Evidence (Zoom, Pan, Fit, Full Page, Page Nav, Region Highlight)
 * Right: Machine Interpretation (OCR Confidence != Codebook Similarity, Decision & Audit Trail)
 */

import { formatStatusBadge } from "./queue.js";

export const viewerState = {
  zoom: 1,
  panX: 0,
  panY: 0,
  currentPage: 1,
  totalPages: 1,
  isPanning: false,
  startX: 0,
  startY: 0,
  activeItem: null,
  activeDoc: null,
  isDirty: false
};

export function confirmDiscardUnsavedChanges() {
  if (!viewerState.isDirty) return true;
  const ok = confirm("You have unsaved corrections in the Edit drawer. Discard unsaved changes and continue?");
  if (ok) {
    viewerState.isDirty = false;
    const banner = document.getElementById("er-unsaved-banner");
    if (banner) banner.hidden = true;
  }
  return ok;
}

export function initViewerControls() {
  const stage = document.getElementById("viewer-stage");
  const wrap = document.getElementById("viewer-canvas-wrap");

  document.getElementById("btn-zoom-in").addEventListener("click", () => setZoom(viewerState.zoom + 0.15));
  document.getElementById("btn-zoom-out").addEventListener("click", () => setZoom(viewerState.zoom - 0.15));
  document.getElementById("btn-fit-page").addEventListener("click", fitToPage);
  document.getElementById("btn-full-page").addEventListener("click", openFullPageModal);
  document.getElementById("btn-close-fullpage").addEventListener("click", closeFullPageModal);

  document.getElementById("btn-page-prev").addEventListener("click", () => {
    if (viewerState.currentPage > 1) {
      viewerState.currentPage -= 1;
      renderDocumentPage();
    }
  });

  document.getElementById("btn-page-next").addEventListener("click", () => {
    if (viewerState.currentPage < viewerState.totalPages) {
      viewerState.currentPage += 1;
      renderDocumentPage();
    }
  });

  // Mouse pan inside dark instrument viewport
  stage.addEventListener("mousedown", (e) => {
    if (wrap.hidden) return;
    viewerState.isPanning = true;
    viewerState.startX = e.clientX - viewerState.panX;
    viewerState.startY = e.clientY - viewerState.panY;
    stage.classList.add("panning");
  });

  window.addEventListener("mousemove", (e) => {
    if (!viewerState.isPanning) return;
    viewerState.panX = e.clientX - viewerState.startX;
    viewerState.panY = e.clientY - viewerState.startY;
    applyTransform();
  });

  window.addEventListener("mouseup", () => {
    viewerState.isPanning = false;
    stage.classList.remove("panning");
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !document.getElementById("fullpage-modal").hidden) {
      closeFullPageModal();
    }
  });
}

export function setZoom(newZoom) {
  viewerState.zoom = Math.max(0.3, Math.min(3.0, newZoom));
  document.getElementById("zoom-readout").textContent = `${Math.round(viewerState.zoom * 100)}%`;
  applyTransform();
}

export function fitToPage() {
  viewerState.zoom = 1;
  viewerState.panX = 0;
  viewerState.panY = 0;
  document.getElementById("zoom-readout").textContent = "100%";
  applyTransform();
}

function applyTransform() {
  const wrap = document.getElementById("viewer-canvas-wrap");
  wrap.style.transform = `translate(${viewerState.panX}px, ${viewerState.panY}px) scale(${viewerState.zoom})`;
}

export async function renderEvidenceSplit(item, doc, context, callbacks) {
  viewerState.activeItem = item;
  viewerState.activeDoc = doc;
  viewerState.currentPage = item ? item.pageNumber || 1 : 1;
  viewerState.totalPages = doc?.pageCount || item?.totalPages || 1;
  fitToPage();

  // Top progress & reference bar
  document.getElementById("split-progress-counter").textContent =
    context.totalInView > 0
      ? `Issue ${context.positionIndex + 1} of ${context.totalInView}`
      : "Direct Document Inspection";

  document.getElementById("split-doc-ref").textContent = item
    ? `${item.documentName} · Page ${item.pageNumber}`
    : doc
      ? `${doc.name} · ${doc.pageCount || "?"} page(s)`
      : "";

  document.getElementById("btn-prev-issue").disabled = context.positionIndex <= 0;
  document.getElementById("btn-next-issue").disabled =
    context.positionIndex < 0 || context.positionIndex >= context.totalInView - 1;

  // Render Left Document Viewer
  await renderDocumentPage();

  // Render Right Machine Interpretation
  renderInterpretationPanel(item, doc, callbacks);
}

async function renderDocumentPage() {
  const doc = viewerState.activeDoc;
  const item = viewerState.activeItem;

  const docNameEl = document.getElementById("viewer-doc-name");
  const pageLabelEl = document.getElementById("viewer-page-label");
  const wrap = document.getElementById("viewer-canvas-wrap");
  const imgEl = document.getElementById("viewer-img");
  const pdfCanvas = document.getElementById("viewer-pdf-canvas");
  const missingBox = document.getElementById("missing-source-box");
  const regionBox = document.getElementById("region-highlight");

  docNameEl.textContent = doc?.name || item?.documentName || "Unavailable Document";
  pageLabelEl.textContent = `Page ${viewerState.currentPage} of ${viewerState.totalPages}`;

  document.getElementById("btn-page-prev").disabled = viewerState.currentPage <= 1;
  document.getElementById("btn-page-next").disabled = viewerState.currentPage >= viewerState.totalPages;

  // Honest missing-source check
  if (!doc || (!doc.objectUrl && !doc.pdfDoc && !doc.syntheticSvgUrl)) {
    wrap.hidden = true;
    missingBox.hidden = false;
    document.getElementById("missing-source-reason").textContent =
      item?.missingReason ||
      "The original uploaded file is not available in this session. MediExtract never substitutes an invented preview.";
    return;
  }

  missingBox.hidden = true;
  wrap.hidden = false;

  // Render PDF page via PDF.js or fallback
  if (doc.isPdf && doc.pdfDoc) {
    imgEl.hidden = true;
    pdfCanvas.hidden = false;
    const page = await doc.pdfDoc.getPage(viewerState.currentPage);
    const viewport = page.getViewport({ scale: 1.35 });
    pdfCanvas.width = viewport.width;
    pdfCanvas.height = viewport.height;
    const ctx = pdfCanvas.getContext("2d");
    await page.render({ canvasContext: ctx, viewport }).promise;
  } else if (doc.objectUrl || doc.syntheticSvgUrl) {
    pdfCanvas.hidden = true;
    imgEl.hidden = false;
    imgEl.src = doc.objectUrl || doc.syntheticSvgUrl;
    imgEl.style.maxWidth = "540px";
  }

  // Highlight region if coordinates exist on this exact page (never invent a bbox)
  if (item?.bbox && viewerState.currentPage === item.pageNumber) {
    regionBox.hidden = false;
    regionBox.style.left = `${item.bbox.xPct}%`;
    regionBox.style.top = `${item.bbox.yPct}%`;
    regionBox.style.width = `${item.bbox.wPct}%`;
    regionBox.style.height = `${item.bbox.hPct}%`;
    regionBox.classList.remove("er-pulse");
    void regionBox.offsetWidth;
    regionBox.classList.add("er-pulse");
    document.getElementById("region-tag").textContent = item.fieldName;
  } else {
    regionBox.hidden = true;
    regionBox.classList.remove("er-pulse");
  }
}

function setConfidenceMeter(elId, ratio) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (typeof ratio !== "number") {
    el.style.width = "0%";
    el.className = "er-meter-fill";
    return;
  }
  const pct = Math.max(0, Math.min(100, Math.round(ratio * 100)));
  el.style.width = `${pct}%`;
  const tier = ratio >= 0.85 ? "high" : ratio >= 0.6 ? "medium" : "low";
  el.className = `er-meter-fill ${tier}`;
}

function renderInterpretationPanel(item, doc, callbacks) {
  const editDrawer = document.getElementById("edit-drawer");
  editDrawer.hidden = true;
  viewerState.isDirty = false;
  const unsavedBanner = document.getElementById("er-unsaved-banner");
  if (unsavedBanner) unsavedBanner.hidden = true;

  // Animated focus transition on panel body
  const bodyPanel = document.getElementById("interp-body-panel");
  if (bodyPanel) {
    bodyPanel.classList.remove("er-focus-anim");
    void bodyPanel.offsetWidth;
    bodyPanel.classList.add("er-focus-anim");
  }

  const coordsStrip = document.getElementById("er-coords-strip");
  const coordsText = document.getElementById("er-coords-text");
  const coordsPage = document.getElementById("er-coords-page");

  // Direct local document inspection mode (before backend OCR runs)
  if (!item) {
    if (coordsStrip) coordsStrip.classList.add("missing");
    if (coordsText) coordsText.textContent = "Manual inspection mode — no extracted field coordinates";
    if (coordsPage) coordsPage.textContent = `Page ${viewerState.currentPage} of ${viewerState.totalPages}`;
    setConfidenceMeter("interp-ocr-meter", null);
    setConfidenceMeter("interp-cb-meter", null);
    const techOrig = document.getElementById("tech-orig-val");
    if (techOrig) techOrig.textContent = "—";
    const techCoords = document.getElementById("tech-coords-val");
    if (techCoords) techCoords.textContent = "None (manual view)";
    const techRule = document.getElementById("tech-rule-val");
    if (techRule) techRule.textContent = "Awaiting OCR pipeline";
    document.getElementById("interp-source-ref").textContent = `SOURCE: ${doc?.name || "—"}`;
    document.getElementById("interp-field-name").textContent = "Awaiting Backend Extraction";
    document.getElementById("interp-status-badge").outerHTML =
      `<span class="status-badge amber" id="interp-status-badge">◷ Pending OCR</span>`;
    document.getElementById("interp-extracted-text").textContent =
      "No fields extracted yet. Connect the FastAPI OCR backend to extract fields and confidence scores.";
    document.getElementById("interp-orig-tag").textContent = "";
    document.getElementById("interp-ocr-conf").textContent = "—";
    document.getElementById("interp-cb-sim").textContent = "—";
    document.getElementById("interp-codebook-val").textContent = "Awaiting extraction";
    document.getElementById("interp-validation-box").hidden = true;
    document.getElementById("interp-audit-log").innerHTML =
      "<strong>Audit History:</strong> Document uploaded locally; backend extraction not yet executed.";

    document.getElementById("btn-confirm-val").disabled = true;
    document.getElementById("btn-edit-val").disabled = true;
    document.getElementById("btn-flag-val").disabled = true;
    return;
  }

  document.getElementById("btn-confirm-val").disabled = false;
  document.getElementById("btn-edit-val").disabled = false;
  document.getElementById("btn-flag-val").disabled = false;

  document.getElementById("interp-source-ref").textContent =
    `SOURCE: ${item.documentName} · PAGE ${item.pageNumber}`;
  document.getElementById("interp-field-name").textContent = item.fieldName;

  const badgeContainer = document.getElementById("interp-status-badge");
  badgeContainer.outerHTML = formatStatusBadge(item.reviewStatus).replace(
    'class="status-badge',
    'id="interp-status-badge" class="status-badge'
  );

  // Preserve original extracted text & show reviewer correction if edited
  const currentVal = item.correctedText !== undefined ? item.correctedText : item.extractedText;
  document.getElementById("interp-extracted-text").textContent =
    currentVal || "(Missing / Blank)";
  document.getElementById("interp-orig-tag").textContent =
    item.correctedText !== undefined
      ? `Original OCR: "${item.extractedText || "Blank"}"`
      : "Unedited OCR";

  // Strictly separate OCR Confidence from Codebook Similarity
  document.getElementById("interp-ocr-conf").textContent =
    typeof item.ocrConfidence === "number"
      ? `${Math.round(item.ocrConfidence * 100)}%`
      : "Unavailable";
  setConfidenceMeter("interp-ocr-meter", item.ocrConfidence);

  document.getElementById("interp-cb-sim").textContent =
    typeof item.codebookSimilarity === "number"
      ? `${Math.round(item.codebookSimilarity * 100)}%`
      : "N/A";
  setConfidenceMeter("interp-cb-meter", item.codebookSimilarity);

  if (coordsStrip && coordsText && coordsPage) {
    if (item.bbox) {
      coordsStrip.classList.remove("missing");
      coordsText.textContent = `Source BBox [${item.bbox.xPct}%, ${item.bbox.yPct}%, ${item.bbox.wPct}%, ${item.bbox.hPct}%] ⟶ Linked to ${item.fieldName}`;
    } else {
      coordsStrip.classList.add("missing");
      coordsText.textContent = "No visual coordinates available for this field";
    }
    coordsPage.textContent = `Page ${item.pageNumber} of ${item.totalPages || viewerState.totalPages}`;
  }

  const techOrig = document.getElementById("tech-orig-val");
  if (techOrig) techOrig.textContent = item.extractedText || "(Blank)";
  const techCoords = document.getElementById("tech-coords-val");
  if (techCoords) {
    techCoords.textContent = item.bbox
      ? `Page ${item.pageNumber} · [${item.bbox.xPct}%, ${item.bbox.yPct}%, ${item.bbox.wPct}%, ${item.bbox.hPct}%]`
      : `Page ${item.pageNumber} · Unavailable`;
  }
  const techRule = document.getElementById("tech-rule-val");
  if (techRule) techRule.textContent = item.reasonLabel || item.reasonCode || "Standard review";
  const techReviewer = document.getElementById("tech-reviewer-val");
  if (techReviewer) techReviewer.textContent = item.lastReviewer || "Records Clerk (Local Session)";

  document.getElementById("interp-codebook-val").textContent =
    item.selectedCodebookLabel ||
    item.suggestedCodebookLabel ||
    "No matching codebook entry";

  // Validation Notice (Flagged for human assessment, never declaring medical error)
  const valBox = document.getElementById("interp-validation-box");
  if (item.validationMessage) {
    valBox.hidden = false;
    valBox.className =
      item.reasonCode === "VALIDATION_FAILURE" || item.reasonCode === "PROCESSING_FAILURE"
        ? "validation-notice exception"
        : "validation-notice";
    document.getElementById("interp-validation-title").textContent = `${item.reasonLabel}: `;
    document.getElementById("interp-validation-msg").textContent = item.validationMessage;
  } else {
    valBox.hidden = true;
  }

  // Audit Log
  const auditEl = document.getElementById("interp-audit-log");
  if (item.auditHistory && item.auditHistory.length > 0) {
    auditEl.innerHTML =
      "<strong>Audit History:</strong><br/>" +
      item.auditHistory
        .map(
          (entry) =>
            `<span class="mono-tag">${escapeHtml(entry.timestamp)}</span> — ${escapeHtml(entry.action)} ${entry.note ? `(${escapeHtml(entry.note)})` : ""}`
        )
        .join("<br/>");
  } else {
    auditEl.innerHTML = "<strong>Audit History:</strong> No reviewer actions recorded yet.";
  }

  // Wire Action Buttons
  document.getElementById("btn-confirm-val").onclick = () => callbacks.onDecision(item.id, "VERIFIED");
  document.getElementById("btn-flag-val").onclick = () => callbacks.onDecision(item.id, "FLAGGED");
  document.getElementById("btn-edit-val").onclick = () => openEditDrawer(item, callbacks);
}

export function openEditDrawer(item, callbacks) {
  if (!item) return;
  const drawer = document.getElementById("edit-drawer");
  drawer.hidden = false;

  const textInput = document.getElementById("edit-text-input");
  const cbGroup = document.getElementById("edit-codebook-group");
  const cbSelect = document.getElementById("edit-codebook-select");
  const chkUnreadable = document.getElementById("chk-unreadable");
  const chkUnrecognised = document.getElementById("chk-unrecognised");
  const noteInput = document.getElementById("edit-note-input");

  textInput.value = item.correctedText !== undefined ? item.correctedText : item.extractedText || "";
  chkUnreadable.checked = Boolean(item.markedUnreadable);
  chkUnrecognised.checked = Boolean(item.markedUnrecognised);
  noteInput.value = "";
  viewerState.isDirty = false;
  const unsavedBanner = document.getElementById("er-unsaved-banner");
  if (unsavedBanner) unsavedBanner.hidden = true;

  const markDirty = () => {
    viewerState.isDirty = true;
    if (unsavedBanner) unsavedBanner.hidden = false;
  };
  textInput.oninput = markDirty;
  cbSelect.onchange = markDirty;
  chkUnreadable.onchange = markDirty;
  chkUnrecognised.onchange = markDirty;
  noteInput.oninput = markDirty;

  if (item.codebookOptions && item.codebookOptions.length > 0) {
    cbGroup.hidden = false;
    cbSelect.innerHTML = `<option value="">-- Select codebook entry --</option>`;
    for (const opt of item.codebookOptions) {
      const o = document.createElement("option");
      o.value = opt.code;
      o.textContent = `${opt.code} — ${opt.label}`;
      if ((item.selectedCodebookCode || item.suggestedCodebookCode) === opt.code) {
        o.selected = true;
      }
      cbSelect.appendChild(o);
    }
  } else {
    cbGroup.hidden = true;
  }

  textInput.focus();

  document.getElementById("btn-cancel-edit").onclick = () => {
    viewerState.isDirty = false;
    if (unsavedBanner) unsavedBanner.hidden = true;
    drawer.hidden = true;
  };

  document.getElementById("btn-save-edit").onclick = () => {
    viewerState.isDirty = false;
    if (unsavedBanner) unsavedBanner.hidden = true;
    const selectedOpt = cbSelect.selectedOptions[0];
    callbacks.onEditSave(item.id, {
      correctedText: textInput.value.trim(),
      selectedCodebookCode: cbGroup.hidden ? null : cbSelect.value || null,
      selectedCodebookLabel:
        !cbGroup.hidden && cbSelect.value && selectedOpt ? selectedOpt.textContent : null,
      markedUnreadable: chkUnreadable.checked,
      markedUnrecognised: chkUnrecognised.checked,
      note: noteInput.value.trim()
    });
    drawer.hidden = true;
  };
}

function openFullPageModal() {
  const modal = document.getElementById("fullpage-modal");
  const body = document.getElementById("fullpage-body");
  const imgEl = document.getElementById("viewer-img");
  const pdfCanvas = document.getElementById("viewer-pdf-canvas");

  body.innerHTML = "";
  if (!imgEl.hidden && imgEl.src) {
    const clone = document.createElement("img");
    clone.src = imgEl.src;
    clone.style.maxWidth = "95vw";
    clone.style.background = "#FFF";
    body.appendChild(clone);
  } else if (!pdfCanvas.hidden) {
    const clone = document.createElement("img");
    clone.src = pdfCanvas.toDataURL();
    clone.style.maxWidth = "95vw";
    body.appendChild(clone);
  } else {
    body.innerHTML = `<p style="color:#F3F0E8;">No document page loaded.</p>`;
  }

  document.getElementById("fullpage-title").textContent =
    `${document.getElementById("viewer-doc-name").textContent} — Page ${viewerState.currentPage}`;
  modal.hidden = false;
}

function closeFullPageModal() {
  document.getElementById("fullpage-modal").hidden = true;
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
