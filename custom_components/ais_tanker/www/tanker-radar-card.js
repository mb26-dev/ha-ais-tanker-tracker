/*
 * AIS Tanker Radar Card
 * Layer 3 of the AIS Tanker Tracker (custom integration "ais_tanker").
 *
 * Visualises the "vessels" attribute of sensor.ais_tanker_overview on a
 * Leaflet nautical chart inside the Shadow DOM of a Lovelace card.
 *
 * Zero build, single file. Resource: /local/tanker-radar-card.js (module)
 */

const TRC_VERSION = "1.1.0";
const TRC_LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
const TRC_LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";

const TRC_DEFAULTS = {
  entity: "sensor.ais_tanker_overview",
  title: "AIS Tanker Radar",
  map_height: "620px",
  default_layer: "satellite",
  default_zoom: 9,
  show_range_rings: true,
  show_vessel_list: true,
  auto_fit: true,
  privacy_mode: false,
};

const TRC_FALLBACK_CENTER = [1.26, 103.83];

const TRC_DEG = String.fromCharCode(176);
const TRC_DOT = String.fromCharCode(183);

const TRC_REGIONS = [
  { key: "home", label: "Home / Local" },
  { key: "andaman", label: "Andaman & Malacca", lat: 4.5, lon: 99.5, zoom: 6 },
  { key: "singapore", label: "Singapore Strait", lat: 1.22, lon: 103.85, zoom: 11 },
  { key: "hormuz", label: "Strait of Hormuz", lat: 26.5, lon: 56.2, zoom: 7 },
  { key: "suez", label: "Suez Canal", lat: 30.5, lon: 32.3, zoom: 8 },
  { key: "fit", label: "Fit All" },
];

const TRC_RING_KM = [10, 25, 50];

const TRC_LOAD_COLORS = {
  Laden: { main: "#ff4d4f", alt: "#fa8c16", label: "LADEN" },
  Ballast: { main: "#00d2b8", alt: "#10b981", label: "BALLAST" },
  other: { main: "#fadb14", alt: "#d4b106", label: "PARTIAL" },
};

const TRC_SOURCES = {
  local_sdr: { label: "LIVE RF", short: "RF", color: "#22d3ee" },
  aisstream: { label: "AISSTREAM", short: "NET", color: "#60a5fa" },
  aishub: { label: "AISHUB", short: "HUB", color: "#a78bfa" },
  demo: { label: "DEMO", short: "DEMO", color: "#94a3b8" },
};

/* Maritime Identification Digits (first 3 digits of a ship MMSI) */
const TRC_MID = {
  "201": "Albania", "205": "Belgium", "209": "Cyprus", "210": "Cyprus", "211": "Germany",
  "212": "Cyprus", "215": "Malta", "218": "Germany", "219": "Denmark", "220": "Denmark",
  "224": "Spain", "225": "Spain", "226": "France", "227": "France", "228": "France",
  "229": "Malta", "230": "Finland", "232": "United Kingdom", "233": "United Kingdom",
  "234": "United Kingdom", "235": "United Kingdom", "236": "Gibraltar", "237": "Greece",
  "238": "Croatia", "239": "Greece", "240": "Greece", "241": "Greece", "244": "Netherlands",
  "245": "Netherlands", "246": "Netherlands", "247": "Italy", "248": "Malta", "249": "Malta",
  "250": "Ireland", "255": "Madeira", "256": "Malta", "257": "Norway", "258": "Norway",
  "259": "Norway", "261": "Poland", "263": "Portugal", "265": "Sweden", "266": "Sweden",
  "271": "Turkey", "273": "Russia", "304": "Antigua and Barbuda", "305": "Antigua and Barbuda",
  "308": "Bahamas", "309": "Bahamas", "311": "Bahamas", "312": "Belize", "314": "Barbados",
  "316": "Canada", "319": "Cayman Islands", "338": "USA", "341": "Saint Kitts and Nevis",
  "351": "Panama", "352": "Panama", "353": "Panama", "354": "Panama", "355": "Panama",
  "356": "Panama", "357": "Panama", "366": "USA", "367": "USA", "368": "USA", "369": "USA",
  "370": "Panama", "371": "Panama", "372": "Panama", "373": "Panama", "374": "Panama",
  "375": "Saint Vincent", "376": "Saint Vincent", "377": "Saint Vincent", "403": "Saudi Arabia",
  "405": "Bangladesh", "412": "China", "413": "China", "414": "China", "416": "Taiwan",
  "417": "Sri Lanka", "419": "India", "422": "Iran", "425": "Iraq", "428": "Israel",
  "431": "Japan", "432": "Japan", "436": "Kazakhstan", "440": "South Korea", "441": "South Korea",
  "447": "Kuwait", "450": "Lebanon", "455": "Maldives", "461": "Oman", "463": "Pakistan",
  "466": "Qatar", "468": "Syria", "470": "UAE", "471": "UAE", "472": "Tajikistan",
  "473": "Yemen", "475": "Yemen", "477": "Hong Kong", "503": "Australia", "506": "Myanmar",
  "508": "Brunei", "511": "Palau", "512": "New Zealand", "514": "Cambodia", "515": "Cambodia",
  "518": "Cook Islands", "520": "Fiji", "525": "Indonesia", "529": "Kiribati", "533": "Malaysia",
  "538": "Marshall Islands", "548": "Philippines", "553": "Papua New Guinea", "563": "Singapore",
  "564": "Singapore", "565": "Singapore", "566": "Singapore", "567": "Thailand", "570": "Tonga",
  "572": "Tuvalu", "574": "Vietnam", "576": "Vanuatu", "577": "Vanuatu", "601": "South Africa",
  "605": "Algeria", "613": "Cameroon", "620": "Comoros", "622": "Egypt", "624": "Ethiopia",
  "627": "Gabon", "636": "Liberia", "637": "Liberia", "642": "Libya", "645": "Mauritius",
  "657": "Nigeria", "664": "Seychelles", "667": "Sierra Leone", "671": "Togo", "672": "Tunisia",
  "677": "Tanzania", "701": "Argentina", "710": "Brazil", "725": "Chile", "730": "Colombia",
  "735": "Ecuador", "755": "Paraguay", "760": "Peru", "770": "Uruguay", "775": "Venezuela",
};

/* ------------------------------------------------------------------------ */
/* Leaflet loader (singleton)                                                */
/* ------------------------------------------------------------------------ */

let trcLeafletPromise = null;
let trcLeafletCssPromise = null;

function trcLoadLeaflet() {
  if (window.L && typeof window.L.map === "function") {
    return Promise.resolve(window.L);
  }
  if (trcLeafletPromise) {
    return trcLeafletPromise;
  }
  trcLeafletPromise = new Promise((resolve, reject) => {
    const waitForGlobal = () => {
      const started = Date.now();
      const timer = setInterval(() => {
        if (window.L && typeof window.L.map === "function") {
          clearInterval(timer);
          resolve(window.L);
        } else if (Date.now() - started > 20000) {
          clearInterval(timer);
          reject(new Error("Leaflet load timeout"));
        }
      }, 100);
    };
    const existing = document.querySelector(`script[src="${TRC_LEAFLET_JS}"]`);
    if (existing) {
      waitForGlobal();
      return;
    }
    const script = document.createElement("script");
    script.src = TRC_LEAFLET_JS;
    script.async = true;
    script.dataset.tankerRadar = "leaflet";
    script.onload = () => {
      if (window.L) {
        resolve(window.L);
      } else {
        waitForGlobal();
      }
    };
    script.onerror = () => {
      trcLeafletPromise = null;
      reject(new Error("Leaflet could not be loaded"));
    };
    document.head.appendChild(script);
  });
  return trcLeafletPromise;
}

function trcLoadLeafletCss() {
  if (!trcLeafletCssPromise) {
    trcLeafletCssPromise = fetch(TRC_LEAFLET_CSS)
      .then((response) => (response.ok ? response.text() : null))
      .catch(() => null);
  }
  return trcLeafletCssPromise;
}

/* ------------------------------------------------------------------------ */
/* Helpers                                                                   */
/* ------------------------------------------------------------------------ */

