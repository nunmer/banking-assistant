/* Forte Premier concierge orb.
 *
 * Exposes window.Sphere with the contract app.js already relies on:
 *   Sphere.setLevel(v)   0..1 audio level (mic while listening, TTS while speaking)
 *   Sphere.setMode(m)    "idle" | "listening" | "thinking" | "speaking"
 *
 * This is a direct port of the AI_Orb layer from FortePremier_Concept_2026,
 * not an interpretation of it. The Figma layer is:
 *
 *   1. a flat #C9B07E disc, with a greyscale render of folded silk
 *      luminosity-blended onto it — shipped here as orb-texture.png, cropped
 *      straight out of the export;
 *   2. that whole result screen-blended over a #614C20 disc. The order matters
 *      and is easy to get backwards: screening last is what lifts the shadow
 *      folds to a warm brown instead of letting them fall to near-black;
 *   3. a 1px ring at 1.225x the orb radius carrying an angular gradient with
 *      two opposed #C9B07E lobes ~90 degrees wide, centred on the upper-right
 *      and lower-left diagonal.
 *
 * Everything the concept does is therefore *already* in the texture. Earlier
 * attempts at shading a sphere procedurally kept landing on something that read
 * as a moon, because any noise — fbm included — becomes surface texture at this
 * scale, and the concept is polished metal folding over itself.
 *
 * What this file adds on top of the static layer is motion, and only three
 * kinds, all of which leave the composition recognisable:
 *   - a differential twist, so the outer gold shears past the core and the
 *     folds move without the whole ball spinning like a solid;
 *   - a global spin that advances only while there is audio, so an idle orb
 *     holds the pose the concept was drawn in;
 *   - bloom and ring brightness tracking the level.
 *
 * Two invariants, both of which previous versions broke:
 *   - The silhouette never moves. Level feeds brightness and flow, and scale by
 *     at most 3%, so loud speech reads as the orb running hotter rather than as
 *     it tearing itself apart.
 *   - The bloom is forced to zero before the canvas edge, so it never shows as
 *     a square.
 */
