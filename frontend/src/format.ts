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
