const TH_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."];

/** "2015-07-22" → "22 ก.ค. 2558" */
export function thaiDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${TH_MONTHS[m - 1]} ${y + 543}`;
}

/** "2015-07-22" → "22 ก.ค." (chart axis) */
export function thaiDateShort(iso: string): string {
  const [, m, d] = iso.split("-").map(Number);
  return `${d} ${TH_MONTHS[m - 1]}`;
}

const TH_WEEKDAYS = ["อาทิตย์", "จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์"];

/** "2015-07-22" → "วันพุธ" */
export function thaiWeekday(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `วัน${TH_WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]}`;
}

/** "2015-07-22" → "ก.ค. 58" (axis for long ranges) */
export function thaiMonthShort(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  return `${TH_MONTHS[m - 1]} ${String(y + 543).slice(2)}`;
}

/** First day of each month among `dates` — axis ticks for long ranges (one label per month). */
export function monthStarts(dates: string[]): string[] {
  return dates.filter((d) => d.endsWith("-01"));
}

/** Rewrite ISO dates inside API text (e.g. risk indicators) to the Thai format. */
export function thaiDatesInText(text: string): string {
  return text.replace(/\d{4}-\d{2}-\d{2}/g, thaiDate);
}

/** Amounts: whole numbers with commas, no currency unit (sales are Rossmann data, not baht). */
export function money(x: number): string {
  return Math.round(x).toLocaleString("en-US");
}

export function percent(x: number, digits = 2): string {
  return `${(x * 100).toFixed(digits)}%`;
}

/** ISO date `n` days after `iso` (negative for before). */
export function addDays(iso: string, n: number): string {
  return new Date(Date.parse(`${iso}T00:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10);
}

export function daysInMonth(ym: string): number {
  return new Date(Date.UTC(Number(ym.slice(0, 4)), Number(ym.slice(5, 7)), 0)).getUTCDate();
}

/** "2015-08" → "ส.ค. 58" */
export function thaiYearMonth(ym: string): string {
  return thaiMonthShort(`${ym}-01`);
}

/** "2015-08" → "ส.ค. 2558" */
export function thaiYearMonthLong(ym: string): string {
  return `${TH_MONTHS[Number(ym.slice(5, 7)) - 1]} ${Number(ym.slice(0, 4)) + 543}`;
}

/** Signed percent change, e.g. "+3%" / "−2%". */
export function change(x: number): string {
  const v = Math.round(x * 100);
  return v === 0 ? "0%" : `${v > 0 ? "+" : "−"}${Math.abs(v)}%`;
}

/** Stagger rows for callouts that are closer than `minGap` slots apart. */
export function pillRows(dates: string[], allDates: string[], minGap: number): number[] {
  const rows: number[] = [];
  dates.forEach((d, i) => {
    const prev = i > 0 ? allDates.indexOf(dates[i - 1]) : -Infinity;
    rows.push(allDates.indexOf(d) - prev < minGap ? (rows[i - 1] ?? 0) + 1 : 0);
  });
  return rows;
}

/** Shortfall probability for people: whole percent, never a bare 0% or 100% from 200 simulated paths. */
export function oddsText(p: number): string {
  if (p < 0.01) return "ต่ำกว่า 1%";
  if (p > 0.99) return "มากกว่า 99%";
  return `${Math.round(p * 100)}%`;
}

/** Probability of a shortfall on `date` from a shortfall-risk response, if that day is in it. */
export function oddsOn(risk: { days: { date: string; p_shortfall: number }[] }, date: string): number | undefined {
  return risk.days.find((d) => d.date === date)?.p_shortfall;
}
