/*
 * Smart Ventilation Card – wird mit der Integration ausgeliefert.
 *
 *   type: custom:smart-ventilation-card
 *   device: <Gerät eines Raums oder der Übersicht>   (empfohlen, per Editor wählbar)
 *   # alternativ: entity: sensor.schlafzimmer_empfehlung
 */
const DOMAIN = "smart_ventilation";

const STATUS = {
  running: { icon: "mdi:window-open-variant", color: "var(--info-color, #039be5)" },
  cold: { icon: "mdi:snowflake-alert", color: "var(--info-color, #039be5)" },
  due: { icon: "mdi:air-filter", color: "var(--warning-color, #ffa600)" },
  blocked: { icon: "mdi:window-closed-variant", color: "var(--secondary-text-color)" },
  ok: { icon: "mdi:check-circle-outline", color: "var(--success-color, #43a047)" },
};
const RISK_COLOR = {
  hoch: "var(--error-color, #db4437)",
  "erhöht": "var(--warning-color, #ffa600)",
  niedrig: "var(--success-color, #43a047)",
};

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, unit = "", digits = 1) =>
  v === null || v === undefined ? "–" : `${Number(v).toLocaleString("de-DE", { maximumFractionDigits: digits })}${unit}`;
const duration = (s) => {
  s = Math.max(0, Math.round(s || 0));
  const m = Math.floor(s / 60), sec = s % 60;
  return m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")} h` : `${m}:${String(sec).padStart(2, "0")} min`;
};

/* Kleine Verlaufskurve: Feuchte (Linie) und Temperatur (gestrichelt) über die Lüftungsdauer */
function sparkline(trace) {
  const pts = (trace?.punkte || []).filter((p) => p[1] !== null && p[1] !== undefined);
  if (pts.length < 2) return "";
  const W = 300, H = 56, P = 4;
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0] || 1;
  const line = (idx) => {
    const vals = pts.map((p) => p[idx]).filter((v) => v !== null && v !== undefined);
    if (vals.length < 2) return "";
    const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
    return pts
      .filter((p) => p[idx] !== null && p[idx] !== undefined)
      .map((p, i) => `${i ? "L" : "M"}${(P + ((p[0] - t0) / (t1 - t0 || 1)) * (W - 2 * P)).toFixed(1)},${(P + (1 - (p[idx] - lo) / span) * (H - 2 * P)).toFixed(1)}`)
      .join(" ");
  };
  const first = pts[0], last = pts[pts.length - 1];
  const label = trace.laeuft ? "Laufende Lüftung" : "Letzte Lüftung";
  return `
    <div class="trace">
      <div class="trace-head"><span>${label} · ${duration(last[0] - first[0])}</span>
        <span>${num(first[1], "")} → <b>${num(last[1], " g/m³")}</b>${first[2] != null && last[2] != null ? ` · ${num(first[2], "")} → ${num(last[2], " °C")}` : ""}</span></div>
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${label}">
        <path d="${line(2)}" class="t"/><path d="${line(1)}" class="h"/>
      </svg>
    </div>`;
}

class SmartVentilationCard extends HTMLElement {
  static getConfigForm() {
    return {
      schema: [{ name: "device", required: true, selector: { device: { filter: { integration: DOMAIN } } } }],
      computeLabel: () => "Raum oder Übersicht",
    };
  }

  static getStubConfig(hass) {
    const id = Object.keys(hass.states).find((e) => hass.states[e].attributes?.karte);
    return id ? { entity: id } : {};
  }

  setConfig(config) {
    if (!config || (!config.device && !config.entity)) {
      throw new Error("Bitte einen Raum (device) oder eine Entität (entity) auswählen");
    }
    this._config = config;
    this._last = undefined;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    const entityId = this._findEntity();
    const state = entityId ? hass.states[entityId] : undefined;
    const key = state ? JSON.stringify([state.attributes.karte, state.attributes.raeume, state.state]) : "none";
    if (key === this._last) return; // nur neu zeichnen, wenn sich etwas geändert hat
    this._last = key;
    this._entityId = entityId;
    this._render(state);
  }

