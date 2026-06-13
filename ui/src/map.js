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

// Render markers. `onPick` is called with the chosen city's evaluation.
export function renderCities(result, onPick) {
  if (!map) return;
  map.invalidateSize(); // container may have just become visible
  if (layer) layer.remove();
  layer = L.layerGroup().addTo(map);

  // Muted context: every city in the database that wasn't selected by the GA.
  const picked = new Set(result.evals.map((e) => e.city.name));
  (result.allCoords || []).forEach((c) => {
    if (picked.has(c.name)) return;
    L.circleMarker([c.lat, c.lon], {
      radius: 4, color: "#fff", weight: 1,
      fillColor: COLORS.other, fillOpacity: 0.4,
    }).bindTooltip(c.name, { direction: "top", offset: [0, -4] }).addTo(layer);
  });

  // Highlighted picks: rank #1 in accent + halo, the rest in teal. All clickable.
  result.evals.forEach((ev) => {
    const isOpt = ev.optimal;
    if (isOpt) {
      // Soft concentric rings signal "broad area / region, not exact city centre".
      [50000, 33000, 18000].forEach((radius, i) => {
        L.circle([ev.city.lat, ev.city.lon], {
          radius,
          color: COLORS.optimal,
          weight: 1.5,
          opacity: 0.35 + i * 0.2,
          fillColor: COLORS.optimal,
          fillOpacity: 0.06 + i * 0.05,
          dashArray: i === 0 ? "6 6" : null,
          interactive: false,
        }).addTo(layer);
      });
    }
    const marker = L.circleMarker([ev.city.lat, ev.city.lon], {
      radius: isOpt ? 12 : 8,
      color: "#fff",
      weight: isOpt ? 2 : 1.5,
      fillColor: isOpt ? COLORS.optimal : COLORS.selected,
      fillOpacity: 1,
      className: isOpt ? "opt-marker" : "",
    });
    marker.bindTooltip(
      `<b>${ev.city.name}</b>${isOpt ? " — optimal" : ev.isMunich ? " — Munich" : ""}<br>` +
      `rank #${ev.rank} · ${ev.buildoutYears.toFixed(2)} yr · €${(ev.lcc / 1e6).toFixed(0)}M · ${Math.round(ev.co2Tonnes)} t · click for details`,
      { direction: "top", offset: [0, -4] }
    );
    marker.on("click", () => onPick(ev));
    marker.addTo(layer);
  });

  const opt = result.best;
  map.setView([opt.city.lat, opt.city.lon], 6, { animate: true });
  return result.best;
}

export function invalidate() {
  if (map) setTimeout(() => map.invalidateSize(), 50);
}
