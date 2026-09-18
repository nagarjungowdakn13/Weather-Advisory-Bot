const scrollback = document.getElementById("scrollback");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const statusLabel = document.querySelector(".status-label");
const statusDot = document.querySelector(".dot");
const needle = document.getElementById("needle");
const chips = document.getElementById("chips");

const ICONS = {
  user: `<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="4" r="2.4" stroke="currentColor" stroke-width="1.1"/><path d="M1.5 10.3c.8-2.2 2.5-3.3 4.5-3.3s3.7 1.1 4.5 3.3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg>`,
  assistant: `<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M4 8.2a2.6 2.6 0 1 1 .5-5.1 3.2 3.2 0 0 1 6.1.9 2.3 2.3 0 0 1-.4 4.2H4Z" stroke="currentColor" stroke-width="1" stroke-linejoin="round"/><path d="M8.4 2.2 8 1M10 3l.9-.8M3 3.2l-.9-.7" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>`,
  system: `<svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M5.5 1 6.4 4.6 10 5.5 6.4 6.4 5.5 10 4.6 6.4 1 5.5 4.6 4.6 5.5 1Z" stroke="currentColor" stroke-width="0.9" stroke-linejoin="round"/></svg>`,
};

const THINKING_PHRASES = [
  "reading the sky…",
  "checking the barometer…",
  "cross-referencing conditions…",
  "consulting the rulebook…",
  "almost there…",
];

// needle bearing + label per verdict tier
const TIERS = {
  clear: { angle: 0, label: "clear" },
  advisory: { angle: 62, label: "heads up" },
  caution: { angle: 150, label: "caution" },
  high: { angle: 205, label: "high risk" },
  note: { angle: -55, label: "note" },
};

function sessionId() {
  let id = sessionStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem("session_id", id);
  }
  return id;
}

function timeAgo(ts) {
  const s = Math.round((Date.now() - ts) / 1000);
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  return `${h}h ago`;
}

function tickTimestamps() {
  document.querySelectorAll("[data-ts]").forEach((el) => {
    el.textContent = el.dataset.prefix + timeAgo(Number(el.dataset.ts));
  });
}
setInterval(tickTimestamps, 15000);

function sevClass(sev) {
  const s = (sev || "").toLowerCase();
  if (s.includes("high") || s.includes("severe") || s.includes("critical")) return "sev-high";
  if (s.includes("caution")) return "sev-caution";
  return "sev-advisory";
}

function tierFromSeverity(sev) {
  const s = (sev || "").toLowerCase();
  if (s.includes("high") || s.includes("severe") || s.includes("critical")) return "high";
  if (s.includes("caution")) return "caution";
  if (s.includes("advisory") || s.includes("watch")) return "advisory";
  return "clear";
}

/**
 * Splits the raw reply into prose + structured citation lines, and derives
 * a verdict tier from the primary citation's severity (or from the prose
 * itself when nothing was triggered — e.g. clarifying questions, failures).
 */
function parseResponse(text) {
  const lines = text.split("\n");
  const citeRe = /^(Source|Also):\s*(\S+)\s*\(([^)]+)\)\s*[—-]\s*(.+)$/i;
  const proseLines = [];
  const citations = [];
  for (const line of lines) {
    const m = line.match(citeRe);
    if (m) {
      citations.push({ kind: m[1], name: m[2], severity: m[3].trim(), desc: m[4].trim() });
    } else if (line.trim() !== "") {
      proseLines.push(line);
    }
  }
  const prose = proseLines.join("\n").trim();
  let tier = "clear";
  const notTriggered = /(within the safe range|no .*advisory applies|no .*advisory (is )?needed|safely within)/i.test(prose);
  if (citations.length && !notTriggered) {
    tier = tierFromSeverity(citations[0].severity);
  } else if (!citations.length && /(couldn.?t|could not|don.?t have|do not have|need a location|which city|try again)/i.test(text)) {
    tier = "note";
  }
  return { prose, citations, tier };
}

function setCompass(tier) {
  const t = TIERS[tier] || TIERS.clear;
  needle.setAttribute("class", `needle tier-${tier}`);
  needle.style.transform = `rotate(${t.angle}deg)`;
}

function buildCitationBlock(citations) {
  if (!citations.length) return null;
  const box = document.createElement("div");
  box.className = "citation";
  for (const c of citations) {
    const row = document.createElement("div");
    row.className = "citation-line";
    row.innerHTML = `
      <span class="citation-kind">${c.kind === "Source" ? "cited rule" : "also"}</span>
      <span class="citation-name">${c.name}</span>
      <span class="citation-sev ${sevClass(c.severity)}">${c.severity}</span>
    `;
    const desc = document.createElement("div");
    desc.className = "citation-desc";
    desc.textContent = c.desc;
    box.appendChild(row);
    box.appendChild(desc);
  }
  return box;
}

let assistantTurns = 0;

