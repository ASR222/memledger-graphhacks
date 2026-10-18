/* MemLedger /demo landing page: the hero video and the header's eye tracker. */

/* ── the demo video ──────────────────────────────────────────
   Paste the YouTube link here (watch?v=, youtu.be/, /embed/ or
   /shorts/ all work). Empty shows a placeholder in the hero. */
const DEMO_VIDEO = "";

function youtubeId(url) {
  if (!url) return null;
  try {
    const u = new URL(url);
    if (u.hostname.endsWith("youtu.be")) return u.pathname.slice(1).split("/")[0] || null;
    if (u.searchParams.get("v")) return u.searchParams.get("v");
    const m = u.pathname.match(/\/(?:embed|shorts|live)\/([\w-]{6,})/);
    return m ? m[1] : null;
  } catch {
    return /^[\w-]{11}$/.test(url) ? url : null;
  }
}

function mountVideo() {
  const box = document.getElementById("video");
  if (!box) return;
  const id = youtubeId(DEMO_VIDEO);
  if (!id) return; /* the placeholder already in the HTML stays */
  const f = document.createElement("iframe");
  f.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}?rel=0&modestbranding=1`;
  f.title = "MemLedger demo video";
  f.loading = "lazy";
  f.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
  f.referrerPolicy = "strict-origin-when-cross-origin";
  f.allowFullscreen = true;
  box.replaceChildren(f);
  box.classList.add("has-video");
}

/* ══ Eye tracker ═════════════════════════════════════════════
   A vanilla port of the Watcher component: a body with two eyes
   that turns toward the cursor. Each eye is a point on a sphere,
   so the one heading for the rim moves less and narrows as it
   turns away; one sprung turn (yaw and pitch) drives both eyes,
   it blinks now and then, and a press makes it say something.
   Written straight to the DOM every frame, never re-rendered. */

const stillness = () => !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

const R = 50; /* the body's radius in the 100-unit viewBox */
const STYLES = {
  Slant: { w: 9, h: 15, r: 4.5 },
  Dots: { w: 11, h: 11, r: 5.5 },
  Squares: { w: 12, h: 12, r: 3.5 },
};
const GAP = 0.19; /* half the gap between the eyes, as a fraction of the radius */
const TILT = 64; /* how far a look to a corner tilts the pair, in degrees at the rim */
const SHAPES = {
  Ball: "M50 0 A50 50 0 1 1 49.99 0 Z",
  Circle: "M50 7 A43 43 0 1 1 49.99 7 Z",
  Cube: "M30 6 H70 A24 24 0 0 1 94 30 V70 A24 24 0 0 1 70 94 H30 A24 24 0 0 1 6 70 V30 A24 24 0 0 1 30 6 Z",
  Pill: "M34 17 H66 A33 33 0 0 1 66 83 H34 A33 33 0 0 1 34 17 Z",
  Hexagon: "M59.53 8.50 L81.18 21.00 Q90.70 26.50 90.70 37.50 L90.70 62.50 Q90.70 73.50 81.18 79.00 L59.53 91.50 Q50.00 97.00 40.47 91.50 L18.82 79.00 Q9.30 73.50 9.30 62.50 L9.30 37.50 Q9.30 26.50 18.82 21.00 L40.47 8.50 Q50.00 3.00 59.53 8.50 Z",
};
/* it talks back when you poke it */
const LINES = [
  "Hey, I see you.", "Boop.", "That tickles.", "Hi there!",
  "Stop poking me.", "I'm watching you.", "Again? Okay.", "You found me.",
  "I remember who said that.", "Revoked. All of it.",
];
const TINTS = ["#8f7cff", "#3ecf8e", "#5ab0ff"];
const KEY_MS = 38;
const HOLD_MS = 1500;

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const NS = "http://www.w3.org/2000/svg";
let clipSeq = 0;

function watcher(el, opts = {}) {
  const o = {
    follow: 60, bounce: 30, size: 100, shape: "Cube", eyes: "Slant",
    eyeScale: 1, eyeWidth: 1, eyeRound: 1, eyeHeight: 1, idle: false, ...opts,
  };
  const still = stillness();
  const base = STYLES[o.eyes] || STYLES.Slant;
  const eye = {
    w: base.w * o.eyeScale * o.eyeWidth,
    h: base.h * o.eyeScale * o.eyeHeight,
    r: base.r * o.eyeScale * o.eyeWidth * o.eyeRound,
  };
  const s = clamp(o.size, 16, 180);
  const clip = `eyt-clip-${++clipSeq}`;
  const body = SHAPES[o.shape] || SHAPES.Ball;

  el.classList.add("eyt");
  el.style.setProperty("--eyt-size", `${s}px`);
  el.setAttribute("role", "img");
  el.setAttribute("aria-label", "A small face with two eyes that follows the cursor");

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "eyt-ball");
  svg.setAttribute("viewBox", "0 0 100 100");
  if (!o.idle) svg.setAttribute("data-poke", "");
  svg.innerHTML =
    `<defs><clipPath id="${clip}"><path d="${body}"/></clipPath></defs>` +
    `<path class="eyt-body" d="${body}"/>` +
    `<g clip-path="url(#${clip})">` +
    [0, 1].map(() => `<g><rect class="eyt-eye" x="${-eye.w / 2}" y="${-eye.h / 2}" width="${eye.w}" height="${eye.h}" rx="${eye.r}"/></g>`).join("") +
    `</g>`;
  el.appendChild(svg);
  const eyes = [...svg.querySelectorAll("g[clip-path] > g")];

  /* the bubble: types one short line, holds it, folds away */
  let say = null, typed = null, turn = 0, lastLine = -1;
  if (!o.idle) {
    say = document.createElement("span");
    say.className = "eyt-say";
    say.setAttribute("aria-live", "polite");
    typed = document.createElement("span");
    const caret = document.createElement("span");
    caret.className = "eyt-caret";
    say.append(typed, caret);
    el.appendChild(say);
    svg.addEventListener("click", async () => {
      const mine = ++turn;
      const pool = LINES.map((_, i) => i).filter((i) => i !== lastLine);
      const i = pool[Math.floor(Math.random() * pool.length)];
      lastLine = i;
      const line = LINES[i];
      const wait = (ms) => new Promise((r) => setTimeout(r, ms));
      say.style.setProperty("--tint", TINTS[Math.floor(Math.random() * TINTS.length)]);
      typed.textContent = "";
      say.setAttribute("data-on", "");
      for (let k = 1; k <= line.length; k++) {
        await wait(KEY_MS + Math.random() * 30);
        if (mine !== turn) return;
        typed.textContent = line.slice(0, k);
      }
      await wait(HOLD_MS);
      if (mine !== turn) return;
      say.removeAttribute("data-on");
    });
  }

  /* where the face is on the ball (fractions of the radius), its
     speed, and where it is heading: one spring on a point */
  const t = { x: 0, y: 0, vx: 0, vy: 0, tx: 0, ty: 0 };
  let prev = 0, blink = 0, nextBlink = performance.now() + 2200;

  const draw = (now) => {
    let lid = 1;
    if (now > nextBlink) {
      blink = now;
      nextBlink = now + (o.idle ? 2000 : 2600 + Math.random() * 3200);
    }
    const since = now - blink;
    if (since < 160) lid = 1 - 0.9 * Math.sin((since / 160) * Math.PI);

    const as = (v) => Math.asin(clamp(v, -0.92, 0.92));
    const yaw = as(t.x), pitch = -as(t.y);
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const tilt = TILT * t.x * t.y;
    const g0 = GAP * Math.max(1, o.eyeScale * 0.8);

    [-g0, g0].forEach((x0, i) => {
      const g = eyes[i];
      const z0 = Math.sqrt(1 - x0 * x0);
      const x1 = x0 * cy + z0 * sy;
      const z1 = -x0 * sy + z0 * cy;
      const y2 = -z1 * sp;
      const z2 = z1 * cp;
      /* depth: the eye nearer the rim is smaller, and narrower across the turn */
      const near = clamp(z2, 0, 1);
      const k = 0.45 + 0.55 * near;
      const sx = k * (0.7 + 0.3 * near);
      /* written as a size, never a scale, so the corners stay round */
      const w = eye.w * sx;
      const h = Math.max(0.6, eye.h * k * lid);
      const rect = g.firstElementChild;
      rect.setAttribute("x", (-w / 2).toFixed(2));
      rect.setAttribute("y", (-h / 2).toFixed(2));
      rect.setAttribute("width", w.toFixed(2));
      rect.setAttribute("height", h.toFixed(2));
      rect.setAttribute("rx", Math.min(eye.r, w / 2, h / 2).toFixed(2));
      g.setAttribute("transform", `translate(${(50 + x1 * R).toFixed(2)} ${(50 + y2 * R).toFixed(2)}) rotate(${tilt.toFixed(2)})`);
      g.style.opacity = z2 < 0.05 ? "0" : "1";
    });
  };

  /* frames, not milliseconds: a dropped frame decays the same energy */
  let raf = 0;
  const tick = (now) => {
    const dt = prev ? Math.min(2.5, (now - prev) / 16.67) : 1;
    prev = now;
    if (still) {
      t.x = t.tx; t.y = t.ty;
    } else {
      const k = 0.06;
      const d = 0.34 - (clamp(o.bounce, 0, 100) / 100) * 0.22;
      t.vx += ((t.tx - t.x) * k - t.vx * d) * dt;
      t.vy += ((t.ty - t.y) * k - t.vy * d) * dt;
      t.x += t.vx * dt;
      t.y += t.vy * dt;
    }
    draw(now);
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  /* don't spin a frame loop in a background tab */
  document.addEventListener("visibilitychange", () => {
    cancelAnimationFrame(raf);
    if (!document.hidden) { prev = 0; raf = requestAnimationFrame(tick); }
  });

  const rest = () => { t.tx = 0; t.ty = 0; };
  if (o.idle) {
    const look = () => {
      const a = Math.random() * Math.PI * 2;
      const far = 0.45 + Math.random() * 0.25;
      t.tx = Math.cos(a) * far; t.ty = Math.sin(a) * far;
      setTimeout(() => { rest(); setTimeout(look, 5000 - 900); }, 900);
    };
    setTimeout(look, 5000);
    return;
  }

  /* the face goes where you are: a spot out along the pointer's
     direction, further the further away you are. In the header it
     watches the whole page, so the reach is measured on the viewport. */
  const aim = (e) => {
    const r = el.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width / 2);
    const dy = e.clientY - (r.top + r.height / 2);
    const d = Math.hypot(dx, dy) || 1;
    const reach = Math.max(60, Math.min(window.innerWidth, window.innerHeight) * 0.28);
    const far = Math.min(0.85, Math.tanh(d / reach) * (clamp(o.follow, 0, 100) / 100) * 1.5);
    t.tx = (dx / d) * far;
    t.ty = (dy / d) * far;
  };
  window.addEventListener("pointermove", aim, { passive: true });
  document.documentElement.addEventListener("pointerleave", rest);
}

/* ── small page helpers ─────────────────────────────────────── */
function copyButtons() {
  document.querySelectorAll("pre[data-copy]").forEach((pre) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "copy";
    b.textContent = "Copy";
    b.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(pre.querySelector("code").innerText);
        b.textContent = "Copied";
      } catch {
        b.textContent = "Select and copy";
      }
      setTimeout(() => { b.textContent = "Copy"; }, 1400);
    });
    pre.appendChild(b);
  });
}

async function liveModes() {
  const el = document.getElementById("liveModes");
  if (!el) return;
  try {
    const h = await (await fetch("/api/health")).json();
    el.textContent = `This deployment: extract ${h.extract} · agents ${h.agents}`;
  } catch {
    el.textContent = "";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  mountVideo();
  document.querySelectorAll("[data-watcher]").forEach((el) =>
    watcher(el, { size: Number(el.dataset.size) || 34, shape: el.dataset.shape || "Cube", follow: 70 }));
  copyButtons();
  liveModes();
});
