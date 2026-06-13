// Leaflet map of Germany. The GA's best 5 cities + Munich are highlighted and
// clickable (each opens its detail view); the other cities are shown muted for context.

const COLORS = {
  optimal: "#d8e02b", // accent (yellowish) — rank #1
  selected: "#57c7d0", // teal — other top picks + Munich
  other: "#6b7280", // muted context
};

let map = null;
let layer = null;

export function initMap(elId) {
  map = L.map(elId, {
    center: [51.1, 10.2],
    zoom: 6,
    zoomControl: true,
    scrollWheelZoom: false,
    attributionControl: true,
  });
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap &copy; CARTO',
  }).addTo(map);
  return map;
}

// Half-size (degrees) of the grid "cell" each city represents, drawn as a patch.
const CELL_LAT = 0.30;
const CELL_LON = 0.42;
const cellBounds = (lat, lon) => [
  [lat - CELL_LAT, lon - CELL_LON],
  [lat + CELL_LAT, lon + CELL_LON],
];

// Main-KPI hover label: Time, Cost, CO2.
const kpiTip = (ev) =>
  `<b>${ev.city.name}</b>${ev.optimal ? " — optimal" : ev.isMunich ? " — Munich" : ""}` +
  `<div class="map-kpis">` +
  `<span><i>Time</i>${ev.buildoutYears.toFixed(2)} yr</span>` +
  `<span><i>Cost</i>€${(ev.lcc / 1e6).toFixed(0)}M</span>` +
  `<span><i>CO₂</i>${Math.round(ev.co2Tonnes)} t/yr</span>` +
  `</div>`;

// Render the map. `onPick` is called with the chosen city's evaluation.
// Each city is shown as the cell region it represents (a coloured patch). The GA's
// best 5 + Munich are highlighted with their Time/Cost/CO2 KPIs; the rest are muted.
export function renderCities(result, onPick) {
  if (!map) return;
  map.invalidateSize(); // container may have just become visible
  if (layer) layer.remove();
  layer = L.layerGroup().addTo(map);

  // Muted context: every city's cell that wasn't selected by the GA.
  const picked = new Set(result.evals.map((e) => e.city.name));
  (result.allCoords || []).forEach((c) => {
    if (picked.has(c.name)) return;
    L.rectangle(cellBounds(c.lat, c.lon), {
      color: COLORS.other, weight: 1, opacity: 0.35,
      fillColor: COLORS.other, fillOpacity: 0.12,
    }).bindTooltip(c.name, { sticky: true }).addTo(layer);
  });

  // Highlighted picks: rank #1 in accent, the rest in teal. All clickable; hover shows KPIs.
  result.evals.forEach((ev) => {
    const isOpt = ev.optimal;
    const color = isOpt ? COLORS.optimal : COLORS.selected;
    const patch = L.rectangle(cellBounds(ev.city.lat, ev.city.lon), {
      color, weight: isOpt ? 2.5 : 1.5, opacity: 0.95,
      fillColor: color, fillOpacity: isOpt ? 0.4 : 0.28,
      className: isOpt ? "opt-cell" : "",
    });
    patch.bindTooltip(kpiTip(ev), {
      sticky: !isOpt,
      permanent: isOpt,
      direction: "top",
      className: "map-kpi-tip" + (isOpt ? " map-kpi-tip-opt" : ""),
    });
    patch.on("click", () => onPick(ev));
    patch.addTo(layer);
  });

  const opt = result.best;
  map.setView([opt.city.lat, opt.city.lon], 6, { animate: true });
  return result.best;
}

export function invalidate() {
  if (map) setTimeout(() => map.invalidateSize(), 50);
}