function addTurn(role, text, { withMeta = true, tier = null, citations = [] } = {}) {
  const row = document.createElement("div");
  let cls = `turn-row ${role}${tier ? ` tier-${tier}` : ""}`;
  if (role === "assistant") {
    assistantTurns += 1;
    if (assistantTurns % 2 === 0) cls += " alt";
  }
  row.className = cls;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.innerHTML = ICONS[role] || "";

  const wrap = document.createElement("div");
  wrap.className = "bubble-wrap";

  if (role === "assistant" && tier) {
    const tag = document.createElement("span");
    tag.className = `verdict-tag tier-${tier}`;
    tag.textContent = TIERS[tier].label;
    wrap.appendChild(tag);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  const citeBlock = buildCitationBlock(citations);
  if (citeBlock) bubble.appendChild(citeBlock);

  wrap.appendChild(bubble);

  if (withMeta && role !== "system") {
    const meta = document.createElement("div");
    meta.className = "meta";
    const ts = Date.now();
    const prefix = role === "user" ? "" : "weathervane · ";
    const tsSpan = document.createElement("span");
    tsSpan.dataset.ts = String(ts);
    tsSpan.dataset.prefix = prefix;
    tsSpan.textContent = prefix + "just now";
    meta.appendChild(tsSpan);

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "copy-btn";
    copyBtn.textContent = "copy";
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.textContent = "copied";
        copyBtn.classList.add("copied");
        setTimeout(() => {
          copyBtn.textContent = "copy";
          copyBtn.classList.remove("copied");
        }, 1200);
      } catch {
        /* clipboard unavailable — silently ignore */
      }
    });
    meta.appendChild(copyBtn);
    wrap.appendChild(meta);
  }

  row.appendChild(avatar);
  row.appendChild(wrap);
  scrollback.appendChild(row);
  scrollback.scrollTop = scrollback.scrollHeight;
  return row;
}

function addPending() {
  const row = document.createElement("div");
  row.className = "turn-row assistant pending";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.innerHTML = ICONS.assistant;

  const wrap = document.createElement("div");
  wrap.className = "bubble-wrap";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = `<span class="typing-dots"><span></span><span></span><span></span></span><span class="typing-phrase">${THINKING_PHRASES[0]}</span>`;
  wrap.appendChild(bubble);

  row.appendChild(avatar);
  row.appendChild(wrap);
  scrollback.appendChild(row);
  scrollback.scrollTop = scrollback.scrollHeight;

  const phraseEl = bubble.querySelector(".typing-phrase");
  let i = 0;
  const timer = setInterval(() => {
    i = (i + 1) % THINKING_PHRASES.length;
    phraseEl.textContent = THINKING_PHRASES[i];
  }, 1600);

  return { row, stop: () => clearInterval(timer) };
}

function setStatus(state) {
  if (state === "busy") {
    statusLabel.textContent = "checking…";
    statusDot.style.background = "var(--clay)";
    statusDot.style.boxShadow = "0 0 0 3px var(--clay-soft)";
  } else if (state === "error") {
    statusLabel.textContent = "connection trouble";
    statusDot.style.background = "var(--brick)";
    statusDot.style.boxShadow = "0 0 0 3px var(--brick-soft)";
  } else {
    statusLabel.textContent = "watching the sky";
    statusDot.style.background = "var(--sage)";
    statusDot.style.boxShadow = "0 0 0 3px var(--sage-soft)";
  }
}

addTurn(
  "system",
  'ask about outdoor activity safety for a given city — e.g. "is it safe to cycle in Denver today"',
  { withMeta: false }
);

chips.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  input.value = `is it safe to go ${chip.dataset.fill} today?`;
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
});

document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== input) {
    e.preventDefault();
    input.focus();
  }
});

// gentle rotating placeholder while the input is empty and idle
const EXAMPLE_PROMPTS = [
  "is it safe to cycle in Denver today?",
  "any UV risk running in Phoenix this afternoon?",
  "should we still do the picnic in Seattle?",
  "is Boulder too windy for a hike right now?",
];
let placeholderIdx = 0;
setInterval(() => {
  if (document.activeElement === input || input.value) return;
  placeholderIdx = (placeholderIdx + 1) % EXAMPLE_PROMPTS.length;
  input.setAttribute("placeholder", EXAMPLE_PROMPTS[placeholderIdx]);
}, 3400);

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = input.value.trim();
  if (!message) return;

  addTurn("user", message);
  input.value = "";
  input.disabled = true;
  sendBtn.disabled = true;
  sendBtn.classList.add("launch");
  setTimeout(() => sendBtn.classList.remove("launch"), 500);
  setStatus("busy");

  const pending = addPending();

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId(), message }),
    });
    if (!resp.ok) {
      throw new Error(`server returned ${resp.status}`);
    }
    const data = await resp.json();
    pending.stop();
    pending.row.remove();
    const { prose, citations, tier } = parseResponse(data.response);
    addTurn("assistant", prose || data.response, { tier, citations });
    setCompass(tier);
    setStatus("ok");
  } catch (err) {
    pending.stop();
    pending.row.remove();
    addTurn("system", `something went wrong talking to the backend: ${err.message}`);
    setStatus("error");
  } finally {
    input.disabled = false;
    sendBtn.disabled = false;
    input.focus();
  }
});
