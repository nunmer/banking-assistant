/* Digital sphere — a rotating particle globe that reacts to voice.
 *
 * Exposes window.Sphere with:
 *   Sphere.setLevel(v)   0..1 smoothed audio level (mic or TTS playback)
 *   Sphere.setMode(m)    "idle" | "listening" | "thinking" | "speaking"
 *
 * Pure canvas 2D: ~700 points on a Fibonacci lattice, perspective-projected,
 * displaced along their normals by a per-point wave driven by the audio level.
 */
(function () {
  const canvas = document.getElementById("sphere");
  const ctx = canvas.getContext("2d");

  const COUNT = 700;
  const points = [];
  // Fibonacci sphere: near-uniform point distribution.
  const GA = Math.PI * (3 - Math.sqrt(5)); // golden angle
  for (let i = 0; i < COUNT; i++) {
    const y = 1 - (i / (COUNT - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const th = GA * i;
    points.push({
      x: Math.cos(th) * r,
      y,
      z: Math.sin(th) * r,
      phase: Math.random() * Math.PI * 2,
      speed: 0.6 + Math.random() * 1.1,
    });
  }

  // Mode → base colour temperature and idle motion.
  const MODES = {
    idle:      { hueA: 326, hueB: 286, breathe: 0.028, spin: 0.0016 },
    listening: { hueA: 336, hueB: 300, breathe: 0.05,  spin: 0.0034 },
    thinking:  { hueA: 306, hueB: 266, breathe: 0.04,  spin: 0.006 },
    speaking:  { hueA: 330, hueB: 290, breathe: 0.05,  spin: 0.0026 },
  };

  let mode = MODES.idle;
  let level = 0;        // raw target from audio
  let shownLevel = 0;   // smoothed (fast attack, slow release)
  let rotY = 0;
  let rotX = -0.35;
  let t = 0;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const size = canvas.clientWidth;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  window.addEventListener("resize", resize);
  resize();

  function frame() {
    const size = canvas.clientWidth;
    const cx = size / 2;
    const cy = size / 2;
    const R = size * 0.33;

    // Attack fast so speech onsets snap; release slowly so it feels alive.
    shownLevel += (level - shownLevel) * (level > shownLevel ? 0.4 : 0.06);

    t += 1;
    rotY += mode.spin + shownLevel * 0.004;
    const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
    const cosX = Math.cos(rotX), sinX = Math.sin(rotX);

    ctx.clearRect(0, 0, size, size);

    // Center glow breathing with the level.
    const glowR = R * (0.9 + shownLevel * 0.55);
    const glow = ctx.createRadialGradient(cx, cy, R * 0.1, cx, cy, glowR);
    glow.addColorStop(0, `hsla(${mode.hueA}, 90%, 55%, ${0.20 + shownLevel * 0.25})`);
    glow.addColorStop(1, "transparent");
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, size, size);

    // Draw back-to-front for painter's-order depth.
    const projected = [];
    for (const p of points) {
      // Rotate around Y, then X.
      let x = p.x * cosY + p.z * sinY;
      let z = -p.x * sinY + p.z * cosY;
      let y = p.y * cosX - z * sinX;
      z = p.y * sinX + z * cosX;

      // Radial displacement: idle breathing + audio-driven wave.
      const wave =
        Math.sin(t * 0.02 * p.speed + p.phase) * mode.breathe +
        Math.sin(t * 0.11 * p.speed + p.phase * 3) * shownLevel * 0.30;
      const d = 1 + wave;

      const scale = 1 / (1.65 - z * 0.62); // perspective
      projected.push({
        sx: cx + x * d * R * scale * 1.28,
        sy: cy + y * d * R * scale * 1.28,
        z,
        scale,
      });
    }
    projected.sort((a, b) => a.z - b.z);

    for (const q of projected) {
      const depth = (q.z + 1) / 2; // 0 back → 1 front
      const hue = mode.hueB + (mode.hueA - mode.hueB) * depth;
      const alpha = 0.16 + depth * 0.74;
      const size_ = (0.9 + depth * 1.7) * q.scale * (1 + shownLevel * 0.7);
      ctx.beginPath();
      ctx.arc(q.sx, q.sy, size_, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${hue}, 88%, ${48 + depth * 22}%, ${alpha})`;
      ctx.fill();
    }

    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  window.Sphere = {
    setLevel(v) { level = Math.max(0, Math.min(1, v)); },
    setMode(name) { mode = MODES[name] || MODES.idle; if (name === "idle" || name === "thinking") level = 0; },
  };
})();
