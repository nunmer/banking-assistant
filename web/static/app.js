/* Forte Voice web client.
 *
 * Flow (same contract as the Telegram bot):
 *   mic tap → record → POST /api/stt → transcript
 *   transcript (or typed text) → POST /api/chat → {action, message, speech, lang}
 *   reply → POST /api/tts → MP3 → play, sphere reacts to playback level
 *
 * The sphere reacts to the user's mic level while recording and to the bot's
 * voice while a reply is playing.
 */
(function () {
  "use strict";

  const micBtn = document.getElementById("mic");
  const chatEl = document.getElementById("chat");
  const statusEl = document.getElementById("status");
  const form = document.getElementById("text-form");
  const input = document.getElementById("text-input");

  // Stable per-browser session, so multi-turn slot-filling works.
  const sessionId =
    localStorage.getItem("forte_session") ||
    (localStorage.setItem("forte_session", crypto.randomUUID()),
    localStorage.getItem("forte_session"));

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

  function confirmButtons() {
    const row = document.createElement("div");
    row.className = "confirm-row";
    for (const [key, cls] of [["yes", "yes"], ["no", "no"]]) {
      const btn = document.createElement("button");
      btn.textContent = t(key);
      btn.className = cls;
      btn.addEventListener("click", () => {
        row.remove();
        sendText(t(key));
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
      if (blob.size > 800) handleRecording(blob);
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

  async function handleRecording(blob) {
    Sphere.setMode("thinking");
    setStatus("thinking", true);
    micBtn.disabled = true;
    try {
      const fd = new FormData();
      const ext = blob.type.includes("mp4") ? "m4a" : "webm";
      fd.append("file", blob, `voice.${ext}`);
      const resp = await fetch("/api/stt", { method: "POST", body: fd });
      if (!resp.ok) throw new Error(`stt ${resp.status}`);
      const { text } = await resp.json();
      if (!text || !text.trim()) {
        setStatus("idle");
        Sphere.setMode("idle");
        return;
      }
      bubble(text, "user");
      await converse(text, { speak: true });
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
    bubble(text, "user");
    converse(text, { speak: false });
  }

  async function converse(text, { speak }) {
    Sphere.setMode("thinking");
    setStatus("thinking", true);
    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, text }),
      });
      if (!resp.ok) throw new Error(`chat ${resp.status}`);
      const data = await resp.json();
      if (data.lang && STRINGS[data.lang]) uiLang = data.lang;

      bubble(data.message, "bot");
      if (data.action === "confirm") confirmButtons();

      if (speak) await speakReply(data.speech || data.message, data.lang);
    } catch (err) {
      console.error(err);
      bubble(t("error"), "bot error");
    } finally {
      setStatus("idle");
      Sphere.setMode("idle");
    }
  }

  async function speakReply(text, lang) {
    try {
      const resp = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang }),
      });
      if (!resp.ok) return; // silent fallback to text-only
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);

      const ctx = ensureAudioCtx();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      const src = ctx.createMediaElementSource(audio);
      src.connect(analyser);
      analyser.connect(ctx.destination);

      Sphere.setMode("speaking");
      setStatus("speaking", true);
      trackLevel(analyser);

      await new Promise((resolve) => {
        audio.onended = resolve;
        audio.onerror = resolve;
        audio.play().catch(resolve); // autoplay blocked → fall back silently
      });
      stopLevel();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("tts playback:", err);
      stopLevel();
    }
  }

  // ── Text input ─────────────────────────────────────────────────────────

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    sendText(text);
  });

  setStatus("idle");
})();