(function () {
  const canvas = document.getElementById("sphere");
  if (!canvas) return;

  // Orb radius in shader units, where 1.0 is half the canvas height. The Figma
  // orb is 150px across in a 402px frame and its ring sits at 183.75px, so the
  // canvas is drawn at 260px to leave the ring and the bloom somewhere to go:
  // 150 / 260 = 0.577.
  const R_BASE = 0.577;
  const RING_FACTOR = 1.225; // 91.875 / 75, straight off the export

  const TEXTURE_URL = "/static/orb-texture.png";

  // The concept draws no glow at all, so idle bloom is zero and an untouched
  // page is the concept frame exactly. Bloom only exists to signal that audio
  // is being heard, so it belongs to the states that have audio.
  const MODES = {
    idle:      { fold: 0.45, spin: 0.00, react: 0.55, bloom: 0.00, breathe: 0.007 },
    listening: { fold: 1.00, spin: 1.00, react: 1.00, bloom: 0.22, breathe: 0.011 },
    thinking:  { fold: 1.55, spin: 0.55, react: 0.30, bloom: 0.12, breathe: 0.009 },
    speaking:  { fold: 1.25, spin: 0.90, react: 0.92, bloom: 0.24, breathe: 0.010 },
  };

  let mode = MODES.idle;
  let level = 0;   // raw target from audio
  let shown = 0;   // smoothed; everything visible is driven from this

  let foldPhase = 0;
  let wavePhase = 0;
  let spinPhase = 0;
  // The ring's lobes start where the concept puts them: 60 degrees up from the
  // right, i.e. the upper-right / lower-left diagonal.
  let ringPhase = Math.PI / 3;
  let breatheT = 0;

  // Eased mode weight, so switching modes fades instead of snapping.
  let bloomW = MODES.idle.bloom;

  let lastT = 0;

  /* Advance every animated quantity by dt seconds. Split out so the WebGL and
   * fallback renderers stay in lockstep on timing. */
  function step(dt) {
    // A fast attack made every consonant snap the orb outward; releasing more
    // slowly than it attacks keeps the motion continuous either way.
    const rate = level > shown ? 6.5 : 3.0;
    shown += (level - shown) * (1 - Math.exp(-dt * rate));
    bloomW += (mode.bloom - bloomW) * (1 - Math.exp(-dt * 2.2));

    const lit = shown * mode.react; // "how animated right now", 0..1

    foldPhase += dt * 0.22 * mode.fold;
    wavePhase += dt * (0.16 + lit * 0.20) * mode.fold;
    // Only turns while there is something to say, so an idle orb keeps the pose
    // the concept was drawn in instead of slowly drifting out of it.
    spinPhase += dt * (0.05 + lit * 0.30) * mode.spin;
    ringPhase += dt * (0.10 + lit * 0.25);
    breatheT += dt;

    const breath = Math.sin(breatheT * 0.62) * mode.breathe;
    return { lit, radius: R_BASE * (1 + breath + lit * 0.03) };
  }

  // ── WebGL renderer ──────────────────────────────────────────────────────

  const VERT = `
    attribute vec2 aPos;
    void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
  `;

  const FRAG = `
    precision highp float;

    uniform vec2      uRes;
    uniform sampler2D uTex;
    uniform float     uHasTex;
    uniform float     uRadius;
    uniform float     uLevel;
    uniform float     uBloom;
    uniform float     uFold;
    uniform float     uWave;
    uniform float     uSpin;
    uniform float     uRingPhase;

    // #C9B07E — the brand gold. The disc fill the texture's luminosity is
    // applied over, and the colour of the ring and the bloom.
    const vec3 GOLD = vec3(0.78824, 0.69020, 0.49412);
    // #614C20 — the darker disc the shaded result is screened over.
    const vec3 BASE = vec3(0.38039, 0.29804, 0.12549);

    float lumOf(vec3 c) { return dot(c, vec3(0.3, 0.59, 0.11)); }

    /* ClipColor and SetLum from the PDF blend-mode spec, which is what Figma's
       "luminosity" implements. Doing this properly rather than just multiplying
       a ramp is what keeps the shadow folds gold instead of grey. */
    vec3 clipColor(vec3 c) {
      float l = lumOf(c);
      float n = min(min(c.r, c.g), c.b);
      float x = max(max(c.r, c.g), c.b);
      if (n < 0.0) c = l + (c - l) * (l / max(l - n, 1e-4));
      if (x > 1.0) c = l + (c - l) * ((1.0 - l) / max(x - l, 1e-4));
      return c;
    }

    vec3 setLum(vec3 c, float l) { return clipColor(c + (l - lumOf(c))); }

    /* Stand-in luminance for the one case where the texture is missing: a
       plainly lit sphere. Never the intended look, but the orb is the whole
       screen here, so it must not be able to come up empty. */
    float fallbackLum(vec2 p, float rr) {
      float z = sqrt(max(1.0 - rr * rr, 0.0));
      float d = max(dot(normalize(vec3(p, z + 0.001)),
                        normalize(vec3(-0.35, 0.45, 0.82))), 0.0);
      return 0.30 + 0.62 * pow(d, 0.9);
    }

    void main() {
      vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / (0.5 * uRes.y);
      float r = length(uv);
      float R = uRadius;
      float lvl = uLevel;

      // Premultiplied accumulation, so the layers composite without any
      // per-layer alpha bookkeeping.
      vec3  rgb = vec3(0.0);
      float a = 0.0;

      // ── Bloom ─────────────────────────────────────────────────────────
      // The concept has no glow around the orb; this is deliberately near zero
      // at idle and only opens up with audio, where it is doing a job —
      // showing the user they are being heard.
      float halo = exp(-max(r - R, 0.0) * 5.0) * smoothstep(1.0, R, r);
      float bloom = halo * (uBloom + lvl * 0.14);
      rgb += GOLD * bloom;
      a += bloom;

      // ── Ring ──────────────────────────────────────────────────────────
      // Two opposed lobes on a hairline circle, matching the angular gradient
      // in the export. Held to at least a device pixel so it survives on a
      // low-DPR screen.
      float ringR = R * ${RING_FACTOR};
      float halfW = max(0.0038, 1.2 / (0.5 * uRes.y));
      float band = smoothstep(halfW, 0.0, abs(r - ringR));
      float ang = atan(uv.y, uv.x);
      // acos(0.68) either side of the peak gives a ~94-degree lobe, matching
      // the angular gradient's transparent-to-transparent span.
      float lobe = pow(smoothstep(0.68, 1.0, abs(cos(ang - uRingPhase))), 1.5);
      float arc = band * lobe * 0.9 * (0.80 + lvl * 0.20);
      rgb += GOLD * arc;
      a += arc;

      // ── Body ──────────────────────────────────────────────────────────
      vec2 p = uv / R;
      float rr = min(length(p), 1.0);
      float th = atan(p.y, p.x);

      // Differential twist: the core is anchored and the outer gold swings
      // around it, so the folds shear past each other. A rigid rotation of the
      // whole texture reads as an object spinning; this reads as the material
      // moving, which is what the concept implies.
      float twist = uSpin
                  + rr * 0.34 * sin(uFold)
                  + sin(uWave + rr * 1.9) * 0.10;
      vec2 q = vec2(cos(th + twist), sin(th + twist)) * rr;

      // 0.4925 rather than 0.5 keeps the sample just inside the texture's own
      // antialiased edge, which would otherwise show as a dark hairline.
      float texLum = texture2D(uTex, vec2(0.5) + q * 0.4925).r;
      float Y = mix(fallbackLum(p, rr), texLum, uHasTex);

      // The concept's two stacked blends, in the order the export applies them.
      vec3 shaded = setLum(GOLD, clamp(Y + lvl * 0.05, 0.0, 1.0));
      vec3 body = 1.0 - (1.0 - BASE) * (1.0 - shaded); // screen


      // Antialias the silhouette over roughly one and a half device pixels.
      float aa = 1.5 / (0.5 * uRes.y);
      float inside = smoothstep(R + aa, R - aa, r);
      rgb = mix(rgb, body, inside);
      a = mix(a, 1.0, inside);

      gl_FragColor = vec4(rgb, clamp(a, 0.0, 1.0));
    }
  `;

  function compile(gl, type, src) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      gl.deleteShader(sh);
      return null;
    }
    return sh;
  }

  const UNIFORMS = ["uRes", "uTex", "uHasTex", "uRadius", "uLevel", "uBloom",
                    "uFold", "uWave", "uSpin", "uRingPhase"];

  /* Builds the program, quad and uniform table. Returns null if anything about
   * the GL path is unavailable, which hands the orb to the 2D fallback. */
  function buildGL(gl) {
    const vs = compile(gl, gl.VERTEX_SHADER, VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return null;

    const prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    gl.deleteShader(vs);
    gl.deleteShader(fs);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]), // one oversized triangle
      gl.STATIC_DRAW
    );

    gl.useProgram(prog);
    const loc = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    gl.disable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    // Premultiplied source, matching what the shader writes.
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

    const u = {};
    for (const name of UNIFORMS) u[name] = gl.getUniformLocation(prog, name);
    return { prog, u };
  }

  /* The texture is 512x512 and non-power-of-two in neither dimension, but
   * WebGL1 still requires CLAMP_TO_EDGE and no mipmaps for NPOT sources, which
   * is what it gets. The image is smooth enough that the missing mip levels
   * cost nothing visible. */
  function uploadTexture(gl, img) {
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    return tex;
  }

  function startGL(img) {
    const opts = {
      alpha: true,
      premultipliedAlpha: true,
      antialias: false, // the silhouette is analytically antialiased already
      depth: false,
      stencil: false,
      powerPreference: "low-power",
    };
    let gl;
    try {
      gl = canvas.getContext("webgl", opts) ||
           canvas.getContext("experimental-webgl", opts);
    } catch {
      return false;
    }
    if (!gl) return false;

    let built = buildGL(gl);
    if (!built) return false;

    let tex = img ? uploadTexture(gl, img) : null;
    let w = 0;
    let h = 0;

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const px = Math.max(1, Math.round(canvas.clientWidth * dpr));
      const py = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (px === w && py === h) return;
      w = px;
      h = py;
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
    }

    // A lost context cannot be recovered by re-reading the canvas, so hold the
    // slot and rebuild once the browser hands it back.
    canvas.addEventListener("webglcontextlost", (e) => {
      e.preventDefault();
      built = null;
    });
    canvas.addEventListener("webglcontextrestored", () => {
      built = buildGL(gl);
      tex = img ? uploadTexture(gl, img) : null;
      w = h = 0;
    });

    function frame(now) {
      requestAnimationFrame(frame);
      const dt = lastT ? Math.min((now - lastT) / 1000, 0.05) : 0;
      lastT = now;
      const { radius } = step(dt);
      if (!built) return;

      resize();
      const u = built.u;
      gl.useProgram(built.prog);
      if (tex) {
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.uniform1i(u.uTex, 0);
      }
      gl.uniform1f(u.uHasTex, tex ? 1 : 0);
      gl.uniform2f(u.uRes, w, h);
      gl.uniform1f(u.uRadius, radius);
      gl.uniform1f(u.uLevel, shown * mode.react);
      gl.uniform1f(u.uBloom, bloomW);
      gl.uniform1f(u.uFold, foldPhase);
      gl.uniform1f(u.uWave, wavePhase);
      gl.uniform1f(u.uSpin, spinPhase);
      gl.uniform1f(u.uRingPhase, ringPhase);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    requestAnimationFrame(frame);
    return true;
  }

  // ── Canvas-2D fallback ──────────────────────────────────────────────────
  // Only reached when WebGL is unavailable. Same three Figma layers, composited
  // with the canvas "luminosity" blend mode instead of shaded per pixel, so the
  // twist has to be a rigid rotation. No per-frame blur anywhere — that is the
  // expensive operation the whole rewrite exists to avoid.

  function start2D(img) {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    function frame(now) {
      requestAnimationFrame(frame);
      const dt = lastT ? Math.min((now - lastT) / 1000, 0.05) : 0;
      lastT = now;
      const { lit, radius } = step(dt);

      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const size = canvas.clientWidth;
      if (canvas.width !== Math.round(size * dpr)) {
        canvas.width = canvas.height = Math.round(size * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);

      const cx = size / 2;
      const cy = size / 2;
      const R = (size / 2) * radius;

      const bloomR = Math.min(size * 0.49, R * 1.9);
      const bloom = ctx.createRadialGradient(cx, cy, R * 0.95, cx, cy, bloomR);
      bloom.addColorStop(0, `rgba(201, 176, 126, ${(bloomW + lit * 0.14).toFixed(3)})`);
      bloom.addColorStop(1, "rgba(201, 176, 126, 0)");
      ctx.fillStyle = bloom;
      ctx.fillRect(0, 0, size, size);

      // The concept's three layers in order: gold disc, luminosity texture,
      // then #614C20 screened in. Screen is commutative, so painting the darker
      // disc last over the top is the same as compositing the pair onto it.
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.clip();
      ctx.fillStyle = "#c9b07e";
      ctx.fill();
      if (img) {
        ctx.save();
        ctx.globalCompositeOperation = "luminosity";
        ctx.translate(cx, cy);
        ctx.rotate(spinPhase + Math.sin(foldPhase) * 0.18);
        const d = R / 0.985;
        ctx.drawImage(img, -d, -d, d * 2, d * 2);
        ctx.restore();
      }
      ctx.globalCompositeOperation = "screen";
      ctx.fillStyle = "#614c20";
      ctx.fill();
      ctx.restore();

      // The ring's two lobes, drawn as tapered arcs. Canvas angles run
      // clockwise with y down, so the phase is negated to put the lobes on the
      // same diagonal the shader does.
      ctx.save();
      ctx.lineWidth = Math.max(1, size * 0.004);
      ctx.lineCap = "round";
      const ringR = R * RING_FACTOR;
      const half = 0.82; // ~94 degrees of sweep, as in the export
      for (const side of [0, Math.PI]) {
        const mid = -ringPhase + side;
        const grad = ctx.createLinearGradient(
          cx + Math.cos(mid - half) * ringR, cy + Math.sin(mid - half) * ringR,
          cx + Math.cos(mid + half) * ringR, cy + Math.sin(mid + half) * ringR
        );
        grad.addColorStop(0, "rgba(201, 176, 126, 0)");
        grad.addColorStop(0.5, `rgba(201, 176, 126, ${(0.72 + lit * 0.18).toFixed(3)})`);
        grad.addColorStop(1, "rgba(201, 176, 126, 0)");
        ctx.strokeStyle = grad;
        ctx.beginPath();
        ctx.arc(cx, cy, ringR, mid - half, mid + half);
        ctx.stroke();
      }
      ctx.restore();
    }
    requestAnimationFrame(frame);
  }

  // The orb is the entire screen here, so a missing texture must still render:
  // both renderers accept null and degrade rather than showing nothing.
  const img = new Image();
  img.onload = () => {
    if (!startGL(img)) start2D(img);
  };
  img.onerror = () => {
    if (!startGL(null)) start2D(null);
  };
  img.src = TEXTURE_URL;

  window.Sphere = {
    setLevel(v) {
      level = Math.max(0, Math.min(1, Number(v) || 0));
    },
    setMode(name) {
      mode = MODES[name] || MODES.idle;
      // Idle and thinking carry no audio — let the level fall away through the
      // smoother rather than cutting it, which used to show as a visible jolt.
      if (name === "idle" || name === "thinking") level = 0;
    },
  };
})();
