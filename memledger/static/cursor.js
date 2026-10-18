/* MemLedger cursor glow: a soft violet light behind the content that follows the
   pointer. No ring or tail: the cursor itself is the violet arrow in style.css.
   pointer-events: none, moved only with translate3d, eased with one lerp per
   frame; the frame loop parks itself once the glow has caught up, so it costs
   nothing while the pointer is still and never competes with the graph's
   rendering. Off on touch devices and with prefers-reduced-motion. */
(() => {
  const mq = (q) => window.matchMedia?.(q).matches;
  if (mq("(pointer: coarse)") || mq("(prefers-reduced-motion: reduce)")) return;

  const glow = document.createElement("div");
  glow.className = "cursor-glow";
  glow.setAttribute("aria-hidden", "true");
  document.body.append(glow);

  const EASE = 0.15;   /* lerp per 60 Hz frame: close enough to read as light, not a tail */
  const R = 150;       /* half of the 300px glow */
  const target = { x: -999, y: -999 };
  const g = { x: -999, y: -999 };
  let raf = 0, prev = 0, shown = false;

  const place = () => {
    glow.style.transform = `translate3d(${(g.x - R).toFixed(1)}px, ${(g.y - R).toFixed(1)}px, 0)`;
  };
  const tick = (now) => {
    const dt = prev ? Math.min(3, (now - prev) / 16.67) : 1;
    prev = now;
    const k = 1 - Math.pow(1 - EASE, dt);   /* the same easing on a busy page as an idle one */
    g.x += (target.x - g.x) * k;
    g.y += (target.y - g.y) * k;
    place();
    if (Math.abs(target.x - g.x) < 0.3 && Math.abs(target.y - g.y) < 0.3) { raf = 0; prev = 0; return; }
    raf = requestAnimationFrame(tick);
  };
  const show = (on) => { if (on !== shown) { shown = on; glow.classList.toggle("on", on); } };

  window.addEventListener("pointermove", (e) => {
    if (e.pointerType && e.pointerType !== "mouse" && e.pointerType !== "pen") return;
    target.x = e.clientX; target.y = e.clientY;
    if (!shown) { g.x = target.x; g.y = target.y; place(); }   /* appear in place */
    show(true);
    if (!raf) raf = requestAnimationFrame(tick);
  }, { passive: true });

  /* hidden when the cursor leaves the window or the tab */
  document.documentElement.addEventListener("pointerleave", () => show(false));
  document.addEventListener("mouseout", (e) => { if (!e.relatedTarget) show(false); });
  window.addEventListener("blur", () => show(false));
  document.addEventListener("visibilitychange", () => { if (document.hidden) show(false); });
})();
