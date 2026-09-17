const scrollback = document.getElementById("scrollback");
const form = document.getElementById("composer");
const input = document.getElementById("input");

function sessionId() {
  let id = sessionStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem("session_id", id);
  }
  return id;
}

function addTurn(role, text) {
  const el = document.createElement("div");
  el.className = `turn ${role}`;
  el.textContent = text;
  scrollback.appendChild(el);
  scrollback.scrollTop = scrollback.scrollHeight;
  return el;
}

addTurn("system", "ask about outdoor activity safety for a given city, e.g. \"is it safe to cycle in Denver today\"");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = input.value.trim();
  if (!message) return;

  addTurn("user", message);
  input.value = "";
  input.disabled = true;

  const pending = addTurn("pending", "thinking...");

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
    pending.remove();
    addTurn("assistant", data.response);
  } catch (err) {
    pending.remove();
    addTurn("system", `something went wrong talking to the backend: ${err.message}`);
  } finally {
    input.disabled = false;
    input.focus();
  }
});
