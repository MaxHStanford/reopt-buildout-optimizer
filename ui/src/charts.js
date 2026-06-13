// Chart.js wrappers for the detail view. Palette avoids purple; each technology and
// objective has a fixed, legible colour.

// Palette tuned to sit under the acid-yellow accent: muted, coordinated tones so
// the yellow stays the brightest thing on screen. Warm amber + cool teal + neutrals.
export const PALETTE = {
  time: "#f2a93b", // amber
  cost: "#6aa0d6", // muted steel-blue
  emit: "#4fbf8f", // muted emerald
  pv: "#f2a93b", // solar amber
  wind: "#57c7d0", // muted teal
  battery: "#8b93a1", // slate
  generator: "#586070", // graphite
  load: "#e8e9e4", // off-white (on dark)
};

let dispatchChart = null;
let mixChart = null;

function baseDefaults() {
  Chart.defaults.color = "#8a8f98";
  Chart.defaults.borderColor = "rgba(255,255,255,.08)";
  Chart.defaults.font.family =
    getComputedStyle(document.body).fontFamily || "system-ui, sans-serif";
}

export function renderDispatch(canvas, d) {
  baseDefaults();
  if (dispatchChart) dispatchChart.destroy();
  const step = Math.max(1, Math.floor(d.labels.length / 12));
  const area = (label, data, color) => ({
    label, data, borderColor: color, backgroundColor: color + "55",
    fill: true, stack: "s", pointRadius: 0, borderWidth: 1, tension: 0.25,
  });
  dispatchChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: d.labels,
      datasets: [
        area("Solar", d.pv, PALETTE.pv),
        area("Wind", d.wind, PALETTE.wind),
        area(d.hasGen ? "Generator" : "Battery", d.fill, d.hasGen ? PALETTE.generator : PALETTE.battery),
        {
          label: "Daily load", data: d.load, borderColor: PALETTE.load,
          borderWidth: 2, fill: false, pointRadius: 0, borderDash: [4, 3], tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.raw.toFixed(1)} MWh` } },
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: false,
          callback(v, i) { return i % step === 0 ? this.getLabelForValue(v) : ""; } } },
        y: { stacked: true, title: { display: true, text: "MWh / day" }, beginAtZero: true },
      },
    },
  });
}

export function renderMix(canvas, ev) {
  baseDefaults();
  if (mixChart) mixChart.destroy();
  const parts = [
    ["Solar", ev.energy.pvKwh, PALETTE.pv],
    ["Wind", ev.energy.windKwh, PALETTE.wind],
    ["Generator", ev.energy.genKwh, PALETTE.generator],
  ].filter((p) => p[1] > 1);
  mixChart = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: parts.map((p) => p[0]),
      datasets: [{ data: parts.map((p) => p[1]), backgroundColor: parts.map((p) => p[2]), borderWidth: 0 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "62%",
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
        tooltip: { callbacks: { label: (c) => `${c.label}: ${(c.raw / 1e6).toFixed(2)} GWh/yr` } },
      },
    },
  });
}
