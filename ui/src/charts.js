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
  gas: "#d9737a", // muted red
  unmet: "#5b7290", // grey-blue
  load: "#e8e9e4", // off-white (on dark)
};

const HOURS_PER_WEEK = 168;
let weekChart = null;
let weekEv = null; // ev whose hourly series the selector slices
let mixChart = null;

function baseDefaults() {
  Chart.defaults.color = "#8a8f98";
  Chart.defaults.borderColor = "rgba(255,255,255,.08)";
  Chart.defaults.font.family =
    getComputedStyle(document.body).fontFamily || "system-ui, sans-serif";
}

// Slice one week (168 h) from a full 8760-h series and convert kW -> MW.
const sliceMw = (arr, w) =>
  arr.slice(w * HOURS_PER_WEEK, w * HOURS_PER_WEEK + HOURS_PER_WEEK).map((x) => x / 1000);

// Interactive per-week dispatch: how each source covers the load in the chosen week.
export function renderWeek(canvas, ev, week) {
  baseDefaults();
  if (weekChart) weekChart.destroy();
  weekEv = ev;
  const hrs = Array.from({ length: HOURS_PER_WEEK }, (_, h) => h);
  const loadMw = ev.loadKw / 1000;
  const area = (label, key, color) => ({
    label, data: sliceMw(ev.series[key], week),
    borderColor: color, backgroundColor: color + "cc",
    fill: true, stack: "s", pointRadius: 0, borderWidth: 0,
  });
  weekChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: hrs,
      datasets: [
        area("Solar", "pv", PALETTE.pv),
        area("Wind", "wind", PALETTE.wind),
        area("Battery", "battery", PALETTE.battery),
        area("Gas", "gas", PALETTE.gas),
        area("Unmet", "unmet", PALETTE.unmet),
        {
          label: "Load", data: hrs.map(() => loadMw), borderColor: PALETTE.load,
          borderWidth: 1.5, fill: false, pointRadius: 0, borderDash: [3, 2],
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.raw.toFixed(1)} MW` } },
      },
      scales: {
        x: { grid: { display: false }, title: { display: true, text: "hour of week" },
          ticks: { maxTicksLimit: 7 } },
        y: { stacked: true, title: { display: true, text: "MW" }, beginAtZero: true },
      },
    },
  });
}

// Re-slice the current week chart to a different week without rebuilding it.
export function setWeek(week) {
  if (!weekChart || !weekEv) return;
  const keys = ["pv", "wind", "battery", "gas", "unmet"];
  keys.forEach((k, i) => { weekChart.data.datasets[i].data = sliceMw(weekEv.series[k], week); });
  weekChart.update();
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
