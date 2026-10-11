export const usd = (v: number | null | undefined, digits = 5) =>
  v === null || v === undefined ? "—" : `$${v.toFixed(digits)}`;

export const ms = (v: number) => `${Math.round(v)} ms`;

export const int = (v: number) => v.toLocaleString("en-US");

export const pretty = (v: unknown) => {
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
};