  getCardSize() {
    return 4;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _findEntity() {
    const { entity, device } = this._config;
    if (entity) return entity;
    const entities = this._hass.entities || {};
    // Raum: Empfehlungs-Sensor (hat "karte"); Übersicht: Sensor mit "raeume"
    const candidates = Object.keys(entities).filter((e) => entities[e].device_id === device);
    return (
      candidates.find((e) => this._hass.states[e]?.attributes?.karte) ||
      candidates.find((e) => e.startsWith("sensor.") && this._hass.states[e]?.attributes?.raeume)
    );
  }

  _moreInfo() {
    if (!this._entityId) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: this._entityId } }));
  }

  _render(state) {
    let body;
    if (!state) {
      body = `<div class="empty">Kein Smart-Ventilation-Raum gefunden.</div>`;
    } else if (state.attributes.karte) {
      body = this._room(state.attributes.karte);
    } else {
      body = this._overview(state);
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>${body}</ha-card>`;
    this.shadowRoot.querySelector(".tap")?.addEventListener("click", () => this._moreInfo());
  }

  _room(k) {
    let st = STATUS.ok;
    if (k.grund === "Kühlen" && k.minuten > 0) st = { icon: "mdi:snowflake-thermometer", color: STATUS.running.color };
    if (k.nach_dusche && !k.laeuft) st = { icon: "mdi:shower", color: STATUS.due.color };
    if (k.kuehlt_aus) st = STATUS.cold;
    else if (k.laeuft) st = STATUS.running;
    else if (k.minuten > 0) st = STATUS.due;
    else if (k.blockiert) st = STATUS.blocked;

    const season = k.saison === "winter" ? "mdi:snowflake" : "mdi:white-balance-sunny";
    let headline = k.status;
    if (k.laeuft) {
      headline = `${k.querlueften ? "Querlüften" : "Lüftung läuft"} · ${duration(k.dauer_s)}`;
    }

    const bar = k.laeuft
      ? `<div class="bar"><div style="width:${Math.min(100, k.fortschritt || 0)}%"></div></div>
         <div class="sub">${k.fortschritt || 0} % des Feuchteunterschieds abgebaut</div>`
      : k.blockiert
        ? `<div class="sub">${esc(k.blockiert)}</div>`
        : "";

    const warn = k.kuehlt_aus
      ? `<div class="warn"><ha-icon icon="mdi:thermometer-alert"></ha-icon>Raum kühlt aus – ${num(k.innen_t, " °C")}. Fenster schließen.</div>`
      : "";

    const co2 = k.co2 !== null && k.co2 !== undefined
      ? `<div class="cell"><span>CO₂</span><b>${num(k.co2, " ppm", 0)}</b><small>${esc(k.luft || "")}</small></div>`
      : "";

    const chips = [
      k.bester_zeitpunkt ? `<span class="chip"><ha-icon icon="mdi:clock-check-outline"></ha-icon>${esc(k.bester_zeitpunkt)}</span>` : "",
      `<span class="chip ${k.gelueftet ? "good" : ""}"><ha-icon icon="${k.gelueftet ? "mdi:check" : "mdi:calendar-clock"}"></ha-icon>` +
        `${k.heute_anzahl}× heute · ${num(k.heute_min, " Min.", 0)}</span>`,
      k.heute_kwh > 0 ? `<span class="chip"><ha-icon icon="mdi:fire"></ha-icon>${num(k.heute_kwh, " kWh", 2)} · ${num(k.heute_eur, " €", 2)}</span>` : "",
      k.ruhezeit ? `<span class="chip"><ha-icon icon="mdi:sleep"></ha-icon>Ruhezeit</span>` : "",
      k.kuehlen_plan ? `<span class="chip"><ha-icon icon="mdi:weather-night"></ha-icon>Kühlen: ${esc(k.kuehlen_plan)}</span>` : "",
      k.nach_dusche ? `<span class="chip warn-chip"><ha-icon icon="mdi:shower"></ha-icon>Nach dem Duschen</span>` : "",
      k.urlaub ? `<span class="chip"><ha-icon icon="mdi:palm-tree"></ha-icon>Urlaub</span>` : "",
      k.entfeuchter ? `<span class="chip"><ha-icon icon="mdi:air-humidifier"></ha-icon>Entfeuchter läuft</span>` : "",
    ].join("");

    return `
      <div class="tap">
        <div class="head">
          <div class="badge" style="color:${st.color}"><ha-icon icon="${st.icon}"></ha-icon></div>
          <div class="title">
            <div class="name">${esc(k.name)} <ha-icon class="season" icon="${season}"></ha-icon></div>
            <div class="status">${esc(headline)}</div>
          </div>
        </div>
        ${bar}${warn}
        <div class="grid">
          <div class="cell"><span>Innen</span><b>${num(k.innen_t, " °C")}</b><small>${num(k.innen_ah, " g/m³")} · ${num(k.innen_rh, " %", 0)}</small></div>
          <div class="cell"><span>Außen</span><b>${num(k.aussen_t, " °C")}</b><small>${num(k.aussen_ah, " g/m³")}</small></div>
          <div class="cell"><span>Wand</span><b>${num(k.wand_t, " °C")}</b>
            <small style="color:${RISK_COLOR[k.schimmel] || "inherit"}">${num(k.wand_rh, " %", 0)} · ${esc(k.schimmel)}</small></div>
          ${co2}
        </div>
        ${sparkline(k.verlauf)}
        <div class="chips">${chips}</div>
      </div>`;
  }

  _overview(state) {
    const rooms = state.attributes.raeume || [];
    const rows = rooms
      .map((r) => {
        const icon = r.laeuft ? "mdi:window-open-variant" : r.lueften ? "mdi:air-filter" : "mdi:check-circle-outline";
        const color = r.laeuft ? STATUS.running.color : r.lueften ? STATUS.due.color : STATUS.ok.color;
        return `<div class="row"><ha-icon style="color:${color}" icon="${icon}"></ha-icon>
          <div class="rname">${esc(r.raum)}</div><div class="rstate">${esc(r.laeuft ? "läuft" : r.empfehlung)}</div></div>`;
      })
      .join("");
    const needing = rooms.filter((r) => r.lueften).length;
    return `
      <div class="tap">
        <div class="head">
          <div class="badge" style="color:${needing ? STATUS.due.color : STATUS.ok.color}">
            <ha-icon icon="${needing ? "mdi:home-alert-outline" : "mdi:home-heart"}"></ha-icon></div>
          <div class="title"><div class="name">Lüften</div>
            <div class="status">${needing ? `${needing} ${needing === 1 ? "Raum" : "Räume"} lüften` : "Alle Räume ok"}</div></div>
        </div>
        <div class="rows">${rows || '<div class="empty">Noch keine Räume eingerichtet.</div>'}</div>
      </div>`;
  }
}

const STYLE = `
  ha-card { padding: 16px; }
  .tap { cursor: pointer; }
  .head { display: flex; align-items: center; gap: 12px; }
  .badge { width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center;
           background: color-mix(in srgb, currentColor 15%, transparent); flex: none; }
  .name { font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
  .season { --mdc-icon-size: 16px; color: var(--secondary-text-color); }
  .status { color: var(--primary-text-color); font-size: 14px; margin-top: 2px; }
  .sub { color: var(--secondary-text-color); font-size: 12px; margin-top: 6px; }
  .bar { height: 6px; border-radius: 3px; background: var(--divider-color); margin-top: 12px; overflow: hidden; }
  .bar div { height: 100%; background: var(--info-color, #039be5); transition: width .5s; }
  .warn { display: flex; gap: 8px; align-items: center; margin-top: 12px; padding: 8px 10px; border-radius: 8px;
          color: var(--error-color, #db4437); background: color-mix(in srgb, var(--error-color, #db4437) 12%, transparent); font-size: 13px; }
  .warn ha-icon { --mdc-icon-size: 18px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(90px, 1fr)); gap: 8px; margin-top: 14px; }
  .cell { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: 10px;
          background: color-mix(in srgb, var(--primary-text-color) 5%, transparent); }
  .cell span { font-size: 11px; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .04em; }
  .cell b { font-size: 16px; font-weight: 600; }
  .cell small { font-size: 12px; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .cell b { white-space: nowrap; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
  .chip { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; padding: 4px 10px; border-radius: 999px;
          background: color-mix(in srgb, var(--primary-text-color) 7%, transparent); color: var(--secondary-text-color); }
  .chip ha-icon { --mdc-icon-size: 14px; }
  .chip.good { color: var(--success-color, #43a047); }
  .rows { margin-top: 10px; display: flex; flex-direction: column; }
  .row { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-top: 1px solid var(--divider-color); }
  .row ha-icon { --mdc-icon-size: 20px; flex: none; }
  .rname { font-weight: 500; flex: none; min-width: 90px; }
  .rstate { color: var(--secondary-text-color); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .empty { color: var(--secondary-text-color); padding: 8px 0; }
  .chip.warn-chip { color: var(--warning-color, #ffa600); }
  .trace { margin-top: 12px; }
  .trace-head { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; color: var(--secondary-text-color); }
  .trace-head b { color: var(--primary-text-color); font-weight: 600; }
  .trace svg { width: 100%; height: 56px; display: block; margin-top: 4px; }
  .trace path { fill: none; stroke-width: 2; vector-effect: non-scaling-stroke; stroke-linejoin: round; stroke-linecap: round; }
  .trace path.h { stroke: var(--info-color, #039be5); }
  .trace path.t { stroke: var(--secondary-text-color); stroke-dasharray: 4 3; opacity: .6; }
`;

if (!customElements.get("smart-ventilation-card")) {
  customElements.define("smart-ventilation-card", SmartVentilationCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "smart-ventilation-card",
    name: "Smart Ventilation",
    description: "Lüftungsstatus, Werte und Statistik eines Raums – oder die Übersicht aller Räume.",
    preview: true,
  });
}
