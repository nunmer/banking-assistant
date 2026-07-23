/* Forte Voice web client.
 *
 * Voice flow: one mic tap opens a live WebSocket (/ws/converse) and starts a
 * hands-free conversation — PCM audio streams continuously and Yandex's own
 * end-of-utterance detector (server-side) decides when each turn is done, so
 * there's no manual stop-tap between turns. Partial captions appear while the
 * user is talking; a {message, audio, action, operation} reply arrives per
 * completed turn and plays back. The mic stays live even during playback (see
 * setBotSpeaking) so saying "stop"/"wait" cuts the reply off — there's no
 * real echo cancellation, so anything else heard mid-reply is discarded
 * rather than acted on. An utterance that wasn't really addressed to the bot
 * (ambient chatter) gets silently ignored too, instead of an "I didn't
 * understand" interruption — ping-ponging with a person nearby shouldn't
 * trip it. Tapping the mic/sphere leaves hands-free mode entirely (or, mid-
 * reply, just cuts the audio and keeps listening — the manual equivalent of
 * saying "stop").
 * Where WebSocket audio capture isn't available, it falls back to the older
 * one-shot record-a-blob-then-upload flow (POST /api/converse).
 * Typed text always goes through POST /api/chat → {action, message, speech, lang}.
 *
 * Modality follows the user: a spoken request gets a spoken answer (no chat
 * bubbles) — instead, the reply materialises near the sphere as a few words
 * at a time, each block dissolving as the next arrives, timed to the audio's
 * own duration (see "Vaporizing reply caption"). A typed request gets a text
 * answer. The one exception is an operation confirmation — its message +
 * Да/Нет buttons are always shown, in both modalities, so the user can see
 * exactly what they are approving.
 *
 * Playback goes through an AudioContext buffer source (not an <audio> tag):
 * the context is unlocked by the mic-tap gesture, so playback can start after
 * the multi-second recognition→chat→TTS chain without tripping autoplay policies.
 */
