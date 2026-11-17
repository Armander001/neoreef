// Toolbar building blocks: group labels, dividers and layer cards.

export function makeGroupLabel(text) {
  const g = document.createElement("div");
  g.className = "tb-group";
  const l = document.createElement("div");
  l.className = "tb-group-label";
  l.textContent = text;
  g.appendChild(l);
  return g;
}

export function makeDivider() {
  const d = document.createElement("div");
  d.className = "tb-divider";
  return d;
}

/**
 * A layer card: checkbox + name [+ tag] [+ fly button] + opacity slider.
 * @param {object} o
 * @param {string} o.name       display name
 * @param {string} o.id         DOM id for the checkbox
 * @param {boolean} [o.checked]
 * @param {boolean} [o.enabled] false renders a dimmed, non-interactive card
 * @param {string}  [o.tag]     small badge text
 * @param {string}  [o.tagClass] extra class for the badge (e.g. "coral", "warn")
 * @param {number}  [o.alpha]   initial opacity 0..1
 * @param {(checked:boolean)=>void} [o.onToggle]
 * @param {(alpha:number)=>void}    [o.onOpacity]
 * @param {()=>void}                [o.onFly]
 */
export function makeCard(o) {
  const enabled = o.enabled ?? true;
  const card = document.createElement("div");
  card.className = "layer-card" + (enabled ? "" : " dim");

  const top = document.createElement("div");
  top.className = "layer-card-top";

  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.id = o.id;
  cb.checked = enabled && (o.checked ?? true);
  cb.disabled = !enabled;
  if (o.onToggle) cb.addEventListener("change", () => o.onToggle(cb.checked));

  const lbl = document.createElement("label");
  lbl.htmlFor = o.id;
  lbl.className = "layer-name";
  lbl.title = o.name;
  lbl.textContent = o.name;
  top.append(cb, lbl);

  if (o.tag) {
    const tag = document.createElement("span");
    tag.className = "layer-tag" + (o.tagClass ? " " + o.tagClass : "");
    tag.textContent = o.tag;
    top.appendChild(tag);
  }
  if (o.onFly) {
    const fly = document.createElement("button");
    fly.className = "fly-btn";
    fly.textContent = "Fly";
    fly.title = "Fly to this layer";
    fly.addEventListener("click", o.onFly);
    top.appendChild(fly);
  }
  card.appendChild(top);

  if (enabled && o.onOpacity) {
    const bubble = document.createElement("div");
    bubble.className = "opacity-bubble";
    const opLbl = document.createElement("span");
    opLbl.className = "opacity-label";
    opLbl.textContent = "opacity";
    const slider = document.createElement("input");
    slider.type = "range";
    slider.className = "opacity-slider";
    slider.min = "0"; slider.max = "1"; slider.step = "0.05";
    slider.value = String(o.alpha ?? 1.0);
    slider.addEventListener("input", () => {
      o.onOpacity(Math.min(1, Math.max(0, parseFloat(slider.value))));
    });
    bubble.append(opLbl, slider);
    card.appendChild(bubble);
  }
  return card;
}

/** Appends a labelled group of cards to `container` (skips empty groups). */
export function appendGroup(container, label, cards) {
  if (!cards.length) return;
  container.appendChild(makeGroupLabel(label));
  cards.forEach(c => container.appendChild(c));
  container.appendChild(makeDivider());
}
