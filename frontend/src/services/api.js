const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");
const CHAT_REQUEST_TIMEOUT_MS = 125_000;

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function errorMessage(payload, response) {
  const detail =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? payload.detail
      : null;

  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item.msg === "string") return item.msg;
        return "";
      })
      .filter(Boolean);
    if (messages.length) return messages.join("; ");
  }

  return `Request failed (${response.status}${response.statusText ? ` ${response.statusText}` : ""}).`;
}

async function request(path, { method = "GET", body, signal, timeoutMs } = {}) {
  let response;
  let text;
  let timedOut = false;
  let timeoutId;
  let timeoutController;
  let forwardAbort;
  let requestSignal = signal;
  if (timeoutMs !== undefined) {
    timeoutController = new AbortController();
    forwardAbort = () => timeoutController.abort(signal?.reason);
    if (signal?.aborted) {
      forwardAbort();
    } else {
      signal?.addEventListener("abort", forwardAbort, { once: true });
    }
    timeoutId = setTimeout(() => {
      timedOut = true;
      timeoutController.abort();
    }, timeoutMs);
    requestSignal = timeoutController.signal;
  }

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: requestSignal,
    });
    text = await response.text();
  } catch (error) {
    if (timedOut) {
      throw new ApiError("The procurement request timed out. Please try again.", 408);
    }
    if (error && error.name === "AbortError") throw error;
    throw new ApiError("Unable to reach the procurement API. Check that the backend is running.");
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
    if (forwardAbort) signal?.removeEventListener("abort", forwardAbort);
  }

  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      if (response.ok) {
        throw new ApiError("The API returned a response that was not valid JSON.", response.status);
      }
    }
  }

  if (!response.ok) {
    throw new ApiError(errorMessage(payload, response), response.status);
  }
  return payload;
}

function requireObject(value, endpoint) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ApiError(`${endpoint} returned an invalid response.`);
  }
  return value;
}

function requireString(value, name) {
  if (typeof value !== "string" || !value.trim()) {
    throw new TypeError(`${name} must be a non-empty string.`);
  }
  return value.trim();
}

function validateChatResponse(payload) {
  const result = requireObject(payload, "Chat endpoint");
  if (typeof result.thread_id !== "string" || !result.thread_id.trim()) {
    throw new ApiError("Chat endpoint returned an invalid thread ID.");
  }
  if (!["completed", "waiting_for_approval"].includes(result.status)) {
    throw new ApiError("Chat endpoint returned an invalid workflow status.");
  }
  if (result.response !== null && typeof result.response !== "string") {
    throw new ApiError("Chat endpoint returned an invalid assistant response.");
  }
  if (!Array.isArray(result.citations)) {
    throw new ApiError("Chat endpoint returned invalid policy citations.");
  }
  if (
    result.purchase_order !== null &&
    (typeof result.purchase_order !== "object" || Array.isArray(result.purchase_order))
  ) {
    throw new ApiError("Chat endpoint returned an invalid purchase order.");
  }
  return result;
}

export async function checkHealth({ signal } = {}) {
  const result = requireObject(await request("/health", { signal }), "Health endpoint");
  if (result.status !== "ok") {
    throw new ApiError("Health endpoint did not report a healthy backend.");
  }
  return result;
}

export async function sendChatMessage({ message, threadId, signal } = {}) {
  const normalizedMessage = requireString(message, "message");
  if (normalizedMessage.length > 10_000) {
    throw new TypeError("message must be no more than 10000 characters.");
  }

  const body = { message: normalizedMessage };
  if (threadId !== undefined && threadId !== null) {
    body.thread_id = requireString(threadId, "threadId");
    if (body.thread_id.length > 128) {
      throw new TypeError("threadId must be no more than 128 characters.");
    }
  }

  const payload = await request("/chat", {
    method: "POST",
    body,
    signal,
    timeoutMs: CHAT_REQUEST_TIMEOUT_MS,
  });
  return validateChatResponse(payload);
}

export async function getPendingApprovals({ limit = 100, signal } = {}) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 500) {
    throw new TypeError("limit must be an integer between 1 and 500.");
  }

  const result = await request(`/approvals?limit=${limit}`, { signal });
  if (!Array.isArray(result)) {
    throw new ApiError("Approvals endpoint returned an invalid response.");
  }
  return result.map((item) => {
    const approval = requireObject(item, "Approvals endpoint");
    if (typeof approval.thread_id !== "string" || !approval.thread_id.trim()) {
      throw new ApiError("Approvals endpoint returned an item without a thread ID.");
    }
    return approval;
  });
}

export async function resolveApproval(
  threadId,
  decision,
  { comment, approverId, approverName, signal } = {},
) {
  const id = requireString(threadId, "threadId");
  if (!["approve", "reject"].includes(decision)) {
    throw new TypeError("decision must be 'approve' or 'reject'.");
  }

  const body = { decision };
  const optionalText = [
    ["comment", comment, 2000],
    ["approver_id", approverId, 128],
    ["approver_name", approverName, 200],
  ];
  for (const [field, value, maxLength] of optionalText) {
    if (value === undefined || value === null) continue;
    if (typeof value !== "string") {
      throw new TypeError(`${field} must be a string.`);
    }
    const normalized = value.trim();
    if (normalized.length > maxLength) {
      throw new TypeError(`${field} must be no more than ${maxLength} characters.`);
    }
    if (normalized) body[field] = normalized;
  }

  const payload = requireObject(
    await request(`/approvals/${encodeURIComponent(id)}`, {
      method: "POST",
      body,
      signal,
    }),
    "Approval endpoint",
  );
  if (payload.thread_id !== id || payload.decision !== decision) {
    throw new ApiError("Approval endpoint returned a result for a different decision.");
  }
  if (!payload.state || typeof payload.state !== "object" || Array.isArray(payload.state)) {
    throw new ApiError("Approval endpoint returned an invalid workflow state.");
  }
  return payload;
}

export async function getWorkflowDefinition({ signal } = {}) {
  const result = requireObject(
    await request("/graph/definition", { signal }),
    "Workflow definition endpoint",
  );
  if (typeof result.mermaid !== "string") {
    throw new ApiError("Workflow definition endpoint returned an invalid diagram.");
  }
  return result;
}

export async function getWorkflowState(threadId, { signal } = {}) {
  const id = requireString(threadId, "threadId");
  const result = requireObject(
    await request(`/graph/${encodeURIComponent(id)}`, { signal }),
    "Workflow state endpoint",
  );
  if (
    typeof result.thread_id !== "string" ||
    !result.values ||
    typeof result.values !== "object" ||
    Array.isArray(result.values) ||
    !Array.isArray(result.next) ||
    !Array.isArray(result.tasks) ||
    !result.metadata ||
    typeof result.metadata !== "object" ||
    Array.isArray(result.metadata)
  ) {
    throw new ApiError("Workflow state endpoint returned an invalid snapshot.");
  }
  return result;
}