(function () {
  "use strict";

  const micBtn = document.getElementById("mic");
  const chatEl = document.getElementById("chat");
  const statusEl = document.getElementById("status");
  const form = document.getElementById("text-form");
  const input = document.getElementById("text-input");
  const docGenEl = document.getElementById("doc-gen");

  // Stable per-browser session, so multi-turn slot-filling works. Inside
  // Telegram this is replaced (below) by the verified Telegram user id, so the
  // Mini App shares one conversation session with the chat bot.
  let sessionId =
    localStorage.getItem("forte_session") ||
    (localStorage.setItem("forte_session", crypto.randomUUID()),
    localStorage.getItem("forte_session"));

  // Telegram first name, for a personalised greeting — only ever set inside
  // the Mini App (verified via /api/tg-auth); null for an anonymous browser
  // session, and never guessed client-side.
  let userName = null;

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
          if (data.user_name) userName = data.user_name;
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
    if (op.document === "statement_pdf" && op.status === "success" && op.tx_id) {
      // "📄 PDF" rather than a translated verb — a universally understood
      // badge that needs no per-language copy (icon + file-type abbreviation).
      const link = document.createElement("a");
      link.className = "op-download";
      const pdfUrl = `${location.origin}/api/statement/pdf/${encodeURIComponent(op.tx_id)}`;
      link.href = pdfUrl;
      link.setAttribute("download", "statement.pdf");
      link.textContent = "📄 PDF ⬇";
      if (tg && tg.initData) {
        // Inside the Telegram Mini App's WebView, navigating straight to a
        // PDF response takes over the whole view with no back gesture —
        // the only way out is force-closing the Mini App entirely. Hand the
        // URL to the phone's real browser instead, which handles PDFs
        // normally (its own back/close), leaving the Mini App untouched.
        link.addEventListener("click", (e) => {
          e.preventDefault();
          tg.openLink(pdfUrl);
        });
      }
      el.appendChild(link);
    }
    chatEl.appendChild(el);
    chatEl.scrollTop = chatEl.scrollHeight;
    return el;
  }

  // ── Statement PDF "generating" flourish ─────────────────────────────────
  // By the time this plays, the PDF already sits server-side (built during
  // the chat+TTS round trip) — this is pure theater, giving "materializing a
  // document" its due moment before the result lands as an ordinary history
  // card, instead of an instant silent pop-in. Sequence: a ghost card over
  // the sphere "prints" a few lines, shows a checkmark, then FLIPs (classic
  // measure-invert-play transform trick) into the exact slot the real history
  // card lands in, so it reads as one continuous object arriving there.
  async function animateDocumentGeneration(operation) {
    if (!docGenEl) {
      opCard({ ...operation, created_at: new Date().toISOString() });
      return;
    }
    docGenEl.innerHTML =
      `<div class="doc-card">
         <div class="doc-icon">
           <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.6">
             <path d="M6 2h9l5 5v15H6z"/><path d="M15 2v5h5"/>
           </svg>
           <div class="doc-check">✓</div>
         </div>
         <div class="doc-lines">
           <span class="doc-line" style="width:78%"></span>
           <span class="doc-line" style="width:52%"></span>
           <span class="doc-line" style="width:64%"></span>
           <span class="doc-line" style="width:40%"></span>
         </div>
       </div>`;
    const card = docGenEl.querySelector(".doc-card");
    const lines = docGenEl.querySelectorAll(".doc-line");
    docGenEl.classList.add("active");

    for (const line of lines) {
      line.classList.add("filled");
      await new Promise((r) => setTimeout(r, 240));
    }
    await new Promise((r) => setTimeout(r, 120));
    card.classList.add("done");
    await new Promise((r) => setTimeout(r, 650));

    // FLIP: place the real card, position it exactly over the ghost via an
    // inverse transform, swap visibility on the same frame (no double-flash),
    // then animate the transform away to its natural resting spot.
    const startRect = card.getBoundingClientRect();
    const el = opCard({ ...operation, created_at: new Date().toISOString() });
    const endRect = el.getBoundingClientRect();

    const dx = startRect.left - endRect.left;
    const dy = startRect.top - endRect.top;
    const sx = startRect.width / endRect.width;
    const sy = startRect.height / endRect.height;

    el.style.transformOrigin = "top left";
    el.style.transition = "none";
    el.style.transform = `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`;
    el.style.opacity = "0";
    docGenEl.classList.remove("active");
    el.style.opacity = "1";

    requestAnimationFrame(() => {
      el.style.transition = "transform 0.55s cubic-bezier(0.22, 0.7, 0.2, 1)";
      el.style.transform = "none";
    });

    await new Promise((r) => setTimeout(r, 600));
    el.style.transition = "";
    el.style.transformOrigin = "";
    docGenEl.innerHTML = "";
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
      micStart: "Говорить",
      micStop: "Остановить прослушивание",
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
      micStart: "Сөйлеу",
      micStop: "Тыңдауды тоқтату",
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
      micStart: "Speak",
      micStop: "Stop listening",
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

  // Tracks the currently-shown confirm row/bubble (if any), so a confirmation
  // answered by VOICE — not a button tap — still gets cleaned up. Button taps
  // remove their own row directly; clearConfirmUI() is the path for every
  // other way a pending confirmation gets resolved (spoken yes/no, cancelled,
  // or superseded by a new request).
  let activeConfirmUI = null;

  function clearConfirmUI() {
    if (!activeConfirmUI) return;
    activeConfirmUI.row.remove();
    if (activeConfirmUI.bubble) activeConfirmUI.bubble.remove();
    activeConfirmUI = null;
  }

  function confirmButtons(voice, confirmBubble) {
    // The buttons inherit the modality of the turn that produced them, so a
    // voice conversation stays voice after a tap on Да/Нет.
    // Mirrors Telegram: answering removes the confirmation prompt entirely —
    // the result replaces it rather than piling up underneath.
    clearConfirmUI(); // never stack two pending confirmations
    const row = document.createElement("div");
    row.className = "confirm-row";
    for (const [key, cls] of [["yes", "yes"], ["no", "no"]]) {
      const btn = document.createElement("button");
      btn.textContent = t(key);
      btn.className = cls;
      btn.addEventListener("click", () => {
        clearConfirmUI();
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
    activeConfirmUI = { row, bubble: confirmBubble };
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
    clearCaption();
    setBotSpeaking(false); // interrupted mid-reply — the mic can act on speech again
  }

  function newTurn() {
    turn += 1;
    stopSpeaking();
    return turn;
  }

  // ── Vaporizing reply caption ─────────────────────────────────────────────
  // A voice reply materialises out of the sphere as a few words at a time —
  // each block dissolves into vapor as the next one arrives — instead of one
  // long sentence the user has to read while also trying to listen. Timed to
  // the reply's own audio duration so the last block clears around when the
  // voice stops talking.

  const captionEl = document.getElementById("caption");
  let captionTimer = null;

  function splitIntoBlocks(text) {
    // Prefer natural pauses (sentence/clause punctuation); anything still
    // longer than a few words gets folded into shorter chunks so nothing
    // sits on screen too long to feel "live".
    const MAX_WORDS = 5;
    const clauses = text.match(/[^.!?,;:—]+[.!?,;:—]?/g) || [text];
    const blocks = [];
    for (const clause of clauses) {
      const words = clause.trim().split(/\s+/).filter(Boolean);
      for (let i = 0; i < words.length; i += MAX_WORDS) {
        blocks.push(words.slice(i, i + MAX_WORDS).join(" "));
      }
    }
    return blocks.length ? blocks : [text.trim()];
  }

  function vaporizeCurrentBlock() {
    if (!captionEl) return;
    const current = captionEl.querySelector(".caption-block:not(.leaving)");
    if (!current) return;
    current.classList.add("leaving");
    current.addEventListener("animationend", () => current.remove(), { once: true });
  }

  function showCaptionBlock(text) {
    if (!captionEl) return;
    vaporizeCurrentBlock();
    const el = document.createElement("span");
    el.className = "caption-block";
    el.textContent = text;
    el.dataset.text = text; // mirrored by the ::before/::after vapor trails
    captionEl.appendChild(el);
  }

  function clearCaption() {
    if (captionTimer) {
      clearTimeout(captionTimer);
      captionTimer = null;
    }
    if (captionEl) captionEl.innerHTML = "";
  }

  function playCaption(text, totalMs) {
    const blocks = splitIntoBlocks(text);
    const perBlock = Math.max(900, totalMs / blocks.length);
    let i = 0;
    const step = () => {
      if (i >= blocks.length) {
        captionTimer = setTimeout(vaporizeCurrentBlock, 350);
        return;
      }
      showCaptionBlock(blocks[i]);
      i += 1;
      captionTimer = setTimeout(step, perBlock);
    };
    step();
  }

  // ── Recording ──────────────────────────────────────────────────────────
  // Two capture paths share one `recording` flag and one mic-tap gesture:
  //   - streaming (default): PCM over a live WebSocket that stays open for
  //     the whole hands-free conversation — Yandex's own end-of-utterance
  //     detector (server-side) decides when each turn is done, so no manual
  //     stop-tap is needed between turns, only to leave hands-free mode
  //     entirely (see startStreamingCapture).
  //   - blob (fallback): the older record-then-upload flow, used only if a
  //     WebSocket/ScriptProcessor can't be set up — one tap-to-stop per turn.

  let recording = false;
  let recStream = null;
  let micSource = null;
  let ws = null;
  let pcmProcessor = null;
  let recorder = null; // MediaRecorder — fallback path only
  // Set right before stopRecording() sends "end" upstream — distinguishes a
  // deliberate stop from the streaming session ending on its own (e.g.
  // Yandex's own inactivity timeout after a long pause), which should
  // reconnect transparently instead of leaving hands-free mode dead.
  let stopRequested = false;
  let autoRestartCount = 0;
  let autoRestartWindowStart = 0;
  const AUTO_RESTART_LIMIT = 3;
  const AUTO_RESTART_WINDOW_MS = 10000;
  // True while a reply is playing. The mic is NOT muted during this —
  // it keeps listening so a spoken "stop"/"wait" can interrupt — but the
  // server needs to know this state to tell an interrupt word apart from
  // the bot just hearing its own voice through the speakers.
  let botSpeaking = false;

  function setBotSpeaking(value) {
    botSpeaking = value;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: "bot_speaking", value }));
    }
  }

  const TARGET_RATE = 16000; // PCM rate the streaming STT endpoint expects

  function resampleTo16k(float32, inputRate) {
    if (inputRate === TARGET_RATE) return float32;
    const ratio = inputRate / TARGET_RATE;
    const outLength = Math.floor(float32.length / ratio);
    const out = new Float32Array(outLength);
    for (let i = 0; i < outLength; i++) {
      const srcPos = i * ratio;
      const idx0 = Math.floor(srcPos);
      const idx1 = Math.min(idx0 + 1, float32.length - 1);
      const frac = srcPos - idx0;
      out[i] = float32[idx0] * (1 - frac) + float32[idx1] * frac;
    }
    return out;
  }

  function floatTo16BitPCM(input) {
    const output = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1, Math.min(1, input[i]));
      output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return output;
  }

  function startStreamingCapture(ctx, stream, myTurn) {
    if (!window.WebSocket) return false;
    let processor;
    try {
      processor = ctx.createScriptProcessor(4096, 1, 1);
    } catch {
      return false; // e.g. an AudioContext that refuses ScriptProcessorNode
    }

    const proto = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${proto}://${location.host}/ws/converse`);
    socket.binaryType = "arraybuffer";
    let liveBubble = null;

    const finish = () => {
      if (liveBubble) { liveBubble.remove(); liveBubble = null; }
      micBtn.disabled = false;
    };

    socket.onopen = () => {
      socket.send(JSON.stringify({ session_id: sessionId, user_name: userName }));
      micSource.connect(processor);
      // ScriptProcessorNode only fires onaudioprocess while connected into the
      // graph toward the destination — route through a silent gain node so
      // the raw mic input is never actually heard.
      const mute = ctx.createGain();
      mute.gain.value = 0;
      processor.connect(mute);
      mute.connect(ctx.destination);
      processor.onaudioprocess = (e) => {
        // Kept live even while the reply plays — the server needs to keep
        // hearing in case the user says "stop"/"wait" (see setBotSpeaking).
        if (socket.readyState !== WebSocket.OPEN) return;
        const input = e.inputBuffer.getChannelData(0);
        const pcm = floatTo16BitPCM(resampleTo16k(input, ctx.sampleRate));
        socket.send(pcm.buffer);
      };
    };

    socket.onmessage = (evt) => {
      let data;
      try { data = JSON.parse(evt.data); } catch { return; }
      if (data.type === "partial") {
        // While the bot is talking, anything heard is either the start of an
        // interrupt word or the bot's own echo — not a caption-worthy user
        // utterance, so it's not shown as one.
        if (botSpeaking) return;
        if (!liveBubble) liveBubble = bubble(data.text, "bot live");
        else liveBubble.textContent = data.text;
        chatEl.scrollTop = chatEl.scrollHeight;
      } else if (data.type === "reply") {
        finish();
        applyReply(data, { voice: true, myTurn });
      } else if (data.type === "interrupt") {
        // The server heard "stop"/"wait" while the bot was talking.
        stopSpeaking();
        setStatus("listening", true);
        Sphere.setMode("listening");
      } else if (data.type === "error") {
        finish();
        bubble(t("error"), "bot error");
        setStatus("idle");
        Sphere.setMode("idle");
      } else if (data.type === "done") {
        // The session is over — this is the only signal for it when the
        // trailing utterance was silence or ambiguous ("was that even
        // addressed to me?") and so never got a "reply" to reset the UI.
        if (myTurn !== turn) return; // a newer session already replaced this one
        finish();
        if (stopRequested) {
          setStatus("idle");
          Sphere.setMode("idle");
        } else {
          // The user never tapped stop — Yandex's own stream ended on its
          // own (its inactivity timeout after a long pause is the usual
          // cause), not a real failure. Reconnect instead of going idle, so
          // hands-free mode doesn't quietly die mid-conversation.
          resumeHandsFreeAfterUnsolicitedEnd(myTurn);
        }
      }
    };

    socket.onclose = () => {
      // Safety net for any other way the connection could end (network
      // drop, a server-side exception before even the error message goes
      // out) — without this, a tap-to-stop that hits one of those leaves
      // "Thinking…" on screen with nothing left to ever clear it.
      if (myTurn !== turn) return;
      finish();
      if (stopRequested) {
        setStatus("idle");
        Sphere.setMode("idle");
      } else {
        resumeHandsFreeAfterUnsolicitedEnd(myTurn);
      }
    };

    ws = socket;
    pcmProcessor = processor;
    return true;
  }

  const MIME_CANDIDATES = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];

  function startBlobCapture(stream, myTurn) {
    const mime = MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m)) || "";
    const chunks = [];
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: mime || "audio/webm" });
      if (blob.size > 800) handleRecording(blob, myTurn);
      else { micBtn.disabled = false; setStatus("idle"); Sphere.setMode("idle"); }
    };
    recorder.start();
  }

  async function startRecording() {
    // Tapping the mic while the bot talks is barge-in: cut the audio first.
    const myTurn = newTurn();
    let stream;
    try {
      // echoCancellation matters more now than it used to: the mic stays
      // live through the bot's own playback (see setBotSpeaking) so a
      // spoken "stop"/"wait" can interrupt it.
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch {
      bubble(t("micDenied"), "bot error");
      return;
    }
    recStream = stream;
    recording = true;
    stopRequested = false;

    const ctx = ensureAudioCtx();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    micSource = ctx.createMediaStreamSource(stream);
    micSource.connect(analyser);
    trackLevel(analyser);

    micBtn.classList.add("recording");
    micBtn.setAttribute("aria-label", t("micStop"));
    Sphere.setMode("listening");
    setStatus("listening", true);

    if (!startStreamingCapture(ctx, stream, myTurn)) startBlobCapture(stream, myTurn);
  }

  // Releases the mic/audio-graph resources for the CURRENT session without
  // touching UI state — shared by a deliberate stop and by an unsolicited
  // reconnect, which need different UI outcomes but the same cleanup.
  function releaseAudioResources() {
    if (micSource) { micSource.disconnect(); micSource = null; }
    if (recStream) { recStream.getTracks().forEach((tr) => tr.stop()); recStream = null; }
    stopLevel();
    if (pcmProcessor) {
      pcmProcessor.onaudioprocess = null;
      pcmProcessor.disconnect();
      pcmProcessor = null;
    }
    ws = null;
  }

  function stopRecording() {
    micBtn.classList.remove("recording");
    micBtn.setAttribute("aria-label", t("micStart"));
    recording = false;
    stopRequested = true;
    Sphere.setMode("thinking");
    setStatus("thinking", true);
    micBtn.disabled = true;

    const socket = ws;
    releaseAudioResources();

    if (socket) {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ action: "end" }));
      } else {
        // Never actually connected — nothing will send a reply.
        socket.close();
        micBtn.disabled = false;
        setStatus("idle");
        Sphere.setMode("idle");
      }
      return;
    }

    if (recorder && recorder.state !== "inactive") recorder.stop();
    recorder = null;
  }

  function giveUpHandsFree(message) {
    recording = false;
    micBtn.classList.remove("recording");
    micBtn.setAttribute("aria-label", t("micStart"));
    micBtn.disabled = false;
    releaseAudioResources();
    bubble(message, "bot error");
    setStatus("idle");
    Sphere.setMode("idle");
  }

  // The streaming session ended without the user tapping stop — most often
  // Yandex's own stream timing out after a long pause, not a real failure.
  // Reconnect transparently so hands-free mode doesn't quietly die; but cap
  // how often that can happen in a burst so a genuine outage (speechkit
  // unreachable, every reconnect immediately dying again) surfaces as a
  // visible error instead of spinning silently forever.
  //
  // Deliberately reconnects only the STT socket, reusing the still-live mic
  // stream, rather than going through startRecording() (which calls
  // newTurn() and so would cut off any reply the bot happens to be speaking
  // right now) — nothing the user did caused this, so it must not sound like
  // they interrupted the bot.
  function resumeHandsFreeAfterUnsolicitedEnd(myTurn) {
    if (myTurn !== turn) return; // a newer session already replaced this one
    if (!recStream || recStream.getTracks().every((tr) => tr.readyState === "ended")) {
      giveUpHandsFree(t("micDenied"));
      return;
    }
    const now = Date.now();
    if (now - autoRestartWindowStart > AUTO_RESTART_WINDOW_MS) {
      autoRestartWindowStart = now;
      autoRestartCount = 0;
    }
    autoRestartCount += 1;
    if (autoRestartCount > AUTO_RESTART_LIMIT) {
      giveUpHandsFree(t("error"));
      return;
    }
    if (pcmProcessor) {
      pcmProcessor.onaudioprocess = null;
      pcmProcessor.disconnect();
      pcmProcessor = null;
    }
    if (!startStreamingCapture(ensureAudioCtx(), recStream, myTurn)) {
      startBlobCapture(recStream, myTurn);
    }
  }

  function recoverFromMicError(err) {
    console.error("mic toggle failed:", err);
    recording = false;
    micBtn.classList.remove("recording");
    micBtn.setAttribute("aria-label", t("micStart"));
    micBtn.disabled = false;
    bubble(t("error"), "bot error");
    setStatus("idle");
    Sphere.setMode("idle");
  }

  function toggleRecording() {
    // Any unexpected error here must surface, not silently make the mic
    // button do nothing — that's indistinguishable from "broken" to the user.
    // startRecording() is async and called without await, so its errors need
    // a .catch(), not just try/catch (which only sees synchronous throws).
    try {
      if (recording) {
        if (currentSource) {
          // The bot is mid-reply — a tap now means "stop talking, I have
          // something to say", not "end the conversation". Cut the audio
          // (this also un-mutes the mic) and keep hands-free mode listening.
          stopSpeaking();
          setStatus("listening", true);
          Sphere.setMode("listening");
        } else {
          stopRecording();
        }
      } else {
        // A deliberate fresh start shouldn't inherit an unrelated earlier
        // burst of unsolicited reconnects counted against the auto-restart cap.
        autoRestartCount = 0;
        startRecording().catch(recoverFromMicError);
      }
    } catch (err) {
      recoverFromMicError(err);
    }
  }

  micBtn.addEventListener("click", toggleRecording);

  // ── Pipeline (fallback blob-upload path) ────────────────────────────────

  async function handleRecording(blob, myTurn) {
    try {
      // One round trip: STT → chat → TTS run server-side (like the Telegram
      // bot), instead of the browser paying internet latency between stages.
      const fd = new FormData();
      fd.append("session_id", sessionId);
      if (userName) fd.append("user_name", userName);
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
        if (userName) fd.append("user_name", userName);
        const resp = await fetch("/api/converse", { method: "POST", body: fd });
        if (!resp.ok) throw new Error(`converse ${resp.status}`);
        data = await resp.json();
      } else {
        const resp = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, text, user_name: userName }),
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
      // Any new reply resolves whatever confirmation was previously pending —
      // including one answered by voice, where there's no button click to
      // remove it. A fresh confirm rebuilds its own row right after.
      clearConfirmUI();
      if (data.operation) {
        // A completed operation stays in the log as a persistent card — in
        // BOTH modalities. This is the durable record, synced with Telegram.
        if (data.operation.document) {
          // Not awaited: the generating/flying flourish runs concurrently
          // with the spoken reply below, rather than delaying it.
          animateDocumentGeneration(data.operation);
        } else {
          opCard({ ...data.operation, created_at: new Date().toISOString() });
        }
      } else if (!voice || confirming) {
        // Text modality shows every reply; voice modality shows only the
        // confirmation (so the user sees exactly what they approve).
        const el = bubble(data.message, "bot");
        if (confirming) confirmButtons(voice, el);
      }

      if (voice && data.audio) {
        // Non-confirmation replies get the vaporizing caption instead of a
        // static bubble — something to watch while the answer is spoken,
        // instead of silence during the wait.
        const captionText = !confirming && !data.operation ? data.message : null;
        await playBase64(data.audio, myTurn, captionText);
      }
      // TTS failed and nothing is on screen yet → fall back to text.
      else if (voice && data.message && !confirming && !data.operation)
        bubble(data.message, "bot");
    } finally {
      // Only the current turn may reset the UI — an interrupted reply must
      // not stomp the state of the action that interrupted it.
      if (myTurn === turn) {
        // Hands-free mode is still listening for the next turn — "idle"
        // would wrongly read as "stopped" when the mic is still live.
        if (recording) {
          setStatus("listening", true);
          Sphere.setMode("listening");
        } else {
          setStatus("idle");
          Sphere.setMode("idle");
        }
      }
    }
  }

  async function playBase64(b64, myTurn = turn, captionText = null) {
    // A newer user action started while this reply was in flight → stay silent.
    if (myTurn !== turn) return;
    try {
      const raw = atob(b64);
      const bytes = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

      const ctx = ensureAudioCtx();
      const buffer = await ctx.decodeAudioData(bytes.buffer);
      if (myTurn !== turn) return; // interrupted during decode
      stopSpeaking(); // safety net: never two sources at once (also clears any caption)

      const src = ctx.createBufferSource();
      src.buffer = buffer;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      analyser.connect(ctx.destination);
      currentSource = src;
      // The mic stays live (not muted) during playback so a spoken
      // "stop"/"wait" can interrupt — the server just needs to know we're
      // speaking, to tell an interrupt word apart from hearing itself.
      setBotSpeaking(true);

      Sphere.setMode("speaking");
      setStatus("speaking", true);
      trackLevel(analyser);
      if (captionText) playCaption(captionText, buffer.duration * 1000);

      await new Promise((resolve) => {
        src.onended = resolve; // fires on natural end AND on .stop()
        src.start();
      });
      if (currentSource === src) currentSource = null;
      setBotSpeaking(false);
      stopLevel();
      clearCaption();
    } catch (err) {
      console.error("tts playback:", err);
      setBotSpeaking(false);
      stopLevel();
      clearCaption();
    }
  }

  // The sphere is a talk button too: tap to speak, tap again to finish.
  // Tapping while the bot talks cuts the speech and starts listening
  // (startRecording opens a new turn, which stops any current playback).
  document.getElementById("sphere").addEventListener("click", () => {
    if (micBtn.disabled) return; // mid-processing — ignore taps
    toggleRecording();
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
