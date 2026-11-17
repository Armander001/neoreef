// Transient status toast (#status).

let timer = null;

export function showStatus(msg, ms = 3000) {
  const el = document.getElementById("status");
  if (!el) return;
  el.textContent = msg;
  el.style.display = "block";
  clearTimeout(timer);
  timer = setTimeout(() => { el.style.display = "none"; }, ms);
}

export function setNote(containerId, text, { error = false } = {}) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = "";
  const span = document.createElement("span");
  span.className = "tb-note" + (error ? " error" : "");
  span.textContent = text;
  el.appendChild(span);
}
