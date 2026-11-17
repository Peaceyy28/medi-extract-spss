/**
 * Screen 01: The Project Index
 * Renders real projects from application state, expressive varied panels,
 * honest loading/error/empty states, and Create Project workflow (.SAV or blank PDF).
 */

export function renderProjectIndex(state, callbacks) {
  const grid = document.getElementById("pi-projects-grid");
  const statusBox = document.getElementById("pi-projects-status");
  if (!grid) return;

  if (state.projectsLoading) {
    statusBox.hidden = false;
    statusBox.innerHTML = `<div class="panel" style="padding:24px; text-align:center;"><span class="mono-tag">Loading projects…</span></div>`;
    grid.innerHTML = "";
    return;
  }

  if (state.projectsError) {
    statusBox.hidden = false;
    statusBox.innerHTML = `
      <div class="panel" style="padding:24px; border-color:var(--signal-oxide-border); background:var(--signal-oxide-bg);">
        <strong style="color:var(--signal-oxide);">Unable to load projects</strong>
        <p style="margin:6px 0 0; font-size:13px;">${escapeHtml(state.projectsError)}</p>
      </div>
    `;
    return;
  }

  statusBox.hidden = true;
  grid.innerHTML = "";

  if (state.projects.length === 0) {
    const empty = document.createElement("div");
    empty.className = "panel";
    empty.style.gridColumn = "span 7";
    empty.style.padding = "32px";
    empty.innerHTML = `
      <span class="mono-tag">NO PROJECTS CONFIGURED</span>
      <h3 class="proj-title">Start your first clinical data workspace</h3>
      <p style="color:var(--ink-secondary); margin:0 0 16px;">
        Create a project from an existing SPSS template (.sav) or a blank questionnaire PDF to begin receiving encounter forms.
      </p>
    `;
    grid.appendChild(empty);
  } else {
    state.projects.forEach((proj, idx) => {
      const projBatches = state.batches.filter((b) => b.projectId === proj.id);
      const batchIds = new Set(projBatches.map((b) => b.id));
      const projDocs = state.documents.filter((d) => batchIds.has(d.batchId));
      const totalPages = projDocs.reduce((sum, d) => sum + (d.pageCount || 0), 0);

      // Compute genuine last activity timestamp from batches/documents
      const timestamps = [
        ...projBatches.map((b) => b.createdAt),
        ...projDocs.map((d) => d.uploadedAt)
      ].filter(Boolean);
      const latestTs = timestamps.length
        ? new Date(Math.max(...timestamps.map((t) => new Date(t).getTime()))).toLocaleString()
        : "No activity yet";

      // Varied visual composition: first project Deep Forest, second Light Blue, others Clean White
      const variantClass = idx === 0 ? "forest" : idx === 1 ? "lightblue" : "clean";
      const isDark = variantClass === "forest";

      const panel = document.createElement("article");
      panel.className = `proj-panel ${variantClass}`;

      const datasetInfo = proj.templateName
        ? `Template: ${proj.templateName}`
        : "No template linked yet";

      const statusBadge =
        projDocs.length > 0
          ? `<span class="pi-lime-pill">${projDocs.length} doc(s) · ${totalPages} page(s)</span>`
          : `<span class="status-badge" style="${isDark ? "background:rgba(255,255,255,0.12); color:#fff; border-color:rgba(255,255,255,0.25);" : ""}">Ready for Intake</span>`;

      panel.innerHTML = `
        <div>
          <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
            <span class="mono-tag">${escapeHtml(proj.reference)} · ${escapeHtml(proj.setupMode || "Workspace")}</span>
            ${statusBadge}
          </div>
          <h3 class="proj-title">${escapeHtml(proj.name)}</h3>
          <p style="margin:0; font-size:13.5px; opacity:0.88;">
            ${escapeHtml(proj.description || "Clinical encounter data processing workspace.")}
          </p>
        </div>

        <div>
          <div class="proj-meta-strip">
            <span><strong>Batches:</strong> ${projBatches.length}</span>
            <span><strong>Dataset:</strong> ${escapeHtml(datasetInfo)}</span>
            <span><strong>Last activity:</strong> ${escapeHtml(latestTs)}</span>
          </div>

          <div style="margin-top:16px; display:flex; justify-content:space-between; align-items:center; gap:10px;">
            <button type="button" class="btn ${isDark ? "btn-lime" : "btn-electric"} btn-open-proj">
              Open Project →
            </button>
            ${proj.id === state.activeProjectId ? `<span class="mono-tag" style="${isDark ? "color:#C5E86C;" : "color:var(--accent-blue);"}">● Active Workspace</span>` : ""}
          </div>
        </div>
      `;

      panel.querySelector(".btn-open-proj").addEventListener("click", () => callbacks.onOpenProject(proj.id));
      grid.appendChild(panel);
    });
  }

  // Always include the distinctive Create New Project entry point
  const createCard = document.createElement("div");
  createCard.className = "proj-create-panel";
  createCard.innerHTML = `
    <div>
      <span class="mono-tag" style="color:var(--accent-blue);">+ NEW WORKSPACE</span>
      <h3 class="proj-title" style="font-size:24px;">Create a new project</h3>
      <p style="color:var(--ink-secondary); font-size:13.5px; margin:0;">
        Configure a new clinical form format by importing an existing SPSS template (<code>.sav</code>) or uploading a blank questionnaire PDF.
      </p>
    </div>
    <div style="display:flex; gap:8px; flex-wrap:wrap;">
      <button type="button" class="btn btn-electric" id="btn-pi-create-sav">From SPSS Template (.sav)</button>
      <button type="button" class="btn" id="btn-pi-create-pdf">From Questionnaire PDF</button>
    </div>
  `;

  createCard.querySelector("#btn-pi-create-sav").addEventListener("click", () => callbacks.onCreateProject("sav"));
  createCard.querySelector("#btn-pi-create-pdf").addEventListener("click", () => callbacks.onCreateProject("pdf"));
  grid.appendChild(createCard);
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