function trcEsc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function trcNum(value) {
  const n = typeof value === "number" ? value : parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

function trcLoadStyle(status) {
  if (status === "Laden") return TRC_LOAD_COLORS.Laden;
  if (status === "Ballast") return TRC_LOAD_COLORS.Ballast;
  return TRC_LOAD_COLORS.other;
}

function trcSource(source) {
  return TRC_SOURCES[source] || { label: String(source || "UNKNOWN").toUpperCase(), short: "?", color: "#94a3b8" };
}

function trcRotation(v) {
  const hdg = trcNum(v.heading);
  if (hdg !== null && hdg >= 0 && hdg < 360) return hdg;
  const cog = trcNum(v.course);
  if (cog !== null && cog >= 0 && cog < 360) return cog;
  return 0;
}

function trcFlag(mmsi) {
  const mid = String(mmsi || "").slice(0, 3);
  return TRC_MID[mid] || "Unknown flag";
}

function trcRelTime(iso) {
  if (!iso) return "--";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "--";
  let s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  s = s % 60;
  if (m < 60) return `${m}m ${s}s ago`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m ago`;
}

function trcFmt(value, digits, unit) {
  const n = trcNum(value);
  if (n === null) return "--";
  return `${n.toFixed(digits)}${unit ? " " + unit : ""}`;
}

function trcCompassPoint(deg) {
  const n = trcNum(deg);
  if (n === null) return "";
  const pts = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return pts[Math.round(n / 22.5) % 16];
}

function trcDesignDraught(length) {
  const l = trcNum(length);
  if (l === null || l <= 0) return 14;
  const ratio = l < 120 ? 0.068 : 0.064;
  return Math.min(23, Math.max(3.5, l * ratio));
}

/* ------------------------------------------------------------------------ */
/* SVG builders                                                              */
/* ------------------------------------------------------------------------ */

function trcShipSvg(v, size, selected) {
  const style = trcLoadStyle(v.load_status);
  const rot = trcRotation(v);
  const speed = trcNum(v.speed_knots) || 0;
  const moving = speed > 0.5;
  const cog = trcNum(v.course);
  const vecRot = moving && cog !== null ? cog - rot : 0;
  const vecLen = moving ? Math.min(24, 4 + speed * 1.4) : 0;
  const gid = `trc-hull-${v.mmsi}`;
  const wake = moving
    ? `<g class="wake">
         <path d="M-3.4,21 Q-8.5,33 -15,46" />
         <path d="M3.4,21 Q8.5,33 15,46" />
         <path class="wake-core" d="M-2.2,22.5 L0,42 L2.2,22.5 Z" />
       </g>`
    : "";
  const vector = moving
    ? `<g transform="rotate(${vecRot.toFixed(1)})">
         <line class="vector" x1="0" y1="-25" x2="0" y2="${(-25 - vecLen).toFixed(1)}" stroke="${style.main}" />
         <circle cx="0" cy="${(-25 - vecLen).toFixed(1)}" r="1.3" fill="${style.main}" />
       </g>`
    : "";
  return `
    <svg class="ship-svg" viewBox="-50 -50 100 100" width="${size}" height="${size}">
      <defs>
        <linearGradient id="${gid}" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="${style.alt}" />
          <stop offset="0.5" stop-color="${style.main}" />
          <stop offset="1" stop-color="${style.alt}" />
        </linearGradient>
      </defs>
      <g transform="rotate(${rot.toFixed(1)})">
        ${wake}
        ${vector}
        <path d="M0,-24 C4.2,-20 5.6,-14 5.6,-8 L5.6,18 Q5.6,22.6 2.8,23.4 L-2.8,23.4 Q-5.6,22.6 -5.6,18 L-5.6,-8 C-5.6,-14 -4.2,-20 0,-24 Z"
              fill="url(#${gid})" stroke="#07111c" stroke-width="0.9" />
        <path d="M0,-19.5 C2.9,-16.4 3.8,-11.6 3.8,-7.4 L3.8,11 L-3.8,11 L-3.8,-7.4 C-3.8,-11.6 -2.9,-16.4 0,-19.5 Z"
              fill="rgba(0,0,0,0.22)" />
        <line x1="0" y1="-16.5" x2="0" y2="10.5" stroke="#f1ead2" stroke-width="0.75" />
        <line x1="-1.7" y1="-14" x2="-1.7" y2="10.5" stroke="#f1ead2" stroke-width="0.35" opacity="0.7" />
        <line x1="1.7" y1="-14" x2="1.7" y2="10.5" stroke="#f1ead2" stroke-width="0.35" opacity="0.7" />
        <rect x="-4.8" y="-1.3" width="9.6" height="2.6" rx="0.5" fill="#2b3138" stroke="#f1ead2" stroke-width="0.3" />
        <circle cx="-2.4" cy="-11" r="0.75" fill="#20262c" />
        <circle cx="2.4" cy="-11" r="0.75" fill="#20262c" />
        <circle cx="-2.4" cy="-5.5" r="0.75" fill="#20262c" />
        <circle cx="2.4" cy="-5.5" r="0.75" fill="#20262c" />
        <circle cx="-2.4" cy="4" r="0.75" fill="#20262c" />
        <circle cx="2.4" cy="4" r="0.75" fill="#20262c" />
        <circle cx="-2.4" cy="8.5" r="0.75" fill="#20262c" />
        <circle cx="2.4" cy="8.5" r="0.75" fill="#20262c" />
        <circle cx="0" cy="-18" r="0.7" fill="#f8fafc" />
        <rect x="-4.9" y="12" width="9.8" height="6.4" rx="1.1" fill="#f3f5f8" stroke="#8b96a3" stroke-width="0.4" />
        <line x1="-4.2" y1="13.1" x2="4.2" y2="13.1" stroke="#1e293b" stroke-width="0.7" />
        <rect x="-1.7" y="18.7" width="3.4" height="2.8" rx="0.5" fill="${style.main}" stroke="#07111c" stroke-width="0.3" />
      </g>
      ${selected ? '<circle class="sel-ring" cx="0" cy="0" r="30" />' : ""}
    </svg>`;
}

function trcHomeIconHtml() {
  return `
    <div class="home-wrap">
      <div class="home-sweep"></div>
      <div class="home-core">
        <svg viewBox="0 0 40 40" width="30" height="30">
          <circle cx="20" cy="20" r="18" fill="rgba(10,22,38,0.85)" stroke="#22d3ee" stroke-width="1.5" />
          <path d="M20 11 L20 30" stroke="#ffd700" stroke-width="2" stroke-linecap="round" />
          <path d="M15 30 L25 30" stroke="#ffd700" stroke-width="2" stroke-linecap="round" />
          <path d="M14.5 15 A8 8 0 0 1 25.5 15" fill="none" stroke="#22d3ee" stroke-width="1.6" stroke-linecap="round" />
          <path d="M11.5 12 A12 12 0 0 1 28.5 12" fill="none" stroke="#22d3ee" stroke-width="1.4" stroke-linecap="round" opacity="0.6" />
          <circle cx="20" cy="11" r="2" fill="#ffd700" />
        </svg>
      </div>
      <div class="home-label">HOME</div>
    </div>`;
}

function trcCompassSvg() {
  let ticks = "";
  for (let a = 0; a < 360; a += 10) {
    const major = a % 30 === 0;
    const r1 = major ? 41 : 44;
    const rad = (a - 90) * Math.PI / 180;
    const x1 = (Math.cos(rad) * r1).toFixed(2);
    const y1 = (Math.sin(rad) * r1).toFixed(2);
    const x2 = (Math.cos(rad) * 48).toFixed(2);
    const y2 = (Math.sin(rad) * 48).toFixed(2);
    ticks += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${major ? "#7dd3fc" : "#335"}" stroke-width="${major ? 1.4 : 0.8}" />`;
  }
  return `
    <svg class="compass" viewBox="-60 -60 120 120">
      <circle r="52" fill="rgba(4,12,22,0.85)" stroke="rgba(34,211,238,0.55)" stroke-width="1.2" />
      <circle r="36" fill="none" stroke="rgba(34,211,238,0.18)" stroke-width="0.8" />
      ${ticks}
      <text x="0" y="-27" class="cp n">N</text>
      <text x="29" y="3.5" class="cp">E</text>
      <text x="0" y="33" class="cp">S</text>
      <text x="-29" y="3.5" class="cp">W</text>
      <g class="needle needle-cog" data-k="cog-needle">
        <polygon points="0,-46 3.2,-6 0,-2 -3.2,-6" fill="#22d3ee" />
        <polygon points="0,10 2,2 -2,2" fill="#22d3ee" opacity="0.5" />
      </g>
      <g class="needle needle-hdg" data-k="hdg-needle">
        <polygon points="0,-40 2.2,-4 0,0 -2.2,-4" fill="#ffd700" />
      </g>
      <circle r="4" fill="#0b1726" stroke="#e2e8f0" stroke-width="1" />
    </svg>`;
}

