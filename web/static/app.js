/* Forte Voice web client.
 *
 * Flow (same contract as the Telegram bot):
 *   mic tap → record → POST /api/stt → transcript
 *   transcript (or typed text) → POST /api/chat → {action, message, speech, lang}
 *   voice reply → POST /api/tts → MP3 → Web Audio playback
 *
 * Modality follows the user: a spoken request gets a spoken answer (no chat
 * bubbles), a typed request gets a text answer. The one exception is an
 * operation confirmation — its message + Да/Нет buttons are always shown, in
 * both modalities, so the user can see exactly what they are approving.
 *
 * Playback goes through an AudioContext buffer source (not an <audio> tag):
 * the context is unlocked by the mic-tap gesture, so playback can start after
 * the multi-second STT→chat→TTS chain without tripping autoplay policies.
 */
(function () {
  "use strict";

  const micBtn = document.getElementById("mic");
  const chatEl = document.getElementById("chat");
  const statusEl = document.getElementById("status");
  const form = document.getElementById("text-form");
  const input = document.getElementById("text-input");

  // Stable per-browser session, so multi-turn slot-filling works. Inside
  // Telegram this is replaced (below) by the verified Telegram user id, so the
  // Mini App shares one conversation session with the chat bot.
  let sessionId =
    localStorage.getItem("forte_session") ||
    (localStorage.setItem("forte_session", crypto.randomUUID()),
    localStorage.getItem("forte_session"));

  // ── Telegram Mini App integration + startup ────────────────────────────
  const tg = window.Telegram && window.Telegram.WebApp;

  async function init() {
    if (tg && tg.initData) {
      tg.ready();
      tg.expand();
      if (tg.setHeaderColor) tg.setHeaderColor("#0d0410");
      // Chat scrolling shouldn't drag-close the Mini App (Bot API 7.7+).
      if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
      try {
        const r = await fetch("/api/tg-auth", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ init_data: tg.initData }),
        });
        if (r.ok) {
          const data = await r.json();
          if (data.session_id) sessionId = data.session_id;
        }
      } catch {} // unverified → keep the anonymous browser session
    }
    // History must load AFTER auth so it belongs to the right session — for
    // Telegram users this includes operations done in the chat bot.
    await loadHistory();
  }

  async function loadHistory() {
    try {
      const r = await fetch(
        `/api/history?session_id=${encodeURIComponent(sessionId)}&limit=20`
      );
      if (!r.ok) return;
      const { operations } = await r.json();
      // Newest-first from the API; render oldest-first so the log reads down.
      for (const op of (operations || []).reverse()) opCard(op);
    } catch {} // history is progressive enhancement — never block the app
  }

  function opCard(op) {
    const el = document.createElement("div");
    el.className = `bubble op ${op.status === "success" ? "ok" : "fail"}`;
    const icon = op.status === "success" ? "✅" : "⚠️";
    const when = op.created_at
      ? new Date(op.created_at).toLocaleString(uiLang, {
          day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
        })
      : "";
    const via = op.channel === "telegram" ? " · Telegram" : "";
    el.innerHTML =
      `<div class="op-summary"></div><div class="op-meta">${icon} ${when}${via}</div>`;
    el.querySelector(".op-summary").textContent = op.summary;
    chatEl.appendChild(el);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  let uiLang = "ru-RU"; // follows the language of the last bot reply

  const STRINGS = {
    "ru-RU": {
      idle: "Нажмите на микрофон и говорите",
      listening: "Слушаю… нажмите ещё раз, чтобы закончить",
      thinking: "Думаю…",
      speaking: "Отвечаю…",
      yes: "Да",
      no: "Нет",
      micDenied: "Нет доступа к микрофону — проверьте разрешения",
      error: "Что-то пошло не так. Попробуйте ещё раз.",
    },
    "kk-KZ": {
      idle: "Микрофонды басып, сөйлеңіз",
      listening: "Тыңдап тұрмын… аяқтау үшін тағы басыңыз",
      thinking: "Ойланып жатырмын…",
      speaking: "Жауап беремін…",
      yes: "Иә",
      no: "Жоқ",
      micDenied: "Микрофонға рұқсат жоқ — рұқсаттарды тексеріңіз",
      error: "Бірдеңе дұрыс болмады. Қайталап көріңіз.",
    },
    "en-US": {
      idle: "Tap the mic and speak",
      listening: "Listening… tap again to finish",
      thinking: "Thinking…",
      speaking: "Speaking…",
      yes: "Yes",
      no: "No",
      micDenied: "Microphone access denied — check permissions",
      error: "Something went wrong. Please try again.",
    },
  };

  const t = (key) => (STRINGS[uiLang] || STRINGS["ru-RU"])[key];

  function setStatus(key, active) {
    statusEl.textContent = t(key);
    statusEl.classList.toggle("active", Boolean(active));
  }

  // ── Chat log ───────────────────────────────────────────────────────────

  function bubble(text, who) {
    const el = document.createElement("div");
    el.className = `bubble ${who}`;
    el.textContent = text;
    chatEl.appendChild(el);
    chatEl.scrollTop = chatEl.scrollHeight;
    return el;
  }

  function confirmButtons(voice, confirmBubble) {
    // The buttons inherit the modality of the turn that produced them, so a
    // voice conversation stays voice after a tap on Да/Нет.
    // Mirrors Telegram: answering removes the confirmation prompt entirely —
    // the result replaces it rather than piling up underneath.
    const row = document.createElement("div");
    row.className = "confirm-row";
    for (const [key, cls] of [["yes", "yes"], ["no", "no"]]) {
      const btn = document.createElement("button");
      btn.textContent = t(key);
      btn.className = cls;
      btn.addEventListener("click", () => {
        row.remove();
        if (confirmBubble) confirmBubble.remove();
        ensureAudioCtx(); // user gesture — keep audio unlocked for the reply
        // Confirming before the prompt finished speaking cuts it — the result
        // must never overlap the still-playing question.
        const myTurn = newTurn();
        converse(t(key), { voice, myTurn });
      });
      row.appendChild(btn);
    }
    chatEl.appendChild(row);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  // ── Audio level → sphere ───────────────────────────────────────────────

  let audioCtx = null;
  let levelRaf = null;

  function ensureAudioCtx() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  }

  function trackLevel(analyser) {
    const buf = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) {
        const v = (buf[i] - 128) / 128;
        sum += v * v;
      }
      Sphere.setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4));
      levelRaf = requestAnimationFrame(tick);
    };
    tick();
  }

  function stopLevel() {
    if (levelRaf) cancelAnimationFrame(levelRaf);
    levelRaf = null;
    Sphere.setLevel(0);
  }

  // ── Interruption ───────────────────────────────────────────────────────
  // One reply may be audible at a time. Every user action starts a new turn:
  // it cuts any current playback, and a stale in-flight reply (confirmed
  // before the previous audio finished) can no longer start speaking.
  let turn = 0;
  let currentSource = null;

  function stopSpeaking() {
    if (currentSource) {
      try { currentSource.stop(); } catch {}
      currentSource = null;
    }
    stopLevel();
  }

  function newTurn() {
    turn += 1;
    stopSpeaking();
    return turn;
  }

  // ── Recording ──────────────────────────────────────────────────────────

  let recorder = null;
  let recStream = null;
  let micSource = null;

  const MIME_CANDIDATES = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];

  async function startRecording() {
    // Tapping the mic while the bot talks is barge-in: cut the audio first.
    const myTurn = newTurn();
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      bubble(t("micDenied"), "bot error");
      return;
    }
    recStream = stream;

    const ctx = ensureAudioCtx();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    micSource = ctx.createMediaStreamSource(stream);
    micSource.connect(analyser);
    trackLevel(analyser);

    const mime = MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m)) || "";
    const chunks = [];
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = () => {
      recStream.getTracks().forEach((tr) => tr.stop());
      if (micSource) micSource.disconnect();
      stopLevel();
      const blob = new Blob(chunks, { type: mime || "audio/webm" });
      if (blob.size > 800) handleRecording(blob, myTurn);
      else { setStatus("idle"); Sphere.setMode("idle"); }
    };
    recorder.start();

    micBtn.classList.add("recording");
    Sphere.setMode("listening");
    setStatus("listening", true);
  }

  function stopRecording() {
    micBtn.classList.remove("recording");
    if (recorder && recorder.state !== "inactive") recorder.stop();
    recorder = null;
  }

  micBtn.addEventListener("click", () => {
    if (recorder) stopRecording();
    else startRecording();
  });

  // ── Pipeline ───────────────────────────────────────────────────────────

  async function handleRecording(blob, myTurn) {
    Sphere.setMode("thinking");
    setStatus("thinking", true);
    micBtn.disabled = true;
    try {
      // One round trip: STT → chat → TTS run server-side (like the Telegram
      // bot), instead of the browser paying internet latency between stages.
      const fd = new FormData();
      fd.append("session_id", sessionId);
      const ext = blob.type.includes("mp4") ? "m4a" : "webm";
      fd.append("file", blob, `voice.${ext}`);
      const resp = await fetch("/api/converse", { method: "POST", body: fd });
      if (!resp.ok) throw new Error(`converse ${resp.status}`);
      const data = await resp.json();
      // Re-enable the mic before playback so the reply can be barged into.
      micBtn.disabled = false;
      if (!data.transcript) {
        setStatus("idle");
        Sphere.setMode("idle");
        return;
      }
      await applyReply(data, { voice: true, myTurn });
    } catch (err) {
      console.error(err);
      bubble(t("error"), "bot error");
      setStatus("idle");
      Sphere.setMode("idle");
    } finally {
      micBtn.disabled = false;
    }
  }

  async function sendText(text) {
    const myTurn = newTurn(); // sending text also cuts any current speech
    bubble(text, "user");
    converse(text, { voice: false, myTurn });
  }

  async function converse(text, { voice, myTurn = turn }) {
    Sphere.setMode("thinking");
    setStatus("thinking", true);
    try {
      let data;
      if (voice) {
        // Voice-mode turn (e.g. a confirm-button tap): combined endpoint so
        // the reply audio arrives in the same round trip.
        const fd = new FormData();
        fd.append("session_id", sessionId);
        fd.append("text", text);
        const resp = await fetch("/api/converse", { method: "POST", body: fd });
        if (!resp.ok) throw new Error(`converse ${resp.status}`);
        data = await resp.json();
      } else {
        const resp = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, text }),
        });
        if (!resp.ok) throw new Error(`chat ${resp.status}`);
        data = await resp.json();
      }
      await applyReply(data, { voice, myTurn });
    } catch (err) {
      console.error(err);
      bubble(t("error"), "bot error");
      setStatus("idle");
      Sphere.setMode("idle");
    }
  }

  async function applyReply(data, { voice, myTurn = turn }) {
    try {
      if (data.lang && STRINGS[data.lang]) uiLang = data.lang;

      const confirming = data.action === "confirm";
      if (data.operation) {
        // A completed operation stays in the log as a persistent card — in
        // BOTH modalities. This is the durable record, synced with Telegram.
        opCard({ ...data.operation, created_at: new Date().toISOString() });
      } else if (!voice || confirming) {
        // Text modality shows every reply; voice modality shows only the
        // confirmation (so the user sees exactly what they approve).
        const el = bubble(data.message, "bot");
        if (confirming) confirmButtons(voice, el);
      }

      if (voice && data.audio) await playBase64(data.audio, myTurn);
      // TTS failed and nothing is on screen yet → fall back to text.
      else if (voice && data.message && !confirming && !data.operation)
        bubble(data.message, "bot");
    } finally {
      // Only the current turn may reset the UI — an interrupted reply must
      // not stomp the state of the action that interrupted it.
      if (myTurn === turn) {
        setStatus("idle");
        Sphere.setMode("idle");
      }
    }
  }

  async function playBase64(b64, myTurn = turn) {
    // A newer user action started while this reply was in flight → stay silent.
    if (myTurn !== turn) return;
    try {
      const raw = atob(b64);
      const bytes = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

      const ctx = ensureAudioCtx();
      const buffer = await ctx.decodeAudioData(bytes.buffer);
      if (myTurn !== turn) return; // interrupted during decode
      stopSpeaking(); // safety net: never two sources at once

      const src = ctx.createBufferSource();
      src.buffer = buffer;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      analyser.connect(ctx.destination);
      currentSource = src;

      Sphere.setMode("speaking");
      setStatus("speaking", true);
      trackLevel(analyser);

      await new Promise((resolve) => {
        src.onended = resolve; // fires on natural end AND on .stop()
        src.start();
      });
      if (currentSource === src) currentSource = null;
      stopLevel();
    } catch (err) {
      console.error("tts playback:", err);
      stopLevel();
    }
  }

  // Tapping the sphere while the bot talks stops the speech.
  document.getElementById("sphere").addEventListener("click", () => {
    if (currentSource) {
      stopSpeaking();
      setStatus("idle");
      Sphere.setMode("idle");
    }
  });

  // ── Text input ─────────────────────────────────────────────────────────

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    sendText(text);
  });

  setStatus("idle");
  init();
})();
