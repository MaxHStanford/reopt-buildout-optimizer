// Display formatters. Euro is the currency; metric units throughout.

export const eur = (n) => {
  if (n == null || isNaN(n)) return "—";
  if (Math.abs(n) >= 1e6) return "€" + (n / 1e6).toFixed(2) + "M";
  if (Math.abs(n) >= 1e3) return "€" + (n / 1e3).toFixed(0) + "k";
  return "€" + Math.round(n).toLocaleString("en-GB");
};

export const kw = (n) => Math.round(n || 0).toLocaleString("en-GB");
export const num = (n, d = 0) => (n == null ? "—" : Number(n).toLocaleString("en-GB", { maximumFractionDigits: d }));
export const pct = (n) => (n == null ? "—" : Math.round(n * 100) + "%");

export const years = (y) => {
  const yy = y || 0;
  const days = Math.round(yy * 365);
  return { value: yy.toFixed(2), days };
};

export const tonnes = (t) => {
  if (t == null) return "—";
  if (t < 0.05) return "0";
  if (t >= 1000) return (t / 1000).toFixed(1) + "k";
  return Math.round(t).toLocaleString("en-GB");
};