function trcProfileSvg() {
  return `
    <svg class="profile" viewBox="0 0 300 130" preserveAspectRatio="xMidYMid meet">
      <defs>
        <linearGradient id="trc-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#0b1a2c" />
          <stop offset="1" stop-color="#11263d" />
        </linearGradient>
        <linearGradient id="trc-sea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#1fb6d9" stop-opacity="0.85" />
          <stop offset="1" stop-color="#062a4a" stop-opacity="0.95" />
        </linearGradient>
        <clipPath id="trc-profile-clip"><rect x="0" y="0" width="300" height="130" rx="10" /></clipPath>
      </defs>
      <g clip-path="url(#trc-profile-clip)">
        <rect x="0" y="0" width="300" height="130" fill="url(#trc-sky)" />
        <g data-k="hull-group">
          <path d="M24,36 L262,36 L284,38 L276,62 C272,82 262,100 250,104 L44,104 C36,104 30,98 28,90 L24,36 Z"
                fill="#2b3640" stroke="#0a121a" stroke-width="1.2" />
          <path data-k="boot-top" d="M27,78 L278,78 L276,82 C273,92 264,102 250,104 L44,104 C36,104 30,98 28,90 Z" fill="#7a1f24" />
          <rect x="34" y="12" width="40" height="24" rx="2" fill="#eef2f6" stroke="#7d8896" stroke-width="0.8" />
          <rect x="38" y="16" width="32" height="4" fill="#1e293b" />
          <rect x="52" y="2" width="9" height="12" fill="#c9a227" stroke="#3a3020" stroke-width="0.6" />
          <line x1="90" y1="30" x2="250" y2="30" stroke="#d6d0bb" stroke-width="1.4" />
          <line x1="90" y1="33" x2="250" y2="33" stroke="#d6d0bb" stroke-width="0.8" opacity="0.7" />
          <rect x="160" y="24" width="10" height="9" fill="#38414b" />
          <line x1="262" y1="36" x2="262" y2="18" stroke="#d6d0bb" stroke-width="1.2" />
          <g class="marks">
            <line x1="270" y1="50" x2="276" y2="50" /><line x1="270" y1="64" x2="275" y2="64" />
            <line x1="268" y1="78" x2="273" y2="78" /><line x1="262" y1="92" x2="267" y2="92" />
          </g>
        </g>
        <g class="sea" data-k="sea">
          <g class="sea-wave">
            <path d="M0,0 C25,-5 50,5 75,0 C100,-5 125,5 150,0 C175,-5 200,5 225,0 C250,-5 275,5 300,0 C325,-5 350,5 375,0 C400,-5 425,5 450,0 C475,-5 500,5 525,0 C550,-5 575,5 600,0 L600,140 L0,140 Z"
                  fill="url(#trc-sea)" />
          </g>
          <line class="waterline" x1="0" y1="0" x2="300" y2="0" />
        </g>
        <text data-k="wl-label" class="wl-label" x="96" y="0">T --</text>
      </g>
    </svg>`;
}

/* ------------------------------------------------------------------------ */
/* Styles                                                                    */
/* ------------------------------------------------------------------------ */

