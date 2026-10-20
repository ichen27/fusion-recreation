// Approximation for draft drawing only. The native command parser owns exact values.
export function dimensionNumber(text) {
  if (typeof text !== "string" || text.length > 96) return NaN;
  const match = text
    .trim()
    .match(/^([+-]?(?:\d+\/-?\d+|\d+(?:\.\d*)?|\.\d+))\s*(mm|cm|m|in|ft)?$/i);
  if (!match || match[1].length > 80) return NaN;
  const [a, b = "1"] = match[1].split("/");
  const factor = { mm: 1, cm: 10, m: 1000, in: 25.4, ft: 304.8 }[
    match[2]?.toLowerCase() ?? "mm"
  ];
  const value = (Number(a) / Number(b)) * factor;
  return Number.isFinite(value) ? value : NaN;
}
