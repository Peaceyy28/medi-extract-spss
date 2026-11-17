/**
 * MediExtract API Integration Boundary
 * Connects to the FastAPI backend when available and reports honest
 * unavailability when backend endpoints are not yet running.
 */

const DEFAULT_API_BASE = "http://localhost:8000/api/v1";

export const apiState = {
  baseUrl: DEFAULT_API_BASE,
  connected: false,
  lastCheckedAt: null,
  statusMessage: "Backend API not connected"
};

export async function checkBackendConnection() {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1800);
    const res = await fetch(`${apiState.baseUrl}/projects`, {
      method: "GET",
      signal: controller.signal
    });
    clearTimeout(timer);

    if (res.ok) {
      apiState.connected = true;
      apiState.statusMessage = "Backend API connected";
    } else {
      apiState.connected = false;
      apiState.statusMessage = `Backend API returned HTTP ${res.status}`;
    }
  } catch {
    apiState.connected = false;
    apiState.statusMessage = "Backend API offline (local UI boundary)";
  }
  apiState.lastCheckedAt = new Date().toISOString();
  return apiState;
}

export async function uploadFilesToBackend(projectId, files, onProgress) {
  if (!apiState.connected) {
    return {
      ok: false,
      reason: "BACKEND_UNAVAILABLE",
      message: "Upload stored in local browser session. Backend ingestion endpoint (/api/v1/projects/{id}/ingest) is not connected."
    };
  }

  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiState.baseUrl}/projects/${encodeURIComponent(projectId)}/ingest`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && typeof onProgress === "function") {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve({ ok: true, data: JSON.parse(xhr.responseText) });
        } catch {
          resolve({ ok: false, reason: "INVALID_RESPONSE", message: "Server returned invalid JSON." });
        }
      } else {
        resolve({ ok: false, reason: "HTTP_ERROR", message: `Server returned HTTP ${xhr.status}` });
      }
    };

    xhr.onerror = () => {
      resolve({ ok: false, reason: "NETWORK_ERROR", message: "Network error communicating with backend." });
    };

    xhr.send(formData);
  });
}

export async function submitDecisionToBackend(projectId, reviewId, payload) {
  if (!apiState.connected) {
    return {
      ok: false,
      reason: "BACKEND_UNAVAILABLE",
      message: "Decision recorded in local session only. Backend persistence endpoint is not connected."
    };
  }

  try {
    const res = await fetch(
      `${apiState.baseUrl}/projects/${encodeURIComponent(projectId)}/reviews/${encodeURIComponent(reviewId)}/confirm`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }
    );
    if (!res.ok) {
      return { ok: false, reason: "HTTP_ERROR", message: `Server returned HTTP ${res.status}` };
    }
    return { ok: true, data: await res.json() };
  } catch (err) {
    return { ok: false, reason: "NETWORK_ERROR", message: err.message };
  }
}

export async function inspectMergeFilesOnBackend(projectId, files) {
  if (!apiState.connected) {
    return {
      ok: false,
      reason: "BACKEND_UNAVAILABLE",
      message: "pyreadstat inspection endpoint (/api/v1/projects/{id}/merge/inspect) is not connected. Source files held locally without fabricated schema parsing."
    };
  }

  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  try {
    const res = await fetch(`${apiState.baseUrl}/projects/${encodeURIComponent(projectId)}/merge/inspect`, {
      method: "POST",
      body: formData
    });
    if (!res.ok) {
      return { ok: false, reason: "HTTP_ERROR", message: `Server returned HTTP ${res.status}` };
    }
    return { ok: true, data: await res.json() };
  } catch (err) {
    return { ok: false, reason: "NETWORK_ERROR", message: err.message };
  }
}

export async function executeMasterMergeOnBackend(projectId, payload) {
  if (!apiState.connected) {
    return {
      ok: false,
      reason: "BACKEND_UNAVAILABLE",
      message: "Master merge blocked: pyreadstat merge execution backend (/api/v1/projects/{id}/merge/execute) is offline."
    };
  }

  try {
    const res = await fetch(`${apiState.baseUrl}/projects/${encodeURIComponent(projectId)}/merge/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      return { ok: false, reason: "HTTP_ERROR", message: `Server returned HTTP ${res.status}` };
    }
    return { ok: true, data: await res.json() };
  } catch (err) {
    return { ok: false, reason: "NETWORK_ERROR", message: err.message };
  }
}

export async function runQualityValidationOnBackend(projectId, payload) {
  if (!apiState.connected) {
    return {
      ok: false,
      reason: "BACKEND_UNAVAILABLE",
      message: "Backend validation engine (/api/v1/projects/{id}/validate) is offline; running client-side rules on loaded session records only."
    };
  }

  try {
    const res = await fetch(`${apiState.baseUrl}/projects/${encodeURIComponent(projectId)}/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      return { ok: false, reason: "HTTP_ERROR", message: `Server returned HTTP ${res.status}` };
    }
    return { ok: true, data: await res.json() };
  } catch (err) {
    return { ok: false, reason: "NETWORK_ERROR", message: err.message };
  }
}

export async function exportDatasetOnBackend(projectId, payload) {
  if (!apiState.connected) {
    return {
      ok: false,
      reason: "BACKEND_UNAVAILABLE",
      message: `Binary export (.${payload.format}) requires FastAPI pyreadstat/openpyxl backend (/api/v1/projects/${projectId}/export), which is offline.`
    };
  }

  try {
    const res = await fetch(`${apiState.baseUrl}/projects/${encodeURIComponent(projectId)}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      return { ok: false, reason: "HTTP_ERROR", message: `Server returned HTTP ${res.status}` };
    }
    return { ok: true, data: await res.json() };
  } catch (err) {
    return { ok: false, reason: "NETWORK_ERROR", message: err.message };
  }
}