const TRC_STYLE = `
  :host { display: block; }
  ha-card {
    position: relative;
    overflow: hidden;
    padding: 0;
    border-radius: 12px;
    border: none;
    background: #050c16;
    box-shadow: 0px 0px 12px 2px rgba(255, 215, 0, 1);
    container-type: inline-size;
    container-name: trc;
    color: #e2e8f0;
  }
  .wrap { position: relative; width: 100%; height: var(--trc-height, 620px); min-height: 360px; }
  .map { position: absolute; inset: 0; background: #06101c; }
  .map.leaflet-container { font: inherit; background: #06101c; }
  .glass {
    background: rgba(10, 22, 38, 0.82);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(34, 211, 238, 0.32);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  }
  .hud {
    position: absolute; left: 10px; right: 10px; top: 10px; z-index: 800;
    border-radius: 12px; padding: 8px 12px; display: flex; flex-direction: column; gap: 7px;
    font-size: clamp(10px, 1.05cqw, 13px);
  }
  .hud-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .title-block { display: flex; align-items: center; gap: 8px; margin-right: auto; min-width: 0; }
  .title { font-size: clamp(13px, 1.5cqw, 18px); font-weight: 800; color: #ffd700; letter-spacing: 0.3px; white-space: nowrap; }
  .live {
    display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: 999px;
    font-size: 0.82em; font-weight: 800; letter-spacing: 1px; border: 1px solid currentColor;
    color: #34d399; background: rgba(52, 211, 153, 0.12); white-space: nowrap;
  }
  .live.stale { color: #fbbf24; background: rgba(251, 191, 36, 0.12); }
  .live.dead { color: #f87171; background: rgba(248, 113, 113, 0.12); }
  .live i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; animation: livePulse 1.6s ease-in-out infinite; }
  .feeds { display: flex; gap: 6px; font-size: 0.78em; color: #94a3b8; }
  .feed { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
  .feed b { width: 6px; height: 6px; border-radius: 50%; display: inline-block; background: #475569; }
  .feed.on b { background: #34d399; box-shadow: 0 0 6px #34d399; }
  .feed.warn b { background: #fbbf24; }
  .feed.err b { background: #f87171; }
  .pills { display: flex; gap: 6px; flex-wrap: wrap; }
  .pill {
    display: inline-flex; align-items: baseline; gap: 5px; padding: 3px 9px; border-radius: 8px;
    background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(148, 163, 184, 0.22); white-space: nowrap;
  }
  .pill b { font-size: 1.25em; font-variant-numeric: tabular-nums; color: #f8fafc; }
  .pill span { font-size: 0.8em; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }
  .pill.laden b { color: #ff6b6d; }
  .pill.ballast b { color: #2ee6cf; }
  .pill.rf b { color: #22d3ee; }
  .btns { display: flex; gap: 5px; flex-wrap: wrap; }
  .sep { width: 1px; align-self: stretch; background: rgba(148, 163, 184, 0.25); margin: 0 2px; }
  button.chip {
    font: inherit; font-size: 0.88em; cursor: pointer; padding: 4px 9px; border-radius: 7px;
    color: #cbd5e1; background: rgba(15, 30, 50, 0.7); border: 1px solid rgba(34, 211, 238, 0.22);
    transition: background 0.2s, color 0.2s, border-color 0.2s; white-space: nowrap;
  }
  button.chip:hover { border-color: rgba(34, 211, 238, 0.7); color: #fff; }
  button.chip.active { background: rgba(34, 211, 238, 0.2); border-color: #22d3ee; color: #e0fbff; font-weight: 700; }
  button.chip.gold.active { background: rgba(255, 215, 0, 0.16); border-color: #ffd700; color: #ffe680; }
  .layers {
    position: absolute; right: 10px; top: calc(var(--trc-hud-h, 90px) + 18px); z-index: 790;
    border-radius: 10px; padding: 6px; display: flex; flex-direction: column; gap: 4px;
    font-size: clamp(10px, 0.95cqw, 12px);
  }
  .layers .lh { font-size: 0.78em; color: #7dd3fc; letter-spacing: 1px; padding: 0 4px 2px; font-weight: 800; }
  .layers button.chip { text-align: left; }
  .leaflet-top { top: calc(var(--trc-hud-h, 90px) + 10px); }
  .leaflet-bottom { bottom: var(--trc-list-h, 0px); }
  .leaflet-control-zoom a { background: rgba(10, 22, 38, 0.85); color: #e2e8f0; border-color: rgba(34, 211, 238, 0.3); }
  .leaflet-control-zoom a:hover { background: rgba(34, 211, 238, 0.25); color: #fff; }
  .leaflet-bar { border: 1px solid rgba(34, 211, 238, 0.35); box-shadow: none; }
  .leaflet-control-attribution { background: rgba(5, 12, 22, 0.65) !important; color: #64748b !important; font-size: 9px; }
  .leaflet-control-attribution a { color: #7dd3fc !important; }
  .leaflet-tooltip.trc-tip {
    background: rgba(10, 22, 38, 0.92); color: #e2e8f0; border: 1px solid rgba(34, 211, 238, 0.45);
    border-radius: 6px; box-shadow: none; font-size: 11px; font-weight: 700; padding: 2px 7px;
  }
  .leaflet-tooltip.trc-tip::before { display: none; }
  .leaflet-tooltip.trc-ring-label {
    background: transparent; border: none; box-shadow: none; color: rgba(125, 211, 252, 0.9);
    font-size: 10px; font-weight: 700; text-shadow: 0 0 3px #000, 0 0 3px #000; padding: 0;
  }
  .leaflet-tooltip.trc-ring-label::before { display: none; }
  .wrap.lowzoom .leaflet-tooltip.trc-ring-label { display: none; }
  .tr-icon { background: transparent; border: none; }
  .ship { position: relative; cursor: pointer; }
  .ship-svg { position: absolute; inset: 0; overflow: visible; filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.7)); }
  .ship .wake path { fill: none; stroke: rgba(240, 249, 255, 0.75); stroke-width: 1.3; stroke-linecap: round; }
  .ship .wake .wake-core { fill: rgba(240, 249, 255, 0.28); stroke: none; }
  .ship .wake { animation: wakePulse 1.8s ease-in-out infinite; transform-origin: 0px 22px; }
  .ship .vector { stroke-width: 1.2; stroke-dasharray: 2.4 1.6; }
  .ship .sel-ring { fill: none; stroke: #ffd700; stroke-width: 1.6; stroke-dasharray: 4 3; animation: selSpin 6s linear infinite; transform-origin: 0 0; }
  .ship .rf-ring {
    position: absolute; left: 50%; top: 50%; width: 46%; height: 46%; margin: -23% 0 0 -23%;
    border-radius: 50%; border: 2px solid #22d3ee; opacity: 0; animation: rfPulse 2.2s ease-out infinite;
    pointer-events: none;
  }
  .ship .rf-ring.r2 { animation-delay: 1.1s; }
  .ship .rf-tag {
    position: absolute; left: 50%; bottom: 4%; transform: translateX(-50%); font-size: 8px; font-weight: 900;
    letter-spacing: 0.8px; color: #22d3ee; text-shadow: 0 0 3px #000, 0 0 3px #000; white-space: nowrap; pointer-events: none;
  }
  .ship.demo .ship-svg { opacity: 0.85; }
  .home-wrap { position: relative; width: 120px; height: 120px; pointer-events: none; }
  .home-sweep {
    position: absolute; inset: 0; border-radius: 50%;
    background: conic-gradient(from 0deg, rgba(34, 211, 238, 0) 0deg, rgba(34, 211, 238, 0) 300deg, rgba(34, 211, 238, 0.42) 360deg);
    border: 1px solid rgba(34, 211, 238, 0.35);
    animation: sweep 4s linear infinite;
  }
  .home-core { position: absolute; left: 45px; top: 45px; width: 30px; height: 30px; }
  .home-label {
    position: absolute; left: 50%; top: 80px; transform: translateX(-50%); font-size: 9px; font-weight: 900;
    color: #ffd700; letter-spacing: 1.5px; text-shadow: 0 0 3px #000, 0 0 3px #000;
  }
  .list {
    position: absolute; left: 10px; right: 10px; bottom: 10px; z-index: 800; border-radius: 12px;
    padding: 6px 10px 8px; font-size: clamp(10px, 1cqw, 12px);
  }
  .list-head { display: flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; }
  .list-head .lt { font-weight: 800; color: #7dd3fc; letter-spacing: 1px; text-transform: uppercase; font-size: 0.85em; }
  .list-head .note { color: #64748b; font-size: 0.82em; margin-left: auto; }
  .list-head .chev { transition: transform 0.25s; color: #7dd3fc; font-size: 0.9em; }
  .list.collapsed .chev { transform: rotate(180deg); }
  .list.collapsed .strip { display: none; }
  .strip { display: flex; gap: 6px; overflow-x: auto; padding-top: 6px; scrollbar-width: thin; scrollbar-color: #1e3a5f transparent; }
  .vchip {
    flex: 0 0 auto; min-width: 150px; max-width: 200px; cursor: pointer; border-radius: 9px; padding: 5px 8px 5px 10px;
    background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(148, 163, 184, 0.18); position: relative; overflow: hidden;
    transition: border-color 0.2s, background 0.2s;
  }
  .vchip:hover { border-color: rgba(34, 211, 238, 0.6); }
  .vchip.sel { border-color: #ffd700; background: rgba(255, 215, 0, 0.08); }
  .vchip .bar { position: absolute; left: 0; top: 0; bottom: 0; width: 3px; }
  .vchip .vn { font-weight: 800; color: #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .vchip .vs { color: #94a3b8; font-size: 0.86em; white-space: nowrap; margin-top: 1px; font-variant-numeric: tabular-nums; }
  .vchip .src { position: absolute; right: 6px; top: 5px; font-size: 0.72em; font-weight: 900; letter-spacing: 0.5px; }
  .empty { color: #64748b; padding: 6px 2px; }
  .inspector {
    position: absolute; right: 10px; top: calc(var(--trc-hud-h, 90px) + 18px); bottom: calc(var(--trc-list-h, 0px) + 10px);
    width: min(350px, 88%); z-index: 810; border-radius: 12px; padding: 12px 14px; overflow-y: auto;
    transform: translateX(115%); transition: transform 0.35s cubic-bezier(0.2, 0.8, 0.2, 1);
    font-size: 12px; scrollbar-width: thin; scrollbar-color: #1e3a5f transparent;
  }
  .inspector.open { transform: translateX(0); }
  .ins-head { display: flex; align-items: flex-start; gap: 8px; }
  .ins-name { font-size: 17px; font-weight: 900; color: #f8fafc; line-height: 1.15; word-break: break-word; }
  .ins-sub { color: #94a3b8; font-size: 11px; margin-top: 3px; }
  .ins-close {
    margin-left: auto; flex: 0 0 auto; cursor: pointer; width: 26px; height: 26px; border-radius: 7px; font: inherit; font-size: 14px;
    background: rgba(255, 255, 255, 0.06); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.3);
  }
  .tags { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 8px; }
  .tag { font-size: 10px; font-weight: 800; letter-spacing: 0.5px; padding: 2px 7px; border-radius: 6px; border: 1px solid currentColor; }
  .tag.lost { color: #f87171; background: rgba(248, 113, 113, 0.12); }
  .section-t { margin: 12px 0 5px; font-size: 10px; letter-spacing: 1.2px; color: #7dd3fc; font-weight: 800; text-transform: uppercase; }
  .profile { width: 100%; height: auto; display: block; border-radius: 10px; border: 1px solid rgba(34, 211, 238, 0.2); }
  .profile .marks line { stroke: #f8fafc; stroke-width: 1; opacity: 0.7; }
  .profile .sea { transition: transform 1.2s ease; opacity: 0.72; }
  .profile .sea-wave { animation: waveShift 5s linear infinite; }
  .profile .waterline { stroke: #e0fbff; stroke-width: 1; stroke-dasharray: 5 4; opacity: 0.9; }
  .profile .wl-label { fill: #e0fbff; font-size: 11px; font-weight: 800; transition: transform 1.2s ease; }
  .load-row { display: flex; align-items: center; justify-content: space-between; margin-top: 6px; gap: 8px; }
  .load-badge { font-weight: 900; letter-spacing: 1px; padding: 3px 9px; border-radius: 7px; border: 1px solid currentColor; font-size: 11px; }
  .load-meter { flex: 1 1 auto; height: 6px; border-radius: 3px; background: rgba(148, 163, 184, 0.18); overflow: hidden; }
  .load-meter i { display: block; height: 100%; width: 0%; border-radius: 3px; transition: width 1s ease; }
  .nav-row { display: flex; gap: 12px; align-items: center; }
  .compass { width: 120px; height: 120px; flex: 0 0 120px; }
  .compass .cp { fill: #cbd5e1; font-size: 9px; font-weight: 800; text-anchor: middle; }
  .compass .cp.n { fill: #ffd700; }
  .compass .needle { transition: transform 0.9s ease; }
  .nav-legend { display: flex; flex-direction: column; gap: 6px; font-size: 11px; }
  .nav-legend div { display: flex; align-items: center; gap: 6px; }
  .nav-legend i { width: 10px; height: 3px; border-radius: 2px; display: inline-block; }
  .nav-legend b { font-size: 14px; color: #f8fafc; font-variant-numeric: tabular-nums; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
  .cell { background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(148, 163, 184, 0.16); border-radius: 8px; padding: 6px 8px; min-width: 0; }
  .cell .k { font-size: 9.5px; color: #7f8ea3; text-transform: uppercase; letter-spacing: 0.6px; }
  .cell .v { font-size: 13px; font-weight: 800; color: #f1f5f9; margin-top: 2px; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
  .cell.wide { grid-column: 1 / -1; }
  .error {
    position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); z-index: 900; padding: 14px 18px; border-radius: 10px;
    color: #fca5a5; text-align: center; max-width: 80%;
  }
  .hidden { display: none !important; }
  @keyframes livePulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.35; transform: scale(0.75); } }
  @keyframes wakePulse { 0%, 100% { opacity: 0.35; transform: scaleY(0.9); } 50% { opacity: 0.95; transform: scaleY(1.08); } }
  @keyframes rfPulse { 0% { transform: scale(0.6); opacity: 0.9; } 100% { transform: scale(2.1); opacity: 0; } }
  @keyframes sweep { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
  @keyframes selSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
  @keyframes waveShift { from { transform: translateX(0); } to { transform: translateX(-150px); } }
  @container trc (max-width: 640px) {
    .feeds { display: none; }
    .layers { top: auto; bottom: calc(var(--trc-list-h, 0px) + 22px); }
    .inspector { width: auto; left: 10px; }
  }
`;

/* ------------------------------------------------------------------------ */
/* Card                                                                      */
/* ------------------------------------------------------------------------ */

class TankerRadarCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = { ...TRC_DEFAULTS };
    this._hass = null;
    this._stateObj = null;
    this._built = false;
    this._map = null;
    this._L = null;
    this._baseLayers = {};
    this._activeLayer = null;
    this._shipLayer = null;
    this._ringLayer = null;
    this._homeMarker = null;
    this._markers = new Map();
    this._vessels = [];
    this._byMmsi = new Map();
    this._filter = "all";
    this._showRings = true;
    this._layerKey = "satellite";
    this._selected = null;
    this._selectedSnapshot = null;
    this._listOpen = true;
    this._didInitialView = false;
    this._renderQueued = false;
    this._tick = null;
    this._resizeObserver = null;
  }

  static getConfigElement() {
    return document.createElement("tanker-radar-card-editor");
  }

  static getStubConfig() {
    return { ...TRC_DEFAULTS };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("Invalid configuration");
    }
    const merged = { ...TRC_DEFAULTS, ...config };
    if (!merged.entity) {
      throw new Error("Please define an entity (sensor.ais_tanker_overview)");
    }
    const layerChanged = this._built && merged.default_layer !== this._config.default_layer;
    this._config = merged;
    this._privacy = merged.privacy_mode === true;
    this._showRings = merged.show_range_rings !== false && !this._privacy;
    if (!this._built || layerChanged) {
      this._layerKey = ["satellite", "bathymetry", "dark"].includes(merged.default_layer) ? merged.default_layer : "satellite";
    }
    if (this._built) {
      this._applyConfig();
      if (layerChanged && this._map) this._setLayer(this._layerKey);
      this._queueRender();
    }
  }

  set hass(hass) {
    this._hass = hass;
    const st = hass && hass.states ? hass.states[this._config.entity] : null;
    if (st !== this._stateObj) {
      this._stateObj = st;
      this._queueRender();
    }
    if (!this._built && this.isConnected) this._build();
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return 12;
  }

  getGridOptions() {
    return { columns: "full", min_columns: 6, rows: "auto", min_rows: 6 };
  }

  connectedCallback() {
    if (!this._built) this._build();
    if (!this._tick) {
      this._tick = setInterval(() => this._onTick(), 1000);
    }
    if (this._map) {
      setTimeout(() => this._map && this._map.invalidateSize({ pan: false }), 50);
    }
  }

  disconnectedCallback() {
    if (this._tick) {
      clearInterval(this._tick);
      this._tick = null;
    }
  }

  /* ---------------------------------------------------------------- build */

  _build() {
    if (this._built) return;
    this._built = true;
    const root = this.shadowRoot;
    root.innerHTML = `
      <style data-k="leaflet-css"></style>
      <style>${TRC_STYLE}</style>
      <ha-card>
        <div class="wrap" data-k="wrap">
          <div class="map" data-k="map"></div>
          <div class="hud glass" data-k="hud">
            <div class="hud-row">
              <div class="title-block">
                <svg viewBox="0 0 24 24" width="20" height="20"><circle cx="12" cy="12" r="10" fill="none" stroke="#22d3ee" stroke-width="1.5"/><circle cx="12" cy="12" r="5" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.6"/><path d="M12 12 L19 5" stroke="#ffd700" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="12" r="1.8" fill="#ffd700"/></svg>
                <span class="title" data-k="title"></span>
                <span class="live" data-k="live"><i></i><span data-k="live-text">LIVE AIS RADAR</span></span>
              </div>
              <div class="feeds" data-k="feeds"></div>
              <div class="pills" data-k="pills"></div>
            </div>
            <div class="hud-row">
              <div class="btns" data-k="regions"></div>
              <span class="sep"></span>
              <div class="btns" data-k="filters"></div>
            </div>
          </div>
          <div class="layers glass" data-k="layers">
            <div class="lh">CHART LAYER</div>
            <button class="chip" data-layer="satellite">Ocean Satellite + SeaMap</button>
            <button class="chip" data-layer="bathymetry">Bathymetry Ocean Relief</button>
            <button class="chip" data-layer="dark">Dark Tactical Radar</button>
          </div>
          <div class="inspector glass" data-k="inspector"></div>
          <div class="list glass" data-k="list">
            <div class="list-head" data-k="list-head">
              <span class="lt">Nearest Tankers</span>
              <span class="chev">&#9660;</span>
              <span class="note" data-k="list-note"></span>
            </div>
            <div class="strip" data-k="strip"></div>
          </div>
          <div class="error glass hidden" data-k="error"></div>
        </div>
      </ha-card>`;

    this._el = {};
    root.querySelectorAll("[data-k]").forEach((node) => {
      this._el[node.dataset.k] = node;
    });

    this._el.regions.innerHTML = TRC_REGIONS.map(
      (r) => `<button class="chip" data-region="${r.key}">${trcEsc(r.label)}</button>`
    ).join("");
    this._el.filters.innerHTML = `
      <button class="chip" data-filter="all">All</button>
      <button class="chip" data-filter="laden">Laden Only</button>
      <button class="chip" data-filter="local">Local RF Only</button>
      <button class="chip gold" data-toggle="rings">Show Radar Rings</button>`;

    this._el.regions.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-region]");
      if (btn) this._jump(btn.dataset.region);
    });
    this._el.filters.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button");
      if (!btn) return;
      if (btn.dataset.filter) {
        this._filter = btn.dataset.filter;
        this._queueRender();
      } else if (btn.dataset.toggle === "rings") {
        this._showRings = !this._showRings;
        this._updateRings();
        this._updateButtons();
      }
    });
    this._el.layers.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-layer]");
      if (btn) this._setLayer(btn.dataset.layer);
    });
    this._el["list-head"].addEventListener("click", () => {
      this._listOpen = !this._listOpen;
      this._el.list.classList.toggle("collapsed", !this._listOpen);
      this._measure();
    });
    this._el.strip.addEventListener("click", (ev) => {
      const chip = ev.target.closest("[data-mmsi]");
      if (chip) this._select(parseInt(chip.dataset.mmsi, 10), true);
    });
    this._el.inspector.addEventListener("click", (ev) => {
      if (ev.target.closest("[data-k='close']")) this._closeInspector();
    });

    this._resizeObserver = new ResizeObserver(() => {
      this._measure();
      if (this._map) this._map.invalidateSize({ pan: false });
    });
    this._resizeObserver.observe(this._el.wrap);
    this._resizeObserver.observe(this._el.hud);
    this._resizeObserver.observe(this._el.list);

    this._applyConfig();
    this._initMap();
  }

  _applyConfig() {
    if (!this._el) return;
    const h = this._config.map_height;
    const height = typeof h === "number" ? `${h}px` : String(h || "620px");
    this._el.wrap.style.setProperty("--trc-height", height);
    this._el.title.textContent = this._config.title || "AIS Tanker Radar";
    this._el.list.classList.toggle("hidden", this._config.show_vessel_list === false);
    const ringsBtn = this._el.filters.querySelector("[data-toggle='rings']");
    if (ringsBtn) ringsBtn.classList.toggle("hidden", this._privacy);
    if (this._map && this._L) {
      if (this._privacy && this._homeMarker) {
        this._map.removeLayer(this._homeMarker);
        this._homeMarker = null;
      } else if (!this._privacy && !this._homeMarker) {
        const L = this._L;
        this._homeMarker = L.marker(this._homeLatLng(), {
          icon: L.divIcon({ className: "tr-icon", html: trcHomeIconHtml(), iconSize: [120, 120], iconAnchor: [60, 60] }),
          interactive: false,
          keyboard: false,
          zIndexOffset: -1000,
        }).addTo(this._map);
      }
    }
    this._updateButtons();
    this._updateRings();
    this._measure();
  }

  _measure() {
    if (!this._el) return;
    const hud = this._el.hud.getBoundingClientRect().height || 90;
    const listVisible = this._config.show_vessel_list !== false;
    const list = listVisible ? (this._el.list.getBoundingClientRect().height || 0) + 10 : 0;
    this._el.wrap.style.setProperty("--trc-hud-h", `${Math.round(hud)}px`);
    this._el.wrap.style.setProperty("--trc-list-h", `${Math.round(list)}px`);
  }

  async _initMap() {
    try {
      const [L, css] = await Promise.all([trcLoadLeaflet(), trcLoadLeafletCss()]);
      if (css) {
        this._el["leaflet-css"].textContent = css;
      } else {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = TRC_LEAFLET_CSS;
        link.addEventListener("load", () => this._map && this._map.invalidateSize({ pan: false }));
        this.shadowRoot.insertBefore(link, this.shadowRoot.firstChild);
      }
      this._L = L;
      this._createMap();
    } catch (err) {
      this._showError(`Map engine could not be loaded: ${err && err.message ? err.message : err}`);
    }
  }

  _createMap() {
    const L = this._L;
    const home = this._homeLatLng();
    this._map = L.map(this._el.map, {
      zoomControl: false,
      attributionControl: true,
      worldCopyJump: true,
      minZoom: 2,
      maxZoom: 18,
      zoomSnap: 0.5,
    }).setView(home, Number(this._config.default_zoom) || 9);
    this._map.attributionControl.setPrefix(false);
    L.control.zoom({ position: "topleft" }).addTo(this._map);

    const seamark = () =>
      L.tileLayer("https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png", {
        maxZoom: 18,
        opacity: 0.95,
        attribution: '&copy; <a href="https://www.openseamap.org">OpenSeaMap</a>',
      });
    this._baseLayers = {
      satellite: L.layerGroup([
        L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
          maxZoom: 18,
          maxNativeZoom: 17,
          attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics",
        }),
        seamark(),
      ]),
      bathymetry: L.layerGroup([
        L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}", {
          maxZoom: 18,
          maxNativeZoom: 13,
          attribution: "&copy; Esri, GEBCO, NOAA, Garmin",
        }),
        L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}", {
          maxZoom: 18,
          maxNativeZoom: 13,
        }),
        seamark(),
      ]),
      dark: L.layerGroup([
        L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
          maxZoom: 18,
          maxNativeZoom: 16,
          attribution: "&copy; Esri, HERE, Garmin, OpenStreetMap contributors",
        }),
        L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}", {
          maxZoom: 18,
          maxNativeZoom: 16,
        }),
        seamark(),
      ]),
    };
    this._setLayer(this._layerKey);

    this._ringLayer = L.layerGroup().addTo(this._map);
    this._shipLayer = L.layerGroup().addTo(this._map);
    if (!this._privacy) {
      this._homeMarker = L.marker(home, {
        icon: L.divIcon({ className: "tr-icon", html: trcHomeIconHtml(), iconSize: [120, 120], iconAnchor: [60, 60] }),
        interactive: false,
        keyboard: false,
        zIndexOffset: -1000,
      }).addTo(this._map);
    }
    this._updateRings();

    this._map.on("zoomend", () => {
      this._el.wrap.classList.toggle("lowzoom", this._map.getZoom() < 8.5);
      this._renderMarkers(true);
    });
    this._el.wrap.classList.toggle("lowzoom", this._map.getZoom() < 8.5);
    this._map.on("click", () => {
      if (this._selected !== null) this._closeInspector();
    });
    this._measure();
    setTimeout(() => this._map && this._map.invalidateSize({ pan: false }), 60);
    this._queueRender();
  }

  _showError(message) {
    this._el.error.textContent = message;
    this._el.error.classList.remove("hidden");
  }

  _configCenter() {
    const center = Array.isArray(this._config.center) ? this._config.center.map(trcNum) : null;
    return center && center[0] !== null && center[1] !== null ? [center[0], center[1]] : null;
  }

  _homeLatLng() {
    // Privacy mode never uses the Home Assistant location (safe for screenshots)
    if (this._privacy) return this._configCenter() || TRC_FALLBACK_CENTER;
    const cfg = this._hass && this._hass.config ? this._hass.config : null;
    const lat = cfg ? trcNum(cfg.latitude) : null;
    const lon = cfg ? trcNum(cfg.longitude) : null;
    return lat !== null && lon !== null ? [lat, lon] : TRC_FALLBACK_CENTER;
  }

  /* -------------------------------------------------------------- layers */

  _setLayer(key) {
    if (!this._map || !this._baseLayers[key]) {
      this._layerKey = key;
      this._updateButtons();
      return;
    }
    if (this._activeLayer) this._map.removeLayer(this._activeLayer);
    this._activeLayer = this._baseLayers[key];
    this._activeLayer.addTo(this._map);
    this._layerKey = key;
    this._updateButtons();
  }

  _updateRings() {
    if (!this._map || !this._L || !this._ringLayer) return;
    const L = this._L;
    this._ringLayer.clearLayers();
    if (!this._showRings || this._privacy) return;
    const home = this._homeLatLng();
    if (this._homeMarker) this._homeMarker.setLatLng(home);
    TRC_RING_KM.forEach((km, idx) => {
      L.circle(home, {
        radius: km * 1000,
        color: "#22d3ee",
        weight: idx === TRC_RING_KM.length - 1 ? 1.4 : 1,
        opacity: 0.75,
        dashArray: "4 7",
        fill: idx === 0,
        fillColor: "#22d3ee",
        fillOpacity: 0.04,
        interactive: false,
      }).addTo(this._ringLayer);
      const labelPos = [home[0] + km / 111.32, home[1]];
      L.tooltip({ permanent: true, direction: "center", className: "trc-ring-label", interactive: false })
        .setLatLng(labelPos)
        .setContent(`${km} km`)
        .addTo(this._ringLayer);
    });
  }

  _updateButtons() {
    if (!this._el) return;
    this._el.filters.querySelectorAll("[data-filter]").forEach((b) => {
      b.classList.toggle("active", b.dataset.filter === this._filter);
    });
    const rings = this._el.filters.querySelector("[data-toggle='rings']");
    if (rings) rings.classList.toggle("active", this._showRings);
    this._el.layers.querySelectorAll("[data-layer]").forEach((b) => {
      b.classList.toggle("active", b.dataset.layer === this._layerKey);
    });
  }

  /* ---------------------------------------------------------- navigation */

  _filtered() {
    if (this._filter === "laden") return this._vessels.filter((v) => v.load_status === "Laden");
    if (this._filter === "local") return this._vessels.filter((v) => v.source === "local_sdr");
    return this._vessels;
  }

  _jump(key) {
    if (!this._map) return;
    if (key === "home") {
      this._map.flyTo(this._homeLatLng(), 10, { duration: 1.2 });
      return;
    }
    if (key === "fit") {
      this._fitAll(true);
      return;
    }
    const region = TRC_REGIONS.find((r) => r.key === key);
    if (region) this._map.flyTo([region.lat, region.lon], region.zoom, { duration: 1.4 });
  }

  _fitAll(animate) {
    if (!this._map || !this._L) return;
    const pts = this._filtered()
      .filter((v) => trcNum(v.lat) !== null && trcNum(v.lon) !== null)
      .map((v) => [v.lat, v.lon]);
    if (!pts.length) {
      this._map.setView(this._homeLatLng(), Number(this._config.default_zoom) || 9, { animate });
      return;
    }
    if (!this._privacy) pts.push(this._homeLatLng());
    const bounds = this._L.latLngBounds(pts);
    const hud = parseInt(getComputedStyle(this._el.wrap).getPropertyValue("--trc-hud-h"), 10) || 90;
    const list = parseInt(getComputedStyle(this._el.wrap).getPropertyValue("--trc-list-h"), 10) || 0;
    const opts = {
      paddingTopLeft: [40, hud + 30],
      paddingBottomRight: [40, list + 30],
      maxZoom: 12,
    };
    if (animate) {
      this._map.flyToBounds(bounds, { ...opts, duration: 1.3 });
    } else {
      this._map.fitBounds(bounds, opts);
    }
  }

  /* -------------------------------------------------------------- render */

  _queueRender() {
    if (this._renderQueued) return;
    this._renderQueued = true;
    requestAnimationFrame(() => {
      this._renderQueued = false;
      this._render();
    });
  }

  _render() {
    if (!this._built) return;
    const st = this._stateObj;
    if (!st) {
      this._showError(`Entity not found: ${this._config.entity}`);
      return;
    }
    this._el.error.classList.add("hidden");
    const attrs = st.attributes || {};
    this._vessels = Array.isArray(attrs.vessels) ? attrs.vessels.filter((v) => v && v.mmsi !== undefined) : [];
    this._byMmsi = new Map(this._vessels.map((v) => [v.mmsi, v]));

    this._renderHud(st, attrs);
    this._renderMarkers(false);
    this._renderList();
    this._updateButtons();
    this._renderInspector(false);

    if (!this._didInitialView && this._map) {
      this._didInitialView = true;
      requestAnimationFrame(() => this._initialView());
    }
  }

  _initialView() {
    if (!this._map) return;
    this._measure();
    this._map.invalidateSize({ pan: false });
    const zoom = Number(this._config.default_zoom) || 9;
    const focus = trcNum(this._config.focus_mmsi);
    if (focus !== null && this._byMmsi.has(focus)) {
      const v = this._byMmsi.get(focus);
      this._map.setView([v.lat, v.lon], Math.max(zoom, 11));
      this._select(focus, false);
      return;
    }
    const center = this._configCenter();
    if (center) {
      this._map.setView(center, zoom);
      return;
    }
    if (this._config.auto_fit !== false && !this._privacy) {
      const near = this._vessels.some((v) => trcNum(v.distance_km) !== null && v.distance_km <= 60);
      if (!near && this._vessels.length) {
        this._fitAll(false);
        return;
      }
    }
    this._map.setView(this._homeLatLng(), zoom);
  }

  _renderHud(st, attrs) {
    const total = this._vessels.length;
    const local = trcNum(attrs.local_sdr_count) || 0;
    const global = (trcNum(attrs.aisstream_count) || 0) + (trcNum(attrs.aishub_count) || 0);
    const laden = this._vessels.filter((v) => v.load_status === "Laden").length;
    const ballast = this._vessels.filter((v) => v.load_status === "Ballast").length;
    const totalText = attrs.vessels_truncated ? `${total}+` : `${total}`;
    this._el.pills.innerHTML = `
      <span class="pill"><b>${totalText}</b><span>Total Tankers</span></span>
      <span class="pill rf"><b>${local}</b><span>Local SDR</span></span>
      <span class="pill"><b>${global}</b><span>Global Net</span></span>
      <span class="pill laden"><b>${laden}</b><span>Laden</span></span>
      <span class="pill ballast"><b>${ballast}</b><span>Ballast</span></span>`;

    const feed = (label, cls, title) => `<span class="feed ${cls}" title="${trcEsc(title)}"><b></b>${label}</span>`;
    const mqttLast = attrs.mqtt_last_message ? Date.parse(attrs.mqtt_last_message) : NaN;
    const rfCls = !attrs.mqtt_enabled ? "" : Number.isFinite(mqttLast) && Date.now() - mqttLast < 300000 ? "on" : "warn";
    const streamStatus = String(attrs.aisstream_status || "disabled");
    const streamCls = streamStatus === "connected" ? "on" : streamStatus === "disabled" ? "" : streamStatus.startsWith("error") ? "err" : "warn";
    const hubStatus = String(attrs.aishub_status || "disabled");
    const hubCls = hubStatus === "ok" ? "on" : hubStatus === "disabled" ? "" : hubStatus === "rate_limited" || hubStatus === "pending" ? "warn" : "err";
    this._el.feeds.innerHTML =
      feed("RF", rfCls, `Local SDR: ${attrs.mqtt_enabled ? "enabled" : "disabled"}`) +
      feed("AISSTREAM", streamCls, `aisstream.io: ${streamStatus}`) +
      feed("AISHUB", hubCls, `AISHub: ${hubStatus}`);
    this._updateLive();
  }

  _updateLive() {
    if (!this._el || !this._stateObj) return;
    const updated = Date.parse(this._stateObj.last_updated || "");
    const age = Number.isFinite(updated) ? (Date.now() - updated) / 1000 : Infinity;
    const live = this._el.live;
    live.classList.toggle("stale", age > 120 && age <= 900);
    live.classList.toggle("dead", age > 900);
    this._el["live-text"].textContent = age > 900 ? "AIS SIGNAL LOST" : age > 120 ? "AIS STALE" : "LIVE AIS RADAR";
  }

  _iconSize(v) {
    const len = trcNum(v.length_m) || 120;
    const hull = Math.max(22, Math.min(54, 16 + len / 8));
    const z = this._map ? this._map.getZoom() : 9;
    const scale = z >= 11 ? 1.15 : z >= 8 ? 1 : z >= 6 ? 0.82 : 0.66;
    return Math.round((hull * scale) / 0.48);
  }

  _renderMarkers(force) {
    if (!this._map || !this._L) return;
    const L = this._L;
    const visible = this._filtered();
    const keep = new Set();
    visible.forEach((v) => {
      const lat = trcNum(v.lat);
      const lon = trcNum(v.lon);
      if (lat === null || lon === null) return;
      keep.add(v.mmsi);
      const size = this._iconSize(v);
      const selected = v.mmsi === this._selected;
      const speed = trcNum(v.speed_knots) || 0;
      const key = [
        trcRotation(v).toFixed(0),
        trcNum(v.course) !== null ? Math.round(v.course) : "x",
        speed > 0.5 ? Math.round(speed * 2) : 0,
        v.load_status,
        v.source,
        selected ? 1 : 0,
        size,
      ].join("|");
      let entry = this._markers.get(v.mmsi);
      if (!entry) {
        const marker = L.marker([lat, lon], {
          icon: this._shipIcon(v, size, selected),
          riseOnHover: true,
          keyboard: false,
        });
        marker.bindTooltip(trcEsc(v.name), { direction: "top", offset: [0, -size * 0.22], className: "trc-tip" });
        marker.on("click", (ev) => {
          if (ev && ev.originalEvent) L.DomEvent.stopPropagation(ev.originalEvent);
          this._select(v.mmsi, false);
        });
        marker.addTo(this._shipLayer);
        entry = { marker, key, name: v.name };
        this._markers.set(v.mmsi, entry);
      } else {
        const ll = entry.marker.getLatLng();
        if (ll.lat !== lat || ll.lng !== lon) entry.marker.setLatLng([lat, lon]);
        if (force || entry.key !== key) {
          entry.marker.setIcon(this._shipIcon(v, size, selected));
          entry.key = key;
        }
        if (entry.name !== v.name) {
          entry.marker.setTooltipContent(trcEsc(v.name));
          entry.name = v.name;
        }
      }
      entry.marker.setZIndexOffset(selected ? 1000 : v.source === "local_sdr" ? 500 : 0);
    });
    for (const [mmsi, entry] of this._markers) {
      if (!keep.has(mmsi)) {
        this._shipLayer.removeLayer(entry.marker);
        this._markers.delete(mmsi);
      }
    }
  }

  _shipIcon(v, size, selected) {
    const rf = v.source === "local_sdr"
      ? '<span class="rf-ring"></span><span class="rf-ring r2"></span><span class="rf-tag">LIVE RF</span>'
      : "";
    const html = `<div class="ship ${trcEsc(v.source)}" style="width:${size}px;height:${size}px">${rf}${trcShipSvg(v, size, selected)}</div>`;
    return this._L.divIcon({
      className: "tr-icon",
      html,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
  }

  _renderList() {
    if (this._config.show_vessel_list === false) return;
    const list = this._filtered().slice(0, 40);
    const totalFiltered = this._filtered().length;
    this._el["list-note"].textContent = totalFiltered
      ? `${totalFiltered} shown${this._privacy ? "" : ` ${TRC_DOT} sorted by distance`}`
      : "";
    if (!list.length) {
      this._el.strip.innerHTML = `<div class="empty">No tankers match the current filter.</div>`;
      return;
    }
    this._el.strip.innerHTML = list
      .map((v) => {
        const style = trcLoadStyle(v.load_status);
        const src = trcSource(v.source);
        const dist = trcNum(v.distance_km);
        const distText = dist === null ? "--" : dist >= 100 ? `${dist.toFixed(0)} km` : `${dist.toFixed(1)} km`;
        const distPart = this._privacy ? "" : `${distText} ${TRC_DOT} `;
        return `
          <div class="vchip ${v.mmsi === this._selected ? "sel" : ""}" data-mmsi="${v.mmsi}">
            <span class="bar" style="background:linear-gradient(${style.main},${style.alt})"></span>
            <span class="src" style="color:${src.color}">${src.short}</span>
            <div class="vn">${trcEsc(v.name)}</div>
            <div class="vs">${distPart}${trcFmt(v.speed_knots, 1, "kn")} ${TRC_DOT} <span style="color:${style.main}">${trcEsc(v.load_status || "Unknown")}</span></div>
          </div>`;
      })
      .join("");
  }

  /* ----------------------------------------------------------- inspector */

  _select(mmsi, fly) {
    const v = this._byMmsi.get(mmsi);
    if (!v) return;
    const changed = this._selected !== mmsi;
    this._selected = mmsi;
    this._selectedSnapshot = v;
    if (fly && this._map && trcNum(v.lat) !== null) {
      this._map.flyTo([v.lat, v.lon], Math.max(this._map.getZoom(), 12), { duration: 1.2 });
    }
    this._renderInspector(changed);
    this._renderMarkers(false);
    this._renderList();
  }

  _closeInspector() {
    this._selected = null;
    this._selectedSnapshot = null;
    this._el.inspector.classList.remove("open");
    this._renderMarkers(false);
    this._renderList();
  }

  _renderInspector(rebuild) {
    if (this._selected === null) return;
    const live = this._byMmsi.get(this._selected);
    if (live) this._selectedSnapshot = live;
    const v = this._selectedSnapshot;
    if (!v) return;
    const box = this._el.inspector;
    if (rebuild || !box.dataset.mmsi || box.dataset.mmsi !== String(v.mmsi)) {
      box.dataset.mmsi = String(v.mmsi);
      box.innerHTML = `
        <div class="ins-head">
          <div>
            <div class="ins-name" data-f="name"></div>
            <div class="ins-sub" data-f="sub"></div>
          </div>
          <button class="ins-close" data-k="close" title="Close">&#10005;</button>
        </div>
        <div class="tags" data-f="tags"></div>
        <div class="section-t">Draught &amp; Load</div>
        ${trcProfileSvg()}
        <div class="load-row">
          <span class="load-badge" data-f="load-badge"></span>
          <span class="load-meter"><i data-f="load-meter"></i></span>
          <span data-f="draught-text" style="font-weight:800;color:#f1f5f9;white-space:nowrap"></span>
        </div>
        <div class="section-t">Navigation</div>
        <div class="nav-row">
          ${trcCompassSvg()}
          <div class="nav-legend">
            <div><i style="background:#22d3ee"></i>COG <b data-f="cog"></b></div>
            <div><i style="background:#ffd700"></i>HDG <b data-f="hdg"></b></div>
            <div style="color:#94a3b8" data-f="nav-status"></div>
          </div>
        </div>
        <div class="section-t">Telemetry</div>
        <div class="grid">
          <div class="cell"><div class="k">Speed (SOG)</div><div class="v" data-f="speed"></div></div>
          <div class="cell"><div class="k">Dimensions (L x W)</div><div class="v" data-f="dims"></div></div>
          <div class="cell wide"><div class="k">Destination</div><div class="v" data-f="dest"></div></div>
          <div class="cell"><div class="k">ETA (UTC)</div><div class="v" data-f="eta"></div></div>
          <div class="cell"><div class="k">Vessel Class</div><div class="v" data-f="class"></div></div>
          <div class="cell"><div class="k">Distance from Home</div><div class="v" data-f="dist"></div></div>
          <div class="cell"><div class="k">Bearing</div><div class="v" data-f="bearing"></div></div>
          <div class="cell"><div class="k">Position</div><div class="v" data-f="pos"></div></div>
          <div class="cell"><div class="k">Last Seen</div><div class="v" data-f="seen"></div></div>
        </div>`;
      requestAnimationFrame(() => box.classList.add("open"));
    } else {
      box.classList.add("open");
    }
    this._fillInspector(v, !live);
  }

  _fillInspector(v, lost) {
    const box = this._el.inspector;
    const f = (k) => box.querySelector(`[data-f="${k}"]`);
    const style = trcLoadStyle(v.load_status);
    const src = trcSource(v.source);
    f("name").textContent = v.name || `MMSI ${v.mmsi}`;
    f("sub").textContent = `${trcFlag(v.mmsi)} ${TRC_DOT} MMSI ${v.mmsi}${v.imo ? ` ${TRC_DOT} IMO ${v.imo}` : ""}${v.callsign ? ` ${TRC_DOT} ${v.callsign}` : ""}`;
    f("tags").innerHTML = `
      <span class="tag" style="color:${src.color}">${src.label}</span>
      <span class="tag" style="color:#e2e8f0">${trcEsc(v.vessel_class || "Unknown class")}</span>
      <span class="tag" style="color:#fbbf24">${trcEsc(v.vessel_type_label || "Tanker")}</span>
      ${lost ? '<span class="tag lost">SIGNAL LOST</span>' : ""}`;

    const draught = trcNum(v.draught_m);
    const design = trcDesignDraught(v.length_m);
    const frac = draught === null ? 0.35 : Math.max(0.12, Math.min(0.98, draught / design));
    const deck = 36;
    const keel = 104;
    const waterY = keel - frac * 0.8 * (keel - deck);
    const sea = box.querySelector("[data-k='sea']");
    if (sea) sea.style.transform = `translateY(${waterY.toFixed(1)}px)`;
    const wl = box.querySelector("[data-k='wl-label']");
    if (wl) {
      wl.style.transform = `translateY(${(waterY - 4).toFixed(1)}px)`;
      wl.textContent = draught === null ? "T --" : `T ${draught.toFixed(1)} m`;
    }
    const badge = f("load-badge");
    badge.textContent = v.load_status === "Laden" ? "LADEN" : v.load_status === "Ballast" ? "BALLAST" : String(v.load_status || "UNKNOWN").toUpperCase();
    badge.style.color = style.main;
    const meter = f("load-meter");
    meter.style.width = `${Math.round(frac * 100)}%`;
    meter.style.background = `linear-gradient(90deg, ${style.alt}, ${style.main})`;
    f("draught-text").textContent = draught === null ? "-- m" : `${draught.toFixed(1)} / ~${design.toFixed(1)} m`;

    const cog = trcNum(v.course);
    const hdgRaw = trcNum(v.heading);
    const hdg = hdgRaw !== null && hdgRaw >= 0 && hdgRaw < 360 ? hdgRaw : null;
    const cogNeedle = box.querySelector("[data-k='cog-needle']");
    const hdgNeedle = box.querySelector("[data-k='hdg-needle']");
    if (cogNeedle) {
      cogNeedle.style.transform = `rotate(${(cog || 0).toFixed(1)}deg)`;
      cogNeedle.style.opacity = cog === null ? "0.2" : "1";
    }
    if (hdgNeedle) {
      hdgNeedle.style.transform = `rotate(${(hdg !== null ? hdg : cog || 0).toFixed(1)}deg)`;
      hdgNeedle.style.opacity = hdg === null ? "0.2" : "1";
    }
    f("cog").textContent = cog === null ? "--" : `${cog.toFixed(1)}${TRC_DEG}`;
    f("hdg").textContent = hdg === null ? "n/a" : `${hdg.toFixed(0)}${TRC_DEG}`;
    f("nav-status").textContent = v.nav_status || "Unknown";

    const dist = trcNum(v.distance_km);
    f("speed").textContent = trcFmt(v.speed_knots, 1, "kn");
    f("dims").textContent = v.length_m ? `${v.length_m} x ${v.width_m || "--"} m` : "--";
    f("dest").textContent = v.destination || "--";
    f("eta").textContent = v.eta || "--";
    f("class").textContent = v.vessel_class || "--";
    const brg = trcNum(v.bearing_deg);
    if (this._privacy) {
      f("dist").textContent = "hidden";
      f("bearing").textContent = "hidden";
    } else {
      f("dist").textContent = dist === null ? "--" : `${dist.toFixed(1)} km / ${(dist / 1.852).toFixed(1)} nm`;
      f("bearing").textContent = brg === null ? "--" : `${brg.toFixed(0)}${TRC_DEG} ${trcCompassPoint(brg)}`;
    }
    f("pos").textContent = trcNum(v.lat) === null ? "--" : `${Number(v.lat).toFixed(4)}, ${Number(v.lon).toFixed(4)}`;
    const seen = f("seen");
    seen.dataset.iso = v.last_seen || "";
    seen.textContent = trcRelTime(v.last_seen);
  }

  _onTick() {
    if (!this._built) return;
    this._updateLive();
    if (this._selected !== null) {
      const seen = this._el.inspector.querySelector("[data-f='seen']");
      if (seen && seen.dataset.iso) seen.textContent = trcRelTime(seen.dataset.iso);
    }
  }
}

/* ------------------------------------------------------------------------ */
/* Visual editor                                                             */
/* ------------------------------------------------------------------------ */

const TRC_EDITOR_SCHEMA = [
  { name: "entity", selector: { entity: { domain: "sensor" } } },
  { name: "title", selector: { text: {} } },
  { name: "map_height", selector: { text: {} } },
  {
    name: "default_layer",
    selector: {
      select: {
        mode: "dropdown",
        options: [
          { value: "satellite", label: "Ocean Satellite + SeaMap" },
          { value: "bathymetry", label: "Bathymetry Ocean Relief" },
          { value: "dark", label: "Dark Tactical Radar" },
        ],
      },
    },
  },
  { name: "default_zoom", selector: { number: { min: 2, max: 18, step: 1, mode: "box" } } },
  { name: "show_range_rings", selector: { boolean: {} } },
  { name: "show_vessel_list", selector: { boolean: {} } },
  { name: "auto_fit", selector: { boolean: {} } },
  { name: "privacy_mode", selector: { boolean: {} } },
];

const TRC_EDITOR_LABELS = {
  entity: "Overview entity",
  title: "Title",
  map_height: "Map height (CSS, e.g. 620px or 80vh)",
  default_layer: "Default chart layer",
  default_zoom: "Default zoom",
  show_range_rings: "Show radar range rings",
  show_vessel_list: "Show vessel list",
  auto_fit: "Auto fit to tankers when none are near home",
  privacy_mode: "Privacy mode (hide home marker, rings, distance and bearing)",
};

class TankerRadarCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = { ...TRC_DEFAULTS };
    this._hass = null;
    this._form = null;
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
  }

  _render() {
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (schema) => TRC_EDITOR_LABELS[schema.name] || schema.name;
      this._form.addEventListener("value-changed", (ev) => {
        const value = { ...ev.detail.value };
        const config = { type: this._config.type || "custom:tanker-radar-card", ...value };
        this._config = config;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    if (this._hass) this._form.hass = this._hass;
    this._form.schema = TRC_EDITOR_SCHEMA;
    this._form.data = { ...TRC_DEFAULTS, ...this._config };
  }
}

/* ------------------------------------------------------------------------ */
/* Registration                                                              */
/* ------------------------------------------------------------------------ */

if (!customElements.get("tanker-radar-card")) {
  customElements.define("tanker-radar-card", TankerRadarCard);
}
if (!customElements.get("tanker-radar-card-editor")) {
  customElements.define("tanker-radar-card-editor", TankerRadarCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "tanker-radar-card")) {
  window.customCards.push({
    type: "tanker-radar-card",
    name: "AIS Tanker Radar Card",
    description: "Live nautical chart and radar HUD for the AIS Tanker Tracker integration.",
    preview: true,
  });
}

console.info(
  `%c TANKER-RADAR-CARD %c v${TRC_VERSION} `,
  "color:#0a1626;background:#ffd700;font-weight:700;border-radius:3px 0 0 3px",
  "color:#ffd700;background:#0a1626;font-weight:700;border-radius:0 3px 3px 0"
);
