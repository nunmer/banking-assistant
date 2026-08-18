/* Forte Voice admin panel — plain vanilla JS, no build step, matching app.js.
 *
 * Every fetch() here targets /admin/api/*, which sits behind the same Basic
 * Auth challenge as the /admin page itself — the browser's credential cache
 * from that initial prompt covers these calls automatically, no token
 * handling needed here.
 */
(function () {
  "use strict";

  async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(path, opts);
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`${resp.status} ${text.slice(0, 200)}`);
    }
    const ct = resp.headers.get("content-type") || "";
    return ct.includes("application/json") ? resp.json() : resp.text();
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s == null ? "" : String(s);
    return div.innerHTML;
  }

  function splitCsv(value) {
    return value.split(",").map((s) => s.trim()).filter(Boolean);
  }

  // ── Tabs ───────────────────────────────────────────────────────────────

  const LOADERS = {
    flags: loadFlags,
    scenarios: loadScenarios,
    conversations: loadSessions,
    logs: loadContainers,
  };

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`panel-${btn.dataset.tab}`).classList.add("active");
      const loader = LOADERS[btn.dataset.tab];
      if (loader) loader();
    });
  });

  // ── Flags ──────────────────────────────────────────────────────────────

  const FLAG_FIELDS = [
    ["streaming_voice_enabled", "checkbox"],
    ["tts_voice_ru", "text"],
    ["tts_voice_kk", "text"],
    ["tts_voice_default", "text"],
    ["stt_langs", "text"],
    ["rate_limit_per_min", "number"],
    ["tts_max_chars", "number"],
  ];

  async function loadFlags() {
    const form = document.getElementById("flags-form");
    form.textContent = "Loading…";
    let cfg;
    try {
      cfg = await api("GET", "/admin/api/flags");
    } catch (err) {
      form.textContent = `Failed to load: ${err.message}`;
      return;
    }
    form.innerHTML = "";
    for (const [key, type] of FLAG_FIELDS) {
      const row = document.createElement("label");
      row.className = "field-row";
      const span = document.createElement("span");
      span.textContent = key;
      row.appendChild(span);
      const input = document.createElement("input");
      input.dataset.key = key;
      if (type === "checkbox") {
        input.type = "checkbox";
        input.checked = Boolean(cfg[key]);
      } else {
        input.type = type;
        input.value = cfg[key];
      }
      row.appendChild(input);
      form.appendChild(row);
    }
    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.textContent = "Save";
    saveBtn.className = "btn-primary";
    saveBtn.addEventListener("click", saveFlags);
    form.appendChild(saveBtn);
    const status = document.createElement("div");
    status.id = "flags-status";
    form.appendChild(status);
  }

  async function saveFlags() {
    const status = document.getElementById("flags-status");
    const patch = {};
    for (const [key, type] of FLAG_FIELDS) {
      const input = document.querySelector(`#flags-form input[data-key="${key}"]`);
      if (type === "checkbox") patch[key] = input.checked;
      else if (type === "number") patch[key] = Number(input.value);
      else patch[key] = input.value;
    }
    status.textContent = "Saving…";
    try {
      await api("POST", "/admin/api/flags", patch);
      status.textContent = "Saved.";
    } catch (err) {
      status.textContent = `Failed: ${err.message}`;
    }
  }

  // ── Scenarios ──────────────────────────────────────────────────────────

  const BLANK_SCENARIO = {
    intent: "", display_name: "", description: "", required_params: [], optional_params: [],
    confirm_template: "", confirm_templates: {}, mib_endpoint: "", mib_method: "POST", active: true,
  };

  async function loadScenarios() {
    const listEl = document.getElementById("scenarios-list");
    listEl.textContent = "Loading…";
    let rows;
    try {
      rows = await api("GET", "/admin/api/scenarios");
    } catch (err) {
      listEl.textContent = `Failed to load: ${err.message}`;
      return;
    }
    listEl.innerHTML = "";
    const table = document.createElement("table");
    table.innerHTML = "<thead><tr><th>Intent</th><th>Name</th><th>Active</th><th></th></tr></thead>";
    const tbody = document.createElement("tbody");
    for (const sc of rows) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${escapeHtml(sc.intent)}</td>` +
        `<td>${escapeHtml(sc.display_name)}</td>` +
        `<td>${sc.active ? "yes" : "no"}</td>` +
        `<td><button data-intent="${escapeHtml(sc.intent)}" class="edit-scenario">Edit</button></td>`;
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    listEl.appendChild(table);
    listEl.querySelectorAll(".edit-scenario").forEach((btn) =>
      btn.addEventListener("click", () => {
        const sc = rows.find((r) => r.intent === btn.dataset.intent);
        if (sc) showScenarioForm(sc, true);
      })
    );
  }

  function showScenarioForm(sc, isEdit) {
    const panel = document.getElementById("scenario-form-panel");
    panel.classList.remove("hidden");
    panel.innerHTML =
      `<h3>${isEdit ? "Edit" : "New"} scenario</h3>` +
      `<label>Intent <input id="f-intent" ${isEdit ? "disabled" : ""} value="${escapeHtml(sc.intent)}"></label>` +
      `<label>Display name <input id="f-display" value="${escapeHtml(sc.display_name)}"></label>` +
      `<label>Description <input id="f-desc" value="${escapeHtml(sc.description || "")}"></label>` +
      `<label>Required params (comma-separated) <input id="f-required" value="${escapeHtml((sc.required_params || []).join(", "))}"></label>` +
      `<label>Optional params (comma-separated) <input id="f-optional" value="${escapeHtml((sc.optional_params || []).join(", "))}"></label>` +
      `<label>MIB endpoint <input id="f-endpoint" value="${escapeHtml(sc.mib_endpoint)}"></label>` +
      `<label>MIB method <input id="f-method" value="${escapeHtml(sc.mib_method || "POST")}"></label>` +
      `<label>Confirm template (fallback) <textarea id="f-template">${escapeHtml(sc.confirm_template)}</textarea></label>` +
      `<label>Confirm templates (JSON per language) <textarea id="f-templates">${escapeHtml(JSON.stringify(sc.confirm_templates || {}, null, 2))}</textarea></label>` +
      `<label class="checkbox-row"><input type="checkbox" id="f-active" ${sc.active ? "checked" : ""}> Active</label>` +
      `<div class="form-actions"><button id="f-save" class="btn-primary">Save</button><button id="f-cancel">Cancel</button></div>` +
      `<div id="f-status"></div>`;
    document.getElementById("f-cancel").addEventListener("click", () => panel.classList.add("hidden"));
    document.getElementById("f-save").addEventListener("click", () => saveScenario(isEdit, sc.intent));
  }

  async function saveScenario(isEdit, originalIntent) {
    const status = document.getElementById("f-status");
    let templates;
    try {
      templates = JSON.parse(document.getElementById("f-templates").value || "{}");
    } catch {
      status.textContent = "Confirm templates must be valid JSON.";
      return;
    }
    const body = {
      display_name: document.getElementById("f-display").value,
      description: document.getElementById("f-desc").value || null,
      required_params: splitCsv(document.getElementById("f-required").value),
      optional_params: splitCsv(document.getElementById("f-optional").value),
      confirm_template: document.getElementById("f-template").value,
      confirm_templates: templates,
      mib_endpoint: document.getElementById("f-endpoint").value,
      mib_method: document.getElementById("f-method").value,
      active: document.getElementById("f-active").checked,
    };
    status.textContent = "Saving…";
    try {
      if (isEdit) {
        await api("PUT", `/admin/api/scenarios/${encodeURIComponent(originalIntent)}`, body);
      } else {
        body.intent = document.getElementById("f-intent").value.trim();
        if (!body.intent) throw new Error("Intent is required");
        await api("POST", "/admin/api/scenarios", body);
      }
      status.textContent = "Saved.";
      document.getElementById("scenario-form-panel").classList.add("hidden");
      loadScenarios();
    } catch (err) {
      status.textContent = `Failed: ${err.message}`;
    }
  }

  document.getElementById("new-scenario-btn").addEventListener("click", () => {
    showScenarioForm(BLANK_SCENARIO, false);
  });

  // ── Conversations ──────────────────────────────────────────────────────

  let sessionsSearchDebounce = null;

  document.getElementById("sessions-search").addEventListener("input", (e) => {
    clearTimeout(sessionsSearchDebounce);
    const q = e.target.value;
    sessionsSearchDebounce = setTimeout(() => loadSessions(q), 300);
  });

  async function loadSessions(q) {
    const listEl = document.getElementById("sessions-list");
    listEl.textContent = "Loading…";
    let rows;
    try {
      const qs = q ? `&q=${encodeURIComponent(q)}` : "";
      rows = await api("GET", `/admin/api/conversations/sessions?limit=50${qs}`);
    } catch (err) {
      listEl.textContent = `Failed to load: ${err.message}`;
      return;
    }
    listEl.innerHTML = "";
    const table = document.createElement("table");
    table.innerHTML =
      "<thead><tr><th>Session</th><th>Username</th><th>Name</th><th>Channel</th>" +
      "<th>Last message</th><th>When</th><th>Msgs</th></tr></thead>";
    const tbody = document.createElement("tbody");
    for (const s of rows) {
      const tr = document.createElement("tr");
      tr.className = "clickable-row";
      tr.innerHTML =
        `<td>${escapeHtml(s.session_id)}</td>` +
        `<td>${s.username ? "@" + escapeHtml(s.username) : ""}</td>` +
        `<td>${escapeHtml(s.first_name || "")}</td>` +
        `<td>${escapeHtml(s.channel)}</td>` +
        `<td class="truncate">${escapeHtml(s.last_message || "")}</td>` +
        `<td>${escapeHtml(formatTimestamp(s.last_at))}</td>` +
        `<td>${s.message_count}</td>`;
      tr.addEventListener("click", () => loadTranscript(s.session_id));
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    listEl.appendChild(table);
  }

  const transcriptModal = document.getElementById("transcript-modal");

  function openTranscriptModal() {
    transcriptModal.classList.remove("hidden");
  }

  function closeTranscriptModal() {
    transcriptModal.classList.add("hidden");
  }

  document.getElementById("transcript-modal-close").addEventListener("click", closeTranscriptModal);
  // Click on the dimmed backdrop (not the content itself) also closes it —
  // standard modal convention.
  transcriptModal.addEventListener("click", (e) => {
    if (e.target === transcriptModal) closeTranscriptModal();
  });

  function formatTimestamp(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "" : d.toLocaleString();
  }

  async function loadTranscript(sessionId) {
    const panel = document.getElementById("transcript-panel");
    openTranscriptModal();
    panel.innerHTML = `<h3>Session ${escapeHtml(sessionId)}</h3><div>Loading…</div>`;
    let rows;
    try {
      rows = await api(
        "GET",
        `/admin/api/conversations/${encodeURIComponent(sessionId)}?limit=200`
      );
    } catch (err) {
      panel.innerHTML = `<h3>Session ${escapeHtml(sessionId)}</h3><div>Failed to load: ${escapeHtml(err.message)}</div>`;
      return;
    }

    panel.innerHTML = `<h3>Session ${escapeHtml(sessionId)}</h3>`;
    if (!rows.length) {
      panel.insertAdjacentHTML("beforeend", "<div>No messages.</div>");
      return;
    }
    for (const m of rows) {
      const block = document.createElement("div");
      block.className = "msg-block";
      const detailsBtn = m.turn_id
        ? `<button class="details-btn" data-turn="${escapeHtml(m.turn_id)}">Details</button>`
        : "";
      block.innerHTML =
        `<div class="msg msg-${escapeHtml(m.role)}">` +
        `<span class="msg-role">${escapeHtml(m.role)}</span>` +
        `<span class="msg-text">${escapeHtml(m.text)}</span>` +
        `<span class="msg-time">${escapeHtml(formatTimestamp(m.created_at))}</span>` +
        detailsBtn +
        `</div><div class="msg-events hidden"></div>`;
      panel.appendChild(block);
      const btn = block.querySelector(".details-btn");
      if (btn) {
        btn.addEventListener("click", () => toggleTurnEvents(btn, block.querySelector(".msg-events")));
      }
    }
  }

  async function toggleTurnEvents(btn, eventsEl) {
    if (!eventsEl.classList.contains("hidden")) {
      eventsEl.classList.add("hidden");
      return;
    }
    if (eventsEl.dataset.loaded) {
      eventsEl.classList.remove("hidden");
      return;
    }
    eventsEl.classList.remove("hidden");
    eventsEl.textContent = "Loading…";
    try {
      const events = await api(
        "GET", `/admin/api/turns/${encodeURIComponent(btn.dataset.turn)}/events`
      );
      eventsEl.innerHTML = events.length
        ? events
            .map(
              (e) =>
                `<div class="event-block"><div class="event-step">${escapeHtml(e.step)}` +
                `<span class="event-time">${escapeHtml(e.created_at || "")}</span></div>` +
                `<pre class="event-detail">${escapeHtml(JSON.stringify(e.detail, null, 2))}</pre></div>`
            )
            .join("")
        : "<div class=\"hint\">No trace recorded for this turn.</div>";
      eventsEl.dataset.loaded = "1";
    } catch (err) {
      eventsEl.textContent = `Failed to load trace: ${err.message}`;
    }
  }

  // ── Logs ───────────────────────────────────────────────────────────────

  let logsPollTimer = null;

  async function loadContainers() {
    const select = document.getElementById("log-container-select");
    select.innerHTML = "<option>Loading…</option>";
    try {
      const rows = await api("GET", "/admin/api/containers");
      select.innerHTML = rows
        .map((c) => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)} (${escapeHtml(c.status)})</option>`)
        .join("");
      if (rows.length) loadLogs();
    } catch (err) {
      select.innerHTML = `<option>Failed: ${escapeHtml(err.message)}</option>`;
    }
  }

  async function loadLogs() {
    const select = document.getElementById("log-container-select");
    const out = document.getElementById("log-output");
    const name = select.value;
    if (!name) return;
    try {
      const text = await api("GET", `/admin/api/logs/${encodeURIComponent(name)}?lines=200`);
      out.textContent = text;
      out.scrollTop = out.scrollHeight;
    } catch (err) {
      out.textContent = `Failed to load logs: ${err.message}`;
    }
  }

  document.getElementById("log-refresh-btn").addEventListener("click", loadLogs);
  document.getElementById("log-container-select").addEventListener("change", loadLogs);
  document.getElementById("log-autopoll").addEventListener("change", (e) => {
    if (logsPollTimer) {
      clearInterval(logsPollTimer);
      logsPollTimer = null;
    }
    if (e.target.checked) logsPollTimer = setInterval(loadLogs, 5000);
  });

  // ── Init ───────────────────────────────────────────────────────────────

  loadFlags();
})();
