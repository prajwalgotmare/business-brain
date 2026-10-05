const API = window.BUSINESS_BRAIN_API || "/api/v1";
const role = document.querySelector("#role");
const access = document.querySelector("#access-label");
const status = document.querySelector("#status");
const labels = {
  founder_cfo: "Founder / CFO",
  logistics_manager: "Logistics Manager",
  staff_accountant: "Staff Accountant",
  support_intern: "Support Intern",
};

class ApiRequestError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "ApiRequestError";
    Object.assign(this, details);
  }
}

function headers() {
  return {
    "Content-Type": "application/json",
    "X-Tenant-ID": "tenant_aura",
    "X-User-ID": `demo-${role.value}`,
    "X-Role": role.value,
  };
}

async function parseResponse(response, endpoint) {
  const requestId = response.headers.get("x-request-id") || "not returned";
  const raw = await response.text();
  let body = null;
  try {
    body = raw ? JSON.parse(raw) : null;
  } catch {
    body = null;
  }
  if (!response.ok) {
    const error = body?.error || {};
    throw new ApiRequestError(
      error.message || body?.detail || raw || response.statusText || "Request failed",
      {
        endpoint,
        status: response.status,
        code: error.code || "http_error",
        requestId,
        response: body || raw || null,
      },
    );
  }
  return body;
}

function appendMessage(text, kind) {
  const node = document.createElement("div");
  node.className = `message ${kind}`;
  node.textContent = text;
  document.querySelector("#messages").appendChild(node);
  node.scrollIntoView();
}

function appendError(error, context = "Request") {
  const wrapper = document.createElement("div");
  wrapper.className = "message assistant error-message";
  const summary = document.createElement("div");
  summary.textContent = `${context} failed${error.status ? ` (${error.status})` : ""}: ${error.message}`;
  wrapper.appendChild(summary);

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "error-details-toggle";
  toggle.textContent = "Show technical details";
  const details = document.createElement("pre");
  details.className = "error-details";
  details.hidden = true;
  details.textContent = JSON.stringify(
    {
      endpoint: error.endpoint || "client",
      status: error.status || "network_error",
      code: error.code || "network_error",
      request_id: error.requestId || "not available",
      response: error.response || null,
      browser_message: error.message,
    },
    null,
    2,
  );
  toggle.addEventListener("click", () => {
    details.hidden = !details.hidden;
    toggle.textContent = details.hidden ? "Show technical details" : "Hide technical details";
  });
  wrapper.append(toggle, details);
  document.querySelector("#messages").appendChild(wrapper);
  wrapper.scrollIntoView();
}

function renderResult(data) {
  const block = document.querySelector("#result-template").content.cloneNode(true);
  block.querySelector(".result-meta").textContent =
    `${data.route} · ${data.status} · ${data.model || "governed"}`;
  block.querySelector(".result-answer").textContent = data.answer || "No answer returned.";
  const citations = data.citations || [];
  block.querySelector(".citations").textContent = citations.length
    ? `Citations: ${citations
        .map(
          (item) =>
            `${item.title}, p. ${item.page_number}${item.clause_id ? `, ${item.clause_id}` : ""}`,
        )
        .join(" · ")}`
    : "";
  if (data.approval) {
    block.querySelector(".approval").textContent =
      `Approval required: ${data.approval.required_approver_roles.join(", ")} · ${data.approval.status}`;
  }
  document.querySelector("#messages").appendChild(block);
}

role.addEventListener("change", () => {
  access.textContent = labels[role.value];
});

document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector("#question").value = button.dataset.question;
  });
});

document.querySelector("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#question");
  const question = input.value.trim();
  if (!question) return;
  appendMessage(question, "user");
  input.value = "";
  status.textContent = "Working…";
  try {
    const endpoint = `${API}/agent/run`;
    const response = await fetch(endpoint, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ question, max_tokens: 700 }),
    });
    renderResult(await parseResponse(response, endpoint));
  } catch (error) {
    appendError(
      error instanceof ApiRequestError
        ? error
        : new ApiRequestError(error.message || "Network request failed"),
      "Agent request",
    );
  } finally {
    status.textContent = "Ready";
  }
});

document.querySelector("#upload-btn").addEventListener("click", async () => {
  const file = document.querySelector("#upload").files[0];
  const output = document.querySelector("#upload-result");
  if (!file) {
    output.textContent = "Choose a file first.";
    return;
  }
  const form = new FormData();
  form.append("file", file);
  form.append(
    "resource_type",
    file.name.toLowerCase().endsWith(".pdf") ? "business_document" : "tracking_events",
  );
  const endpoint = `${API}/uploads/preview`;
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "X-Tenant-ID": "tenant_aura",
        "X-User-ID": `demo-${role.value}`,
        "X-Role": role.value,
      },
      body: form,
    });
    const data = await parseResponse(response, endpoint);
    output.textContent = `Preview ready: ${data.job.upload_id}`;
  } catch (error) {
    output.textContent = "Upload preview failed. See technical details below.";
    appendError(
      error instanceof ApiRequestError
        ? error
        : new ApiRequestError(error.message || "Network request failed"),
      "Upload preview",
    );
  }
});
