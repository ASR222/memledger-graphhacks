/* MemLedger /demo landing page: the hero video, the header nav and small helpers.
   The header's eye tracker lives in watcher.js, shared with the console. */

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
    const pill = document.createElement("span");
    pill.className = "status-pill";
    pill.title = "Modes reported by /api/health";
    const dot = document.createElement("span");
    dot.className = "pulse";
    dot.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = `extract: ${h.extract} · agents: ${h.agents}`;
    pill.title = `${label.textContent} (from /api/health)`;
    pill.append(dot, label);
    el.replaceChildren(pill);
  } catch {
    el.textContent = "";
  }
}

/* header: the hamburger below 1100px, and the section you're reading marked in the nav */
function headerNav() {
  const nav = document.getElementById("siteNav");
  const btn = document.querySelector(".menu-toggle");
  if (!nav) return;
  const close = () => { nav.classList.remove("open"); btn?.setAttribute("aria-expanded", "false"); btn?.setAttribute("aria-label", "Open menu"); };
  btn?.addEventListener("click", () => {
    const open = !nav.classList.contains("open");
    nav.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", String(open));
    btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  });
  nav.addEventListener("click", (e) => { if (e.target.closest("a")) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  const links = [...nav.querySelectorAll('a[href^="#"]')];
  const byId = new Map(links.map((a) => [a.getAttribute("href").slice(1), a]));
  const mark = (id) => links.forEach((a) => {
    const on = a === byId.get(id);
    a.classList.toggle("on", on);
    if (on) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
  });
  if (!("IntersectionObserver" in window)) return;
  const io = new IntersectionObserver((entries) => {
    const seen = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
    if (seen.length) mark(seen[0].target.id);
    else if (window.scrollY < 200) mark(null);
  }, { rootMargin: "-64px 0px -60% 0px" });
  byId.forEach((_, id) => { const s = document.getElementById(id); if (s) io.observe(s); });
}

document.addEventListener("DOMContentLoaded", () => {
  headerNav();
  mountVideo();
  copyButtons();
  liveModes();
});
