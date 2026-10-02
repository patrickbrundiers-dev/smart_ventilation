/*
 * Smart Ventilation Card – wird mit der Integration ausgeliefert.
 *
 *   type: custom:smart-ventilation-card
 *   device: <Gerät eines Raums oder der Übersicht>   (im Editor wählbar)
 *   # alternativ: entity: sensor.schlafzimmer_empfehlung
 *   show_details: true    # Kacheln Innen/Außen/Wand/CO₂
 *   show_chart: true      # Verlauf der letzten Lüftung
 *
 * Nutzt ausschließlich Design-Variablen des aktiven Home-Assistant-Themes.
 */
const DOMAIN = "smart_ventilation";
const LOCALE = "de-DE";

/* ---------- Hilfen ---------- */
const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const has = (v) => v !== null && v !== undefined && v !== "" && Number.isFinite(Number(v));
const fmt = (v, digits = 1) =>
  has(v) ? Number(v).toLocaleString(LOCALE, { minimumFractionDigits: 0, maximumFractionDigits: digits }) : "–";
const dur = (s) => {
  s = Math.max(0, Math.round(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")} h` : `${m}:${String(sec).padStart(2, "0")} min`;
};
const ago = (iso) => {
  if (!iso) return "";
  const diff = (Date.parse(iso) - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat("de", { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
};
const join = (parts) => parts.filter(Boolean).join(" · ");
let UID = 0;

/* Ein Chip statt zwei getrennter für Wärmeverlust und Vorheiz-Ersparnis: zeigt die Netto-Bilanz,
   die Aufschlüsselung steht im Titel-Tooltip. Mit "toggle" statt Entität wird kein More-Info-Dialog
   geöffnet, sondern ein lokales Klapp-Panel umgeschaltet (siehe [data-toggle] in _render). */
function renderChip([ent, icon, text, tone, title, toggle, expanded, press]) {
  const t = title ? ` title="${esc(title)}"` : "";
  if (toggle) {
    const caret = `<ha-icon class="chip-caret" icon="${expanded ? "mdi:chevron-up" : "mdi:chevron-down"}"></ha-icon>`;
    return `<button class="chip ${tone ? `tone-${tone}` : ""}" data-toggle="${esc(toggle)}" aria-expanded="${!!expanded}"${t}><ha-icon icon="${icon}"></ha-icon>${esc(text)}${caret}</button>`;
  }
  if (ent && press) {
    return `<button class="chip ${tone ? `tone-${tone}` : ""}" data-entity="${esc(ent)}" data-press="1"${t}><ha-icon icon="${icon}"></ha-icon>${esc(text)}</button>`;
  }
  return ent
    ? `<button class="chip ${tone ? `tone-${tone}` : ""}" data-entity="${esc(ent)}"${t}><ha-icon icon="${icon}"></ha-icon>${esc(text)}</button>`
    : `<span class="chip ${tone ? `tone-${tone}` : ""}"${t}><ha-icon icon="${icon}"></ha-icon>${esc(text)}</span>`;
}

/* ---------- Aufklappbare Statistik (Woche/Monat/Gesamt) unter dem "heute"-Chip ---------- */
function statsPanel(stats) {
  if (!stats) return "";
  const rows = [
    ["Woche", stats.woche],
    ["Monat", stats.monat],
    ["Gesamt", stats.gesamt],
  ];
  return `<div class="breakdown">${rows
    .map(([label, s]) => {
      if (!s) return "";
      const netKwh = (s.kwh || 0) - (s.kwh_gespart || 0);
      const netEur = (s.cost || 0) - (s.kosten_gespart || 0);
      const good = netKwh < -0.004;
      const netText = good
        ? `−${fmt(-netKwh, 2)} kWh · −${fmt(-netEur, 2)} €`
        : `${fmt(netKwh, 2)} kWh · ${fmt(netEur, 2)} €`;
      const durText = s.minutes >= 60 ? `${fmt(s.minutes / 60, 1)} h` : `${fmt(s.minutes, 0)} Min.`;
      return `<div class="breakdown-row"><span>${label} · ${s.count}× · ${durText}</span><span class="${good ? "tone-good" : ""}">${netText}</span></div>`;
    })
    .join("")}</div>`;
}

function costChip(entity, kwh, eur, kwhSaved, eurSaved) {
  if (!(kwh > 0) && !(kwhSaved > 0)) return null;
  const netKwh = kwh - kwhSaved, netEur = eur - eurSaved;
  const detail = join([kwh > 0 && `Wärmeverlust ${fmt(kwh, 2)} kWh`, kwhSaved > 0 && `Vorheizen −${fmt(kwhSaved, 2)} kWh`]);
  if (netKwh > 0.004) {
    return [entity, "mdi:fire", `${fmt(netKwh, 2)} kWh · ${fmt(netEur, 2)} €`, null, detail];
  }
  return [entity, "mdi:piggy-bank-outline", `Netto ${fmt(-netKwh, 2)} kWh gespart · ${fmt(-netEur, 2)} €`, "good", detail];
}

/* ---------- 7-Tage-Sparkline (Lüftungshäufigkeit, Tooltip mit Kosten) ---------- */
function trendChart(days) {
  if (!days || days.length < 2) return "";
  const max = Math.max(1, ...days.map((d) => d.anzahl || 0));
  const bars = days
    .map((d, i) => {
      const count = Number(d.anzahl) || 0;
      const minutes = Number(d.minuten) || 0;
      const pct = count > 0 ? Math.max(10, Math.round((count / max) * 100)) : 0;
      const isToday = i === days.length - 1;
      const date = new Date(`${d.datum}T00:00:00`);
      const wd = date.toLocaleDateString(LOCALE, { weekday: "short" });
      const day = date.toLocaleDateString(LOCALE, { day: "2-digit", month: "2-digit" });
      const title = `${wd}, ${day}: ${count}× · ${minutes} Min.${has(d.kwh) ? ` · ${fmt(d.kwh, 2)} kWh` : ""}`;
      return `
        <span class="trend-day${isToday ? " is-today" : ""}" title="${esc(title)}" aria-label="${esc(title)}">
          <span class="trend-bar" style="--h:${pct}%"></span>
          <span class="trend-count">${count}×</span>
          <span class="trend-min">${minutes} Min.</span>
        </span>`;
    })
    .join("");
  return `
    <div class="trend trend-detailed">
      <span class="trend-label">Letzte 7 Tage</span>
      <div class="trend-bars" role="list" aria-label="Lüftungen und Minuten der letzten 7 Tage">${bars}</div>
    </div>`;
}

/* ---------- Jahresvergleich (Balkendiagramm über die letzten Monate) ---------- */
function yearChart(months) {
  if (!months || months.length < 2) return "";
  const max = Math.max(1, ...months.map((m) => m.bedarf_h || 0));
  const bars = months
    .map((m, i) => {
      const pct = m.bedarf_h > 0 ? Math.max(6, Math.round((m.bedarf_h / max) * 100)) : 0;
      const isLast = i === months.length - 1;
      const title = `${m.monat}: ${fmt(m.bedarf_h, 1)} h Bedarf${has(m.kwh) ? ` · ${fmt(m.kwh, 1)} kWh` : ""}`;
      return `<span class="trend-bar year-bar${isLast ? " is-today" : ""}" style="--h:${pct}%" title="${esc(title)}"></span>`;
    })
    .join("");
  return `<div class="trend"><span class="trend-label">Letzte ${months.length} Monate</span><div class="trend-bars">${bars}</div></div>`;
}

/* ---------- Fensterstatus (bei mehr als einem Fensterkontakt) ---------- */
function windowStatus(windows) {
  if (!windows || windows.length < 2) return "";
  const items = windows
    .map(
      (w) =>
        `<span class="win-item ${w.offen ? "tone-warn" : "tone-good"}"><ha-icon icon="${w.offen ? "mdi:window-open-variant" : "mdi:window-closed-variant"}"></ha-icon>${esc(w.name)}</span>`
    )
    .join("");
  return `<div class="win-list">${items}</div>`;
}

/* ---------- Umschaltbare Sortierung der Übersicht ---------- */
const SORT_MODES = [
  { key: "dringlichkeit", icon: "mdi:sort-variant", label: "Nach Dringlichkeit" },
  { key: "kosten", icon: "mdi:currency-eur", label: "Nach Kosten heute" },
  { key: "schimmel", icon: "mdi:shield-alert-outline", label: "Nach Schimmelrisiko" },
];
const RISK_RANK = { hoch: 2, "erhöht": 1, niedrig: 0 };

function sortRooms(rooms, mode) {
  if (mode === "kosten") {
    return [...rooms].sort((a, b) => (b.heute_eur_netto || 0) - (a.heute_eur_netto || 0));
  }
  if (mode === "schimmel") {
    return [...rooms].sort(
      (a, b) => (RISK_RANK[b.schimmelrisiko] ?? -1) - (RISK_RANK[a.schimmelrisiko] ?? -1) || b.dringlichkeit - a.dringlichkeit
    );
  }
  return rooms; // vom Backend bereits nach Dringlichkeit sortiert
}

/* ---------- Sammel-Warnung oben auf der Übersichtskarte ---------- */
function overviewAlerts(rooms) {
  const mold = rooms.filter((r) => (RISK[r.schimmelrisiko] || [])[0] !== "good" && RISK[r.schimmelrisiko]).length;
  const air = rooms.filter((r) => r.luft === "schlecht").length;
  const shutters = rooms.filter((r) => r.rollo_empfehlung && !r.rollo_geschlossen).length;
  const parts = [];
  if (mold) parts.push(`${mold} Schimmelrisiko`);
  if (air) parts.push(`${air}× CO₂ hoch`);
  if (shutters) parts.push(`${shutters}× Rollo schließen`);
  return parts;
}

/* ---------- Aufschlüsselung des Übersicht-Netto-Chips nach Raum ---------- */
function breakdownList(rooms) {
  const relevant = rooms.filter((r) => Math.abs(r.heute_eur_netto || 0) >= 0.01 || Math.abs(r.heute_kwh_netto || 0) >= 0.01);
  if (!relevant.length) {
    return `<div class="breakdown-empty">Noch keine nennenswerten Kosten oder Ersparnisse heute.</div>`;
  }
  return [...relevant]
    .sort((a, b) => Math.abs(b.heute_eur_netto || 0) - Math.abs(a.heute_eur_netto || 0))
    .map((r) => {
      const net = r.heute_eur_netto || 0;
      const good = net <= -0.004;
      return `<div class="breakdown-row"><span>${esc(r.raum)}</span><span class="${good ? "tone-good" : ""}">${good ? "−" : ""}${fmt(Math.abs(net), 2)} €</span></div>`;
    })
    .join("");
}

/* ---------- Status eines Raums ---------- */
function roomState(k) {
  if (k.laeuft && k.kuehlt_aus) return { tone: "bad", icon: "mdi:snowflake-alert", pill: "Kühlt aus" };
  if (k.laeuft) return { tone: "info", icon: "mdi:window-open-variant", pill: "Läuft", pulse: true };
  if (k.minuten > 0 && k.grund === "Kühlen") return { tone: "info", icon: "mdi:snowflake-thermometer", pill: "Kühlen" };
  if (k.minuten > 0 && k.grund === "Vorheizen") return { tone: "info", icon: "mdi:thermometer-chevron-up", pill: "Vorheizen" };
  if (k.minuten > 0 && k.pausiert) return { tone: "neutral", icon: "mdi:pause-circle-outline", pill: "Pausiert" };
  if (k.nach_dusche && k.minuten > 0) return { tone: "warn", icon: "mdi:shower-head", pill: "Lüften" };
  if (k.minuten > 0) return { tone: "warn", icon: "mdi:window-open-variant", pill: "Lüften" };
  if (k.blockiert) return { tone: "neutral", icon: "mdi:window-closed-variant", pill: "Gesperrt" };
  if (k.status === "Sensordaten fehlen") return { tone: "neutral", icon: "mdi:alert-circle-outline", pill: "Keine Daten" };
  return { tone: "good", icon: "mdi:check-circle-outline", pill: "Gut" };
}

function headline(k) {
  const reason = k.grund ? `wegen ${k.grund.replace(" + ", " und ")}` : "";
  const decision = k.entscheidungsgrund ? `${k.entscheidungsgrund}${Number.isFinite(k.entscheidungs_score) ? ` · Score ${k.entscheidungs_score}` : ""}` : "";
  if (k.laeuft) {
    return { title: k.querlueften ? "Querlüften läuft" : "Lüftung läuft", sub: join([k.kuehlt_aus ? "Bitte Fenster schließen" : "", k.rest_minuten > 0 && `noch ca. ${k.rest_minuten} Min.`]) };
  }
  if (k.minuten > 0 && k.grund === "Kühlen") {
    return { title: "Jetzt abkühlen", sub: join([`Fenster auf, ca. ${k.minuten} Min.`, k.kuehlen_plan && `Nacht: ${k.kuehlen_plan}`]) };
  }
  if (k.minuten > 0 && k.grund === "Vorheizen") {
    return { title: "Jetzt vorheizen", sub: join([`Fenster auf, ca. ${k.minuten} Min.`, k.vorheizen_plan && `Warm: ${k.vorheizen_plan}`]) };
  }
  if (k.minuten > 0 && k.pausiert) {
    const mode = String(k.modus || "Lüften").replace(" (Querlüften)", "");
    return { title: k.pausiert, sub: join([`Später: ${mode}`, `ca. ${k.minuten} Min.`, reason]) };
  }
  if (k.minuten > 0) {
    const cross = String(k.modus || "").includes("Querlüften");
    const mode = String(k.modus || "Lüften").replace(" (Querlüften)", "");
    return {
      title: k.nach_dusche ? "Nach dem Duschen lüften" : mode,
      sub: join([`ca. ${k.minuten} Min.`, cross && "alle Fenster öffnen", reason, decision]),
    };
  }
  if (k.blockiert) return { title: "Gerade nicht lüften", sub: join([k.blockiert, decision]) };
  if (k.status === "Sensordaten fehlen") return { title: "Sensordaten fehlen", sub: "Einstellungen und Reparaturen prüfen" };
  return { title: "Raumklima in Ordnung", sub: k.gelueftet ? "Heute schon ausreichend gelüftet" : "Kein Lüften nötig" };
}

const RISK = { hoch: ["bad", "hoch"], "erhöht": ["warn", "erhöht"], niedrig: ["good", "niedrig"] };
const AIR = { schlecht: "bad", "mäßig": "warn", gut: "good" };

/* ---------- Karte ---------- */
class SmartVentilationCard extends HTMLElement {
  static getConfigForm() {
    return {
      schema: [
        { name: "device", required: true, selector: { device: { filter: { integration: DOMAIN } } } },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "show_details", default: true, selector: { boolean: {} } },
            { name: "show_chart", default: true, selector: { boolean: {} } },
            { name: "show_trend", default: true, selector: { boolean: {} } },
            { name: "show_year", default: true, selector: { boolean: {} } },
            { name: "compact", default: false, selector: { boolean: {} } },
          ],
        },
      ],
      computeLabel: (s) =>
        ({
          device: "Raum oder Übersicht",
          show_details: "Messwerte anzeigen",
          show_chart: "Verlauf anzeigen",
          show_trend: "7-Tage-Trend anzeigen",
          show_year: "Jahresvergleich anzeigen",
          compact: "Kompaktmodus (nur das Wichtigste)",
        }[s.name]),
      computeHelper: (s) =>
        s.name === "device" ? "Ein Raum zeigt Status und Messwerte, die Übersicht alle Räume." : undefined,
    };
  }

  constructor() {
    super();
    this._overviewSort = "dringlichkeit";
    this._overviewExpanded = false;
    this._roomStatsExpanded = false;
  }

  static getStubConfig(hass) {
    try {
      const states = hass?.states || {};
      const id = Object.keys(states).find((e) => states[e]?.attributes?.karte);
      const device = id && hass?.entities?.[id]?.device_id;
      return device ? { device } : id ? { entity: id } : { device: "" };
    } catch (err) {
      console.error("smart-ventilation-card getStubConfig", err);
      return { device: "" };
    }
  }

  setConfig(config) {
    // Keine Ausnahme werfen: ohne Auswahl einen Hinweis zeigen (sonst bleibt die Vorschau leer)
    this._config = {
      show_details: true, show_chart: true, show_trend: true, show_year: true, compact: false,
      ...(config || {}),
    };
    this._uid = `sv${++UID}`;
    this._last = undefined;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    if (this._hass) this.hass = this._hass;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config || !hass) return;
    try {
      const entityId = this._findEntity();
      const state = entityId ? hass.states?.[entityId] : undefined;
      const key = state
        ? JSON.stringify([state.attributes?.karte, state.attributes?.raeume, state.attributes?.summe, state.attributes?.trend_tage, state.state])
        : "none";
      if (key === this._last) return;
      this._last = key;
      this._entityId = entityId;
      this._render(state);
    } catch (err) {
      // Fehler sichtbar machen statt einer leeren Fläche
      console.error("smart-ventilation-card", err);
      this._last = undefined;
      this._showError(err);
    }
  }

  _showError(err) {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const msg = `${err?.name || "Fehler"}: ${err?.message || err}`;
    const where = String(err?.stack || "").split("\n").slice(1, 3).map((l) => l.trim()).join(" | ");
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><div class="alert tone-bad">
      <ha-icon icon="mdi:alert-circle-outline"></ha-icon><div><b>Smart Ventilation: Karte konnte nicht angezeigt werden</b>
      <span>${esc(msg)}</span><span class="err-where">${esc(where)}</span></div></div></ha-card>`;
  }

  getCardSize() {
    if (this._config?.compact) return 2;
    return this._config?.show_chart ? 6 : 4;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _findEntity() {
    const { entity, device } = this._config;
    if (entity) return entity;
    if (!device) return undefined;
    const entities = this._hass.entities || {};
    const own = Object.keys(entities).filter((e) => entities[e].device_id === device);
    return (
      own.find((e) => this._hass.states[e]?.attributes?.karte) ||
      own.find((e) => e.startsWith("sensor.") && this._hass.states[e]?.attributes?.raeume)
    );
  }

  _moreInfo(entityId) {
    if (!entityId) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId } }));
  }

  _render(state) {
    let body;
    this._chartData = null;
    this._lastState = state;
    if (!state) {
      const chosen = this._config.device || this._config.entity;
      body = `<div class="empty"><ha-icon icon="mdi:home-search-outline"></ha-icon>
        <div><b>${chosen ? "Raum nicht gefunden" : "Raum auswählen"}</b><span>${chosen
          ? "Das gewählte Gerät liefert keine Daten – ist die Integration geladen?"
          : "Im Karten-Editor einen Raum oder die Übersicht auswählen."}</span></div></div>`;
    } else if (state.attributes.karte) {
      body = this._room(state.attributes.karte);
    } else {
      body = this._overview(state.attributes.raeume || [], state.attributes.summe || {}, state.attributes.trend_tage || []);
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>${body}</ha-card>`;
    this.shadowRoot.querySelectorAll("[data-entity]:not([data-press])").forEach((el) => {
      const open = (ev) => {
        ev.stopPropagation();
        this._moreInfo(el.dataset.entity || this._entityId);
      };
      el.addEventListener("click", open);
      el.addEventListener("keydown", (ev) => (ev.key === "Enter" || ev.key === " ") && open(ev));
    });
    this.shadowRoot.querySelectorAll("[data-press]").forEach((el) => {
      const press = (ev) => {
        ev.stopPropagation();
        this._press(el.dataset.entity);
      };
      el.addEventListener("click", press);
      el.addEventListener("keydown", (ev) => (ev.key === "Enter" || ev.key === " ") && press(ev));
    });
    // Rein clientseitige Umschalter (Sortierung, Aufschlüsselung aufklappen) - kein Service-Call,
    // nur ein Re-Render mit demselben, zuletzt empfangenen Zustand.
    this.shadowRoot.querySelectorAll("[data-sort]").forEach((el) => {
      const pick = (ev) => {
        ev.stopPropagation();
        this._overviewSort = el.dataset.sort;
        this._render(this._lastState);
      };
      el.addEventListener("click", pick);
      el.addEventListener("keydown", (ev) => (ev.key === "Enter" || ev.key === " ") && pick(ev));
    });
    this.shadowRoot.querySelectorAll("[data-toggle]").forEach((el) => {
      const toggle = (ev) => {
        ev.stopPropagation();
        if (el.dataset.toggle === "breakdown") this._overviewExpanded = !this._overviewExpanded;
        else if (el.dataset.toggle === "stats") this._roomStatsExpanded = !this._roomStatsExpanded;
        this._render(this._lastState);
      };
      el.addEventListener("click", toggle);
      el.addEventListener("keydown", (ev) => (ev.key === "Enter" || ev.key === " ") && toggle(ev));
    });
    this._bindChart();
  }

  _press(entityId) {
    if (!entityId || !this._hass) return;
    this._hass.callService("button", "press", { entity_id: entityId }).catch((err) => console.error("smart-ventilation-card", err));
  }

  /* ---------- Raum ---------- */
  _room(k) {
    const st = roomState(k);
    const h = headline(k);
    const e = k.entitaeten || {};
    const season = k.saison === "winter" ? ["mdi:snowflake", "Winter"] : ["mdi:white-balance-sunny", "Sommer"];
    const windows = k.fenster_anzahl > 1 ? `${k.fenster_anzahl} Fenster` : "";

    const progress = k.laeuft
      ? `<div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${k.fortschritt || 0}"
             aria-label="Feuchteabbau ${k.fortschritt || 0} Prozent">
           <div class="progress-row"><span>${k.fortschritt || 0} % Feuchte abgebaut</span><span>${dur(k.dauer_s)}</span></div>
           <div class="track"><div class="fill" style="width:${Math.min(100, k.fortschritt || 0)}%"></div></div>
         </div>`
      : "";

    const alerts = [];
    if (k.laeuft && k.heizung_ab && k.heizung_ab.length) {
      alerts.push(["info", "mdi:radiator-off", "Heizung abgesenkt", `${k.heizung_ab.join(", ")} – wird nach dem Lüften wiederhergestellt.`]);
    }
    if (k.laeuft && k.heizung_extern && k.heizung_extern.length) {
      alerts.push(["info", "mdi:radiator-off", "Heizung wird selbst geregelt", `${k.heizung_extern.join(", ")} schaltet beim Fenster öffnen automatisch ab.`]);
    }
    if (k.kuehlt_aus) alerts.push(["bad", "mdi:thermometer-alert", "Raum kühlt aus", `${fmt(k.innen_t)} °C – bitte Fenster schließen.`]);
    if (k.schimmel_tage >= 3) alerts.push(["bad", "mdi:alert-octagon-outline", "Schimmelgefahr", `Die Wand war ${k.schimmel_tage} Tage in Folge kritisch feucht.`]);
    else if (k.schimmel_tage === 2) alerts.push(["warn", "mdi:shield-alert-outline", "Wand zwei Tage feucht", "Morgen droht eine Schimmelwarnung – heute gründlich lüften."]);
    if (k.nach_dusche && !k.laeuft) alerts.push(["warn", "mdi:shower-head", "Nach dem Duschen", "Jetzt lüften, bevor sich Feuchte in den Wänden festsetzt."]);
    if (k.regen_bald && k.minuten > 0 && !k.laeuft) alerts.push(["info", "mdi:weather-rainy", "Bald Regen", "Lieber jetzt lüften, bevor es regnet."]);
    if (k.urlaub) alerts.push(["info", "mdi:palm-tree", "Urlaubsmodus", "Keine Erinnerungen – nur Warnungen bei Schimmelgefahr."]);
    const alertHtml = alerts
      .slice(0, 2)
      .map(([tone, icon, title, text]) => `<div class="alert tone-${tone}"><ha-icon icon="${icon}"></ha-icon><div><b>${esc(title)}</b><span>${esc(text)}</span></div></div>`)
      .join("");

    const compact = !!this._config.compact;
    const tiles = this._config.show_details && !compact ? this._tiles(k, e) : "";
    const chart = this._config.show_chart && !compact ? this._chart(k.verlauf) : "";
    const trend = this._config.show_trend !== false && !compact ? trendChart(k.trend_tage) : "";
    const year = this._config.show_year !== false && !compact ? yearChart(k.monatsverlauf) : "";
    const winList = !compact ? windowStatus(k.fenster_status) : "";

    const heuteText = `${fmt(k.heute_anzahl, 0)}× heute · ${fmt(k.heute_min, 0)} Min.`;
    const heuteTone = k.gelueftet && "good";
    const partyText = k.party_bis
      ? `Bis ${new Date(k.party_bis).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" })} Uhr`
      : "Party-Modus";
    // e.party_mode kann fehlen, obwohl der Party-Modus aktiv ist (z.B. direkt nach einem Neustart,
    // solange die Button-Entität noch nicht in der Entity-Registry registriert ist) - dann keinen
    // Tipp zeigen, der Interaktion verspricht, die der (dann als <span> gerenderte) Chip nicht bietet.
    const partyTitle = e.party_mode ? "Antippen, um den Party-Modus vorzeitig zu beenden" : undefined;
    const chips = [
      k.party_modus && [e.party_mode || null, "mdi:party-popper", partyText, "info", partyTitle, null, null, true],
      k.bester_zeitpunkt && !compact && [
        e.bester,
        "mdi:clock-check-outline",
        String(k.bester_zeitpunkt).includes("Wetterdaten nicht verfügbar")
          ? "Vorhersage nicht verfügbar"
          : k.bester_zeitpunkt,
        String(k.bester_zeitpunkt).includes("Wetterdaten nicht verfügbar") ? "warn" : undefined,
      ],
      k.statistik && !compact
        ? [null, k.gelueftet ? "mdi:check-circle-outline" : "mdi:calendar-today", heuteText, heuteTone,
            "Woche, Monat und Gesamt anzeigen", "stats", this._roomStatsExpanded]
        : [e.heute, k.gelueftet ? "mdi:check-circle-outline" : "mdi:calendar-today", heuteText, heuteTone],
      !compact && costChip(e.kosten, k.heute_kwh, k.heute_eur, k.heute_kwh_gespart, k.heute_eur_gespart),
      !compact && k.kuehlen_plan && !(k.minuten > 0 && k.grund === "Kühlen") && [null, "mdi:weather-night", `Kühlen ${k.kuehlen_plan}`],
      !compact && k.vorheizen_plan && !(k.minuten > 0 && k.grund === "Vorheizen") && [null, "mdi:thermometer-chevron-up", `Vorheizen ${k.vorheizen_plan}`],
      !compact && k.entfeuchter && [null, "mdi:air-humidifier", "Entfeuchter läuft"],
      !compact && k.rollo_geschlossen && [null, "mdi:roller-shade-closed", "Rollo geschlossen"],
      !compact && k.rollo_empfehlung && !k.rollo_geschlossen && [null, "mdi:roller-shade", "Rollo schließen empfohlen", "warn"],
      !compact && k.ruhezeit && !String(k.pausiert || "").startsWith("Ruhezeit") && [null, "mdi:sleep", "Ruhezeit"],
    ]
      .filter(Boolean)
      .map(renderChip)
      .join("");
    const stats = k.statistik && this._roomStatsExpanded && !compact ? statsPanel(k.statistik) : "";

    const snoozeButtons = this._config.show_actions !== false && k.minuten > 0 && !k.laeuft && !k.pausiert && e.snooze && e.skip
      ? [
          `<button class="action-btn" data-entity="${esc(e.snooze)}" data-press="1">
             <ha-icon icon="mdi:alarm-snooze"></ha-icon>In 30 Min. erinnern</button>`,
          `<button class="action-btn" data-entity="${esc(e.skip)}" data-press="1">
             <ha-icon icon="mdi:calendar-remove-outline"></ha-icon>Heute nicht mehr</button>`,
        ]
      : [];
    const partyButton = this._config.show_actions !== false && !k.party_modus && e.party_mode
      ? [`<button class="action-btn" data-entity="${esc(e.party_mode)}" data-press="1">
             <ha-icon icon="mdi:party-popper"></ha-icon>Party-Modus starten</button>`]
      : [];
    const actionBtns = compact ? [] : [...snoozeButtons, ...partyButton];
    const actions = actionBtns.length ? `<div class="actions">${actionBtns.join("")}</div>` : "";

    return `
      <div class="head" data-entity="" role="button" tabindex="0" aria-label="${esc(k.name)}: ${esc(h.title)}">
        <div class="badge tone-${st.tone} ${st.pulse ? "pulse" : ""}"><ha-icon icon="${st.icon}"></ha-icon></div>
        <div class="title">
          <div class="name">${esc(k.name)}</div>
          <div class="meta"><ha-icon icon="${season[0]}"></ha-icon>${esc(join([season[1], windows]))}</div>
        </div>
        <span class="pill tone-${st.tone}"><i></i>${esc(st.pill)}</span>
      </div>
      <div class="hero">
        <div class="headline">${esc(h.title)}</div>
        ${h.sub && !compact ? `<div class="sub">${esc(h.sub)}</div>` : ""}
      </div>
      ${compact ? "" : `${progress}${actions}${alertHtml}${tiles}${chart}${trend}${year}${winList}`}
      ${chips ? `<div class="chips">${chips}</div>` : ""}${stats}`;
  }

  _tiles(k, e) {
    const risk = RISK[k.schimmel] || ["neutral", k.schimmel || "–"];
    const wallPct = Math.max(0, Math.min(100, k.wand_rh || 0));
    const tiles = [
      `<button class="tile" data-entity="${esc(e.innen || "")}" aria-label="Innen ${fmt(k.innen_t)} Grad, ${fmt(k.innen_ah)} Gramm pro Kubikmeter, ${fmt(k.innen_rh, 0)} Prozent">
         <span class="t-label"><ha-icon icon="mdi:home-thermometer-outline"></ha-icon>Innen</span>
         <span class="t-value">${fmt(k.innen_t)}<small>°C</small></span>
         <span class="t-sub" title="${has(k.innen_rh) ? `${fmt(k.innen_rh, 0)} % relative Feuchte` : ""}">${fmt(k.innen_ah)} g/m³</span>
       </button>`,
      `<button class="tile" data-entity="${esc(e.aussen || "")}" aria-label="Außen ${fmt(k.aussen_t)} Grad">
         <span class="t-label"><ha-icon icon="mdi:weather-partly-cloudy"></ha-icon>Außen</span>
         <span class="t-value">${fmt(k.aussen_t)}<small>°C</small></span>
         <span class="t-sub">${fmt(k.aussen_ah)} g/m³</span>
       </button>`,
      `<button class="tile" data-entity="${esc(e.wand || "")}" aria-label="Wand ${fmt(k.wand_rh, 0)} Prozent Feuchte bei ${fmt(k.wand_t)} Grad, Schimmelrisiko ${esc(risk[1])}">
         <span class="t-label"><ha-icon icon="mdi:wall"></ha-icon>Wand</span>
         <span class="t-value">${fmt(k.wand_rh, 0)}<small>%</small></span>
         <span class="meter tone-${risk[0]}"><span style="width:${wallPct}%"></span><i style="left:70%"></i><i style="left:80%"></i></span>
         <span class="t-sub" title="Wandtemperatur ${fmt(k.wand_t)} °C"><i class="dot tone-${risk[0]}"></i>${esc(risk[1].charAt(0).toUpperCase() + risk[1].slice(1))}</span>
       </button>`,
    ];
    if (has(k.co2)) {
      const tone = AIR[k.luft] || "neutral";
      const pct = Math.max(0, Math.min(100, ((k.co2 - 400) / 1600) * 100));
      tiles.push(
        `<button class="tile" data-entity="${esc(e.co2 || "")}" aria-label="CO2 ${fmt(k.co2, 0)} ppm, ${esc(k.luft || "")}">
           <span class="t-label"><ha-icon icon="mdi:molecule-co2"></ha-icon>CO₂</span>
           <span class="t-value">${fmt(k.co2, 0)}<small>ppm</small></span>
           <span class="meter tone-${tone}"><span style="width:${pct}%"></span><i style="left:37.5%"></i><i style="left:62.5%"></i></span>
           <span class="t-sub"><i class="dot tone-${tone}"></i>${esc((k.luft || "–").charAt(0).toUpperCase() + (k.luft || "–").slice(1))}</span>
         </button>`
      );
    }
    return `<div class="tiles n${tiles.length}">${tiles.join("")}</div>`;
  }

  /* ---------- Verlauf: nur Feuchte (eine Achse), Temperatur als Text & im Tooltip ---------- */
  _chart(trace) {
    const pts = (trace?.punkte || []).filter((p) => has(p[1]));
    if (pts.length < 2) return "";
    const W = 320, H = 72, PX = 2, PY = 6;
    const t0 = pts[0][0], t1 = pts[pts.length - 1][0] || 1;
    const vals = pts.map((p) => p[1]);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = Math.max((hi - lo) * 0.15, 0.2);
    lo -= pad; hi += pad;
    const x = (t) => PX + ((t - t0) / (t1 - t0 || 1)) * (W - 2 * PX);
    const y = (v) => PY + (1 - (v - lo) / (hi - lo)) * (H - 2 * PY);
    const line = pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
    const area = `${line} L${x(pts[pts.length - 1][0]).toFixed(1)},${H} L${x(t0).toFixed(1)},${H} Z`;
    const first = pts[0], last = pts[pts.length - 1];
    const drop = first[1] > 0 ? Math.round((1 - last[1] / first[1]) * 100) : 0;
    const temps = has(first[2]) && has(last[2]) ? `Temp. ${fmt(first[2])} → ${fmt(last[2])} °C` : "";

    // Temperatur als zweite Linie, eigene (relative) Skala – es geht um den Verlauf, nicht um
    // exakte Achsenwerte, daher keine zweite Beschriftung nötig.
    const tPts = pts.filter((p) => has(p[2]));
    let y2 = null, tempLine = "";
    if (tPts.length >= 2) {
      const tVals = tPts.map((p) => p[2]);
      let tlo = Math.min(...tVals), thi = Math.max(...tVals);
      const tpad = Math.max((thi - tlo) * 0.25, 0.3);
      tlo -= tpad; thi += tpad;
      y2 = (v) => PY + (1 - (v - tlo) / (thi - tlo)) * (H - 2 * PY);
      tempLine = tPts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y2(p[2]).toFixed(1)}`).join(" ");
    }

    this._chartData = { pts, x, y, y2, W, H, t0 };
    const title = trace.laeuft ? "Laufende Lüftung" : "Letzte Lüftung";
    return `
      <div class="chart">
        <div class="c-head">
          <span class="c-title">${title}</span>
          ${tempLine ? `<span class="c-legend"><i class="lg lg-hum"></i>Feuchte<i class="lg lg-temp"></i>Temp.</span>` : ""}
          <span class="c-meta">${esc(join([!trace.laeuft && ago(trace.ende), dur(last[0] - first[0])]))}</span>
        </div>
        <div class="c-values"><b>${fmt(first[1])} → ${fmt(last[1])}</b> g/m³
          ${drop > 0 ? `<span class="delta">−${drop} %</span>` : ""}<span class="c-temp">${esc(temps)}</span></div>
        <div class="plot" role="img" aria-label="${title}: absolute Feuchte von ${fmt(first[1])} auf ${fmt(last[1])} g/m³${temps ? ", " + temps : ""}">
          <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
            <defs><linearGradient id="${this._uid}g" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stop-color="var(--sv-info)" stop-opacity=".28"/><stop offset="1" stop-color="var(--sv-info)" stop-opacity="0"/>
            </linearGradient></defs>
            <path d="${area}" fill="url(#${this._uid}g)"/>
            ${tempLine ? `<path d="${tempLine}" class="line-temp"/>` : ""}
            <path d="${line}" class="line"/>
            <line class="cross" x1="0" x2="0" y1="0" y2="${H}" visibility="hidden"/>
          </svg>
          <span class="dot-end" style="left:${(x(last[0]) / W) * 100}%;top:${(y(last[1]) / H) * 100}%"></span>
          <span class="dot-hover" hidden></span>
          <span class="dot-hover-temp" hidden></span>
          <div class="tip" hidden></div>
        </div>
        <div class="c-axis"><span>0:00</span><span>${dur(last[0] - first[0])}</span></div>
      </div>`;
  }

  _bindChart() {
    const plot = this.shadowRoot.querySelector(".plot");
    if (!plot || !this._chartData) return;
    const { pts, x, y, y2, W, H, t0 } = this._chartData;
    const cross = plot.querySelector(".cross"), tip = plot.querySelector(".tip");
    const dot = plot.querySelector(".dot-hover"), dotTemp = plot.querySelector(".dot-hover-temp");
    const show = (clientX) => {
      const r = plot.getBoundingClientRect();
      const vx = ((clientX - r.left) / r.width) * W;
      let best = pts[0];
      for (const p of pts) if (Math.abs(x(p[0]) - vx) < Math.abs(x(best[0]) - vx)) best = p;
      const px = x(best[0]), py = y(best[1]);
      cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.setAttribute("visibility", "visible");
      dot.hidden = false; dot.style.left = `${(px / W) * 100}%`; dot.style.top = `${(py / H) * 100}%`;
      if (y2 && has(best[2])) {
        dotTemp.hidden = false;
        dotTemp.style.left = `${(px / W) * 100}%`; dotTemp.style.top = `${(y2(best[2]) / H) * 100}%`;
      } else {
        dotTemp.hidden = true;
      }
      tip.hidden = false;
      tip.innerHTML = `<b>${fmt(best[1])} g/m³</b><span>${join([dur(best[0] - t0), has(best[2]) && `${fmt(best[2])} °C`])}</span>`;
      // rechts neben der Linie, in der rechten Hälfte links davon
      const at = (px / W) * r.width;
      const right = px / W < 0.5;
      tip.style.left = `${right ? at + 10 : at - 10}px`;
      tip.style.transform = right ? "none" : "translateX(-100%)";
    };
    const hide = () => { cross.setAttribute("visibility", "hidden"); tip.hidden = true; dot.hidden = true; dotTemp.hidden = true; };
    plot.addEventListener("pointermove", (ev) => show(ev.clientX));
    plot.addEventListener("pointerdown", (ev) => show(ev.clientX));
    plot.addEventListener("pointerleave", hide);
  }

  /* ---------- Übersicht ---------- */
  _overview(rooms, summe, trendTage) {
    const needing = rooms.filter((r) => r.lueften && !r.laeuft && !r.pausiert).length;
    const running = rooms.filter((r) => r.laeuft).length;
    const tone = needing ? "warn" : running ? "info" : "good";
    const pill = needing ? `${needing} lüften` : running ? `${running} läuft` : "Alles gut";
    const compact = !!this._config.compact;
    const chip = costChip(null, summe?.heute_kwh, summe?.heute_eur, summe?.heute_kwh_gespart, summe?.heute_eur_gespart);
    const chipHtml = chip
      ? compact
        ? `<span class="chip ${chip[3] ? `tone-${chip[3]}` : ""}" title="${esc(chip[4] || "")}"><ha-icon icon="${chip[1]}"></ha-icon>${esc(chip[2])}</span>`
        : `<button class="chip ${chip[3] ? `tone-${chip[3]}` : ""}" data-toggle="breakdown" title="${esc(chip[4] || "")}" aria-expanded="${this._overviewExpanded}">
           <ha-icon icon="${chip[1]}"></ha-icon>${esc(chip[2])}
           <ha-icon class="chip-caret" icon="${this._overviewExpanded ? "mdi:chevron-up" : "mdi:chevron-down"}"></ha-icon>
         </button>`
      : "";
    // Sammel-Warnung: auf einen Blick, ohne erst jede Raumzeile einzeln lesen zu müssen, wie viele
    // Räume gerade Aufmerksamkeit brauchen (Schimmelrisiko, schlechte Luft, Rollo-Empfehlung).
    const alertParts = overviewAlerts(rooms);
    const alertHtml = alertParts.length
      ? `<span class="chip tone-warn"><ha-icon icon="mdi:alert-circle-outline"></ha-icon>${esc(alertParts.join(" · "))}</span>`
      : "";
    const chips = chipHtml || alertHtml ? `<div class="chips">${alertHtml}${chipHtml}</div>` : "";
    const breakdown = !compact && chip && this._overviewExpanded ? `<div class="breakdown">${breakdownList(rooms)}</div>` : "";
    const trend = this._config.show_trend !== false && !compact ? trendChart(trendTage) : "";
    const sortRow = !compact && rooms.length > 1
      ? `<div class="sort-row" role="group" aria-label="Sortierung">
           ${SORT_MODES.map(
             (m) => `<button class="sort-btn ${this._overviewSort === m.key ? "active" : ""}" data-sort="${m.key}"
                        title="${esc(m.label)}" aria-pressed="${this._overviewSort === m.key}" aria-label="${esc(m.label)}">
                        <ha-icon icon="${m.icon}"></ha-icon></button>`
           ).join("")}
         </div>`
      : "";
    const rows = sortRooms(rooms, this._overviewSort)
      .map((r) => {
        const t = r.laeuft ? ["info", "mdi:window-open-variant", "Lüftung läuft", "läuft"]
          : r.lueften && r.pausiert ? ["neutral", "mdi:pause-circle-outline", r.pausiert, "Pausiert"]
          : r.lueften ? ["warn", "mdi:window-open-variant", r.empfehlung, `${r.minuten} Min.`]
          : ["good", "mdi:check", "Kein Lüften nötig", ""];
        const riskTone = RISK[r.schimmelrisiko];
        const riskIcon = r.schimmelrisiko === "hoch" ? "mdi:alert-octagon-outline" : "mdi:shield-alert-outline";
        // Kleine Symbole neben dem Raumnamen für alles, was sonst erst auf der Einzelraum-Karte
        // sichtbar wäre: Schimmelrisiko, laufender Entfeuchter, empfohlenes (noch offenes) Rollo.
        const badges = [];
        if (riskTone && riskTone[0] !== "good") {
          badges.push([riskIcon, riskTone[0], `Schimmelrisiko ${riskTone[1]}`]);
        }
        if (r.luft === "schlecht") {
          badges.push(["mdi:molecule-co2", "bad", "CO₂ hoch"]);
        }
        if (r.entfeuchter) {
          badges.push(["mdi:air-humidifier", "info", "Entfeuchter läuft"]);
        }
        if (r.rollo_empfehlung && !r.rollo_geschlossen) {
          badges.push(["mdi:roller-shade", "warn", "Rollo schließen empfohlen"]);
        }
        const badgeHtml = badges
          .map(([icon, tone, title]) => `<ha-icon class="risk tone-${tone}" icon="${icon}" title="${esc(title)}"></ha-icon>`)
          .join("");
        return `<button class="row" data-entity="${esc(r.entity_id || "")}" aria-label="${esc(r.raum)}: ${esc(t[2])}">
            <span class="badge small tone-${t[0]}"><ha-icon icon="${t[1]}"></ha-icon></span>
            <span class="r-text"><b>${esc(r.raum)}${badgeHtml}</b><span>${esc(t[2])}</span></span>
            ${t[3] ? `<span class="pill tone-${t[0]}"><i></i>${esc(t[3])}</span>` : ""}
          </button>`;
      })
      .join("");
    return `
      <div class="head" data-entity="" role="button" tabindex="0" aria-label="Lüften Übersicht">
        <div class="badge tone-${tone}"><ha-icon icon="${needing ? "mdi:home-alert-outline" : "mdi:home-heart"}"></ha-icon></div>
        <div class="title"><div class="name">Lüften</div>
          <div class="meta">${rooms.length} ${rooms.length === 1 ? "Raum" : "Räume"}</div></div>
        <span class="pill tone-${tone}"><i></i>${esc(pill)}</span>
      </div>
      ${chips}${breakdown}${trend}${sortRow}
      <div class="rows">${rows || '<div class="empty"><span>Noch keine Räume eingerichtet.</span></div>'}</div>`;
  }
}

/* ---------- Stil: nur Theme-Variablen, feste Farben nur als Fallback ---------- */
const STYLE = `
  :host {
    display: block; container-type: inline-size;
    --sv-radius: var(--ha-card-border-radius, 12px);
    --sv-inner: max(6px, calc(var(--sv-radius) - 6px));
    --sv-good: var(--success-color, #43a047);
    --sv-warn: var(--warning-color, #ffa600);
    --sv-bad: var(--error-color, #db4437);
    --sv-info: var(--info-color, #039be5);
    --sv-neutral: var(--secondary-text-color, #727272);
    --sv-text: var(--primary-text-color);
    --sv-text-2: var(--secondary-text-color);
    --sv-surface: color-mix(in srgb, var(--primary-text-color) 5%, transparent);
    --sv-surface-hover: color-mix(in srgb, var(--primary-text-color) 9%, transparent);
    --sv-line: var(--divider-color, color-mix(in srgb, var(--primary-text-color) 12%, transparent));
  }
  ha-card { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
  .tone-good { --tone: var(--sv-good); } .tone-warn { --tone: var(--sv-warn); } .tone-bad { --tone: var(--sv-bad); }
  .tone-info { --tone: var(--sv-info); } .tone-neutral { --tone: var(--sv-neutral); }
  button { font: inherit; color: inherit; background: none; border: 0; padding: 0; margin: 0; text-align: left; cursor: pointer; }
  [data-entity]:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }

  /* Kopf */
  .head { display: flex; align-items: center; gap: 12px; cursor: pointer; border-radius: var(--sv-inner); }
  .badge { width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; flex: none; position: relative;
    color: var(--tone); background: color-mix(in srgb, var(--tone) 16%, transparent); }
  .badge ha-icon { --mdc-icon-size: 22px; }
  .badge.small { width: 32px; height: 32px; } .badge.small ha-icon { --mdc-icon-size: 18px; }
  .badge.pulse::after { content: ""; position: absolute; inset: 0; border-radius: 50%; border: 2px solid var(--tone);
    animation: sv-pulse 2.4s ease-out infinite; }
  @keyframes sv-pulse { from { transform: scale(1); opacity: .55; } to { transform: scale(1.45); opacity: 0; } }
  .title { flex: 1; min-width: 0; }
  .name { font-size: 16px; font-weight: 600; line-height: 1.3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .meta { display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--sv-text-2); margin-top: 1px; }
  .meta ha-icon { --mdc-icon-size: 14px; }
  .pill { display: inline-flex; align-items: center; gap: 6px; flex: none; font-size: 12px; font-weight: 600;
    padding: 4px 10px; border-radius: 999px; color: var(--sv-text); background: color-mix(in srgb, var(--tone) 14%, transparent); }
  .pill i { width: 7px; height: 7px; border-radius: 50%; background: var(--tone); }

  /* Aussage */
  .hero { display: flex; flex-direction: column; gap: 2px; }
  .headline { font-size: 20px; font-weight: 600; letter-spacing: -0.01em; line-height: 1.25; }
  .sub { font-size: 13px; color: var(--sv-text-2); line-height: 1.4; }

  /* Fortschritt */
  .progress-row { display: flex; justify-content: space-between; font-size: 12px; color: var(--sv-text-2); margin-bottom: 6px;
    font-variant-numeric: tabular-nums; }
  .track { height: 6px; border-radius: 3px; background: color-mix(in srgb, var(--sv-info) 18%, transparent); overflow: hidden; }
  .track .fill { height: 100%; border-radius: 3px; background: var(--sv-info); transition: width .6s ease; }

  /* Schnellaktionen */
  .actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .action-btn { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500;
    padding: 7px 12px; border-radius: 999px; color: var(--sv-text-2); background: var(--sv-surface);
    border: 1px solid var(--sv-line); transition: background .15s; }
  .action-btn:hover { background: var(--sv-surface-hover); color: var(--sv-text); }
  .action-btn ha-icon { --mdc-icon-size: 15px; }

  /* Hinweise */
  .alert { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; border-radius: var(--sv-inner);
    background: color-mix(in srgb, var(--tone) 12%, transparent); border: 1px solid color-mix(in srgb, var(--tone) 28%, transparent); }
  .alert ha-icon { color: var(--tone); --mdc-icon-size: 20px; flex: none; margin-top: 1px; }
  .alert div { display: flex; flex-direction: column; gap: 1px; font-size: 13px; line-height: 1.35; }
  .alert b { font-weight: 600; } .alert span { color: var(--sv-text-2); }

  /* Kacheln */
  .tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .tiles.n4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @container (min-width: 520px) { .tiles.n4 { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
  .tile { display: flex; flex-direction: column; gap: 3px; padding: 10px 12px; border-radius: var(--sv-inner);
    background: var(--sv-surface); min-width: 0; transition: background .15s; }
  .tile:hover { background: var(--sv-surface-hover); }
  .t-label { display: flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 500; letter-spacing: .04em;
    text-transform: uppercase; color: var(--sv-text-2); }
  .t-label ha-icon { --mdc-icon-size: 14px; }
  .t-value { font-size: 20px; font-weight: 600; line-height: 1.2; white-space: nowrap; }
  .t-value small { font-size: 12px; font-weight: 500; color: var(--sv-text-2); margin-left: 2px; }
  .t-sub { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--sv-text-2);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--tone); flex: none; }
  .meter { position: relative; display: block; height: 4px; border-radius: 2px; margin: 3px 0 2px;
    background: color-mix(in srgb, var(--tone) 22%, transparent); }
  .meter > span { position: absolute; inset: 0 auto 0 0; border-radius: 2px; background: var(--tone); }
  .meter i { position: absolute; top: -2px; width: 2px; height: 8px; border-radius: 1px; transform: translateX(-1px);
    background: var(--card-background-color, var(--ha-card-background, #fff)); }

  /* Verlauf */
  .chart { display: flex; flex-direction: column; gap: 4px; }
  .c-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; min-width: 0; }
  .c-title { font-size: 13px; font-weight: 600; min-width: 0; }
  .c-meta { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--sv-text-2); white-space: nowrap; flex: none; }
  .c-legend { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--sv-text-2); }
  .c-legend .lg { display: inline-block; width: 10px; height: 2px; border-radius: 1px; margin-left: 8px; }
  .c-legend .lg:first-child { margin-left: 0; }
  .c-legend .lg-hum { background: var(--sv-info); }
  .c-legend .lg-temp { background: var(--sv-warn, var(--sv-bad)); }
  .c-values { font-size: 12px; color: var(--sv-text-2); display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
  .c-values b { font-size: 14px; color: var(--sv-text); font-weight: 600; }
  .delta { font-weight: 600; color: var(--sv-text); padding: 1px 6px; border-radius: 999px;
    background: color-mix(in srgb, var(--sv-good) 16%, transparent); }
  .c-temp { margin-left: auto; }
  .plot { position: relative; height: 72px; margin-top: 4px; touch-action: pan-y; cursor: crosshair; }
  .plot svg { width: 100%; height: 100%; display: block; overflow: visible; }
  .plot .line { fill: none; stroke: var(--sv-info); stroke-width: 2; vector-effect: non-scaling-stroke;
    stroke-linejoin: round; stroke-linecap: round; }
  .plot .line-temp { fill: none; stroke: var(--sv-warn, var(--sv-bad)); stroke-width: 1.5; stroke-dasharray: 4 3;
    vector-effect: non-scaling-stroke; stroke-linejoin: round; stroke-linecap: round; opacity: .85; }
  .plot .cross { stroke: var(--sv-text-2); stroke-width: 1; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
  .dot-end, .dot-hover { position: absolute; width: 8px; height: 8px; margin: -4px 0 0 -4px; border-radius: 50%;
    background: var(--sv-info); box-shadow: 0 0 0 2px var(--card-background-color, var(--ha-card-background, #fff)); pointer-events: none; }
  .dot-hover-temp { position: absolute; width: 7px; height: 7px; margin: -3.5px 0 0 -3.5px; border-radius: 50%;
    background: var(--sv-warn, var(--sv-bad)); box-shadow: 0 0 0 2px var(--card-background-color, var(--ha-card-background, #fff)); pointer-events: none; }
  .tip { position: absolute; top: 0; padding: 6px 8px; border-radius: 8px;
    font-size: 12px; line-height: 1.3; white-space: nowrap; pointer-events: none; display: flex; flex-direction: column;
    background: var(--card-background-color, var(--ha-card-background, #fff)); color: var(--sv-text);
    box-shadow: 0 2px 8px rgba(0,0,0,.18); border: 1px solid var(--sv-line); }
  .tip span { color: var(--sv-text-2); }
  .tip[hidden], .dot-hover[hidden], .dot-hover-temp[hidden] { display: none; }
  .c-axis { display: flex; justify-content: space-between; font-size: 11px; color: var(--sv-text-2); font-variant-numeric: tabular-nums; }

  /* Chips */
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; padding: 5px 10px; border-radius: 999px;
    background: var(--sv-surface); color: var(--sv-text-2); white-space: nowrap; }
  button.chip:hover { background: var(--sv-surface-hover); }
  .chip ha-icon { --mdc-icon-size: 15px; }
  .chip.tone-good ha-icon { color: var(--sv-good); }
  .chip.tone-warn ha-icon { color: var(--sv-warn); }
  .chip-caret { --mdc-icon-size: 14px !important; opacity: .6; margin-left: -1px; }

  /* 7-Tage-Trend (Sparkline) */
  .trend { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .trend-label { font-size: 11px; color: var(--sv-text-2); white-space: nowrap; flex: none; }
  .trend-bars { flex: 1; display: flex; align-items: flex-end; gap: 4px; height: 48px; min-width: 0; }
  .trend-day { flex: 1; min-width: 0; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: flex-end;
    gap: 1px; color: var(--sv-text-2); font-size: 9px; line-height: 1.1; font-variant-numeric: tabular-nums; }
  .trend-day.is-today { color: var(--sv-text); font-weight: 600; }
  .trend-bar { width: 100%; height: var(--h, 0%); min-height: 2px; border-radius: 2px 2px 0 0;
    background: color-mix(in srgb, var(--sv-info) 35%, transparent); }
  .trend-day.is-today .trend-bar { background: var(--sv-info); }
  .trend-count, .trend-min { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
  .trend-count { font-weight: 600; color: var(--sv-text); }
  .trend-min { opacity: .8; }
  @container (max-width: 400px) {
    .trend { gap: 6px; }
    .trend-bars { gap: 2px; height: 44px; }
    .trend-count, .trend-min { font-size: 8px; }
  }
  .trend-bar.year-bar { background: color-mix(in srgb, var(--sv-neutral) 40%, transparent); }
  .trend-bar.year-bar.is-today { background: var(--sv-neutral); }

  /* Fensterstatus (mehrere Fensterkontakte) */
  .win-list { display: flex; flex-wrap: wrap; gap: 6px; }
  .win-item { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--tone); }
  .win-item ha-icon { --mdc-icon-size: 15px; }

  /* Aufschlüsselung des Netto-Chips */
  .breakdown { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: var(--sv-inner);
    background: var(--sv-surface); font-size: 12px; }
  .breakdown-row { display: flex; justify-content: space-between; gap: 8px; padding: 2px 0; color: var(--sv-text-2); }
  .breakdown-row span:last-child { font-variant-numeric: tabular-nums; color: var(--sv-text); }
  .breakdown-row span.tone-good { color: var(--sv-good); }
  .breakdown-empty { color: var(--sv-text-2); }

  /* Sortierung der Übersicht */
  .sort-row { display: flex; justify-content: flex-end; gap: 2px; }
  .sort-btn { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 999px; color: var(--sv-text-2); }
  .sort-btn ha-icon { --mdc-icon-size: 16px; }
  .sort-btn:hover { background: var(--sv-surface-hover); }
  .sort-btn.active { color: var(--primary-color, var(--sv-info)); background: color-mix(in srgb, var(--sv-info) 16%, transparent); }

  /* Übersicht */
  .rows { display: flex; flex-direction: column; }
  .row { display: flex; align-items: center; gap: 12px; padding: 10px 4px; border-top: 1px solid var(--sv-line); }
  .row:first-child { border-top: 0; }
  .row:hover .r-text b { text-decoration: underline; text-underline-offset: 3px; }
  .r-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .r-text b { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 4px; }
  .r-text span { font-size: 12px; color: var(--sv-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .risk { --mdc-icon-size: 15px; color: var(--tone, var(--sv-bad)); }

  .empty { display: flex; gap: 12px; align-items: center; color: var(--sv-text-2); font-size: 13px; }
  .empty div { display: flex; flex-direction: column; } .empty b { color: var(--sv-text); }
  .err-where { font-size: 11px; opacity: .7; word-break: break-all; }

  @container (max-width: 340px) {
    .tile { padding: 9px 10px; }
    .t-value { font-size: 18px; }
    .c-temp { margin-left: 0; width: 100%; }
    .headline { font-size: 18px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .badge.pulse::after { animation: none; }
    .track .fill { transition: none; }
  }
`;

if (!customElements.get("smart-ventilation-card")) {
  customElements.define("smart-ventilation-card", SmartVentilationCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "smart-ventilation-card",
    name: "Smart Ventilation",
    description: "Lüftungsstatus, Messwerte und Verlauf eines Raums – oder alle Räume auf einen Blick.",
    preview: true,
    documentationURL: "https://github.com/patrickbrundiers-dev/smart_ventilation",
  });
}
