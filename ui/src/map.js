// Leaflet map of Germany with candidate cities. The optimal city is highlighted;
// the rest are shown muted for context. Clicking the optimal marker opens the detail view.

const COLORS = {
  optimal: "#d8e02b", // accent (yellowish)
  other: "#6b7280",
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

  result.evals.forEach((ev) => {
    const isOpt = ev.optimal;
    // For the optimal site, draw soft concentric rings to signal "this is the broad
    // area / region, not the exact city centre" — the site could sit anywhere nearby.
    if (isOpt) {
      // Outer-to-inner so inner rings paint on top. Bigger radii + clearly visible
      // strokes so the "area, not exact city" halo actually reads at this zoom.
      [50000, 33000, 18000].forEach((radius, i) => {
        L.circle([ev.city.lat, ev.city.lon], {
          radius,
          color: COLORS.optimal,
          weight: 1.5,
          opacity: 0.35 + i * 0.2,      // 0.35 → 0.55 → 0.75
          fillColor: COLORS.optimal,
          fillOpacity: 0.06 + i * 0.05, // 0.06 → 0.11 → 0.16
          dashArray: i === 0 ? "6 6" : null,
          interactive: false,
        }).addTo(layer);
      });
    }
    const marker = L.circleMarker([ev.city.lat, ev.city.lon], {
      radius: isOpt ? 12 : 6,
      color: "#fff",
      weight: isOpt ? 2 : 1,
      fillColor: isOpt ? COLORS.optimal : COLORS.other,
      fillOpacity: isOpt ? 1 : 0.55,
      className: isOpt ? "opt-marker" : "",
    });
    marker.bindTooltip(
      `<b>${ev.city.name}</b>${isOpt ? " — optimal" : ""}<br>` +
      `rank #${ev.rank} · ${ev.buildoutYears.toFixed(2)} yr · €${(ev.lcc / 1e6).toFixed(1)}M · ${Math.round(ev.co2Tonnes)} t`,
      { direction: "top", offset: [0, -4] }
    );
    if (isOpt) {
      marker.bindPopup(
        `<div class="map-pop"><div class="map-pop-name">${ev.city.name}</div>` +
        `<div class="map-pop-tag">Optimal area · approximate</div>` +
        `<button class="map-pop-btn">View system details →</button></div>`,
        { closeButton: false, offset: [0, -6] }
      );
      marker.on("popupopen", (e) => {
        const btn = e.popup.getElement().querySelector(".map-pop-btn");
        if (btn) btn.addEventListener("click", () => onPick(ev));
      });
      marker.on("click", () => marker.openPopup());
    } else {
      marker.on("click", () => onPick(ev));
    }
    marker.addTo(layer);
  });

  const opt = result.best;
  map.setView([opt.city.lat, opt.city.lon], 6, { animate: true });
  return result.best;
}

export function invalidate() {
  if (map) setTimeout(() => map.invalidateSize(), 50);
}
