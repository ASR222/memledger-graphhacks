/* MemLedger cursor follower: a soft violet glow behind the content and a small
   ring that trails the pointer. Both are pointer-events: none, moved only with
   translate3d, and eased with one lerp per frame. The frame loop parks itself
   once both have caught up, so it costs nothing while the pointer is still and
   never competes with the graph's own rendering. Off on touch devices and with
   prefers-reduced-motion. */
(() => {
  const mq = (q) => window.matchMedia?.(q).matches;
  if (mq("(pointer: coarse)") || mq("(prefers-reduced-motion: reduce)")) return;

  const glow = document.createElement("div");
  glow.className = "cursor-glow";
  const ring = document.createElement("div");
  ring.className = "cursor-ring";
  for (const el of [glow, ring]) el.setAttribute("aria-hidden", "true");
  document.body.append(glow, ring);

  const EASE = 0.15;          /* lerp per 60 Hz frame */
  const GLOW_R = 150;         /* half of the 300px glow */
  const RING_R = 4;           /* half of the 8px ring */
  const INTERACTIVE = "a, button, select, input, textarea, label, [role=button], .tab, .cite, .src, .entry li, .radius-list li, .fact";

  const target = { x: -999, y: -999 };
  const g = { x: -999, y: -999 };
  const r = { x: -999, y: -999 };
  let raf = 0, prev = 0, shown = false;

  const place = () => {
    glow.style.transform = `translate3d(${(g.x - GLOW_R).toFixed(1)}px, ${(g.y - GLOW_R).toFixed(1)}px, 0)`;
    ring.style.transform = `translate3d(${(r.x - RING_R).toFixed(1)}px, ${(r.y - RING_R).toFixed(1)}px, 0)`;
  };

  const tick = (now) => {
    const dt = prev ? Math.min(3, (now - prev) / 16.67) : 1;
    prev = now;
    /* frame-rate independent: the same easing on a busy page as on an idle one */
    const k = 1 - Math.pow(1 - EASE, dt);
    const kg = 1 - Math.pow(1 - EASE * 0.6, dt);   /* the glow drifts a little slower */
    r.x += (target.x - r.x) * k; r.y += (target.y - r.y) * k;
    g.x += (target.x - g.x) * kg; g.y += (target.y - g.y) * kg;
    place();
    const settled = Math.abs(target.x - g.x) < 0.3 && Math.abs(target.y - g.y) < 0.3 &&
                    Math.abs(target.x - r.x) < 0.3 && Math.abs(target.y - r.y) < 0.3;
    if (settled) { raf = 0; prev = 0; return; }
    raf = requestAnimationFrame(tick);
  };
  const wake = () => { if (!raf) raf = requestAnimationFrame(tick); };

  const show = (on) => {
    if (on === shown) return;
    shown = on;
    glow.classList.toggle("on", on);
    ring.classList.toggle("on", on);
  };

  window.addEventListener("pointermove", (e) => {
    if (e.pointerType && e.pointerType !== "mouse" && e.pointerType !== "pen") return;
    target.x = e.clientX; target.y = e.clientY;
    if (!shown) { g.x = r.x = target.x; g.y = r.y = target.y; place(); }  /* appear in place, don't fly in */
    show(true);
    wake();
  }, { passive: true });

  /* grow the ring over things you can click; otherwise leave it alone */
  document.addEventListener("pointerover", (e) => {
    ring.classList.toggle("hot", !!e.target.closest?.(INTERACTIVE));
  }, { passive: true });

  /* hidden when the cursor leaves the window or the tab */
  document.documentElement.addEventListener("pointerleave", () => show(false));
  document.addEventListener("mouseout", (e) => { if (!e.relatedTarget) show(false); });
  window.addEventListener("blur", () => show(false));
  document.addEventListener("visibilitychange", () => { if (document.hidden) show(false); });
})();
