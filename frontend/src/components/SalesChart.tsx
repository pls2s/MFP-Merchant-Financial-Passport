import { useMemo, useState } from "react";
import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  ErrorBar,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  addDays, change, daysInMonth, money, monthStarts, thaiDate, thaiDateShort, thaiMonthShort,
  thaiWeekday, thaiYearMonth, thaiYearMonthLong,
} from "../format";
import type { Forecast, Gap, LongForecast, ModelResult, SalesHistory, SeasonalOutlook } from "../types";
import { Accuracy } from "./Accuracy";

/**
 * Sales chart, simple by default:
 *   4w — actual + main LSTM+GRU 14-day forecast
 *   3m — actual + the same models rolled forward 84 days
 *   1y — monthly bars: last 12 months actual, next 12 months seasonal outlook (NOT deep learning)
 * "แสดงรายละเอียด" adds promo days, holidays, past shortfalls, the assumed promo calendar and
 * synthetic sales after the data ends. Backtests live in <Accuracy>, below the chart.
 */
const RANGES = [
  { key: "4w", label: "4 สัปดาห์", back: 28 },
  { key: "3m", label: "3 เดือน", back: 91 },
  { key: "1y", label: "1 ปี", back: 365 },
] as const;
type RangeKey = (typeof RANGES)[number]["key"];

const DATA_END = "2015-07-31"; // last day of real Rossmann sales
const positive = (x: number | null | undefined) => (x != null && x > 0 ? x : null);
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

interface Props {
  forecast: Forecast;
  history: SalesHistory;
  longForecast: LongForecast;
  seasonal: SeasonalOutlook;
  results: ModelResult[];
  asOf: string;
  gaps: Gap[];
  pastGaps: Gap[];
}

// --- Summary sentence ------------------------------------------------------------

function Summary({ range, p }: { range: RangeKey; p: Props }) {
  const { forecast, history, longForecast, seasonal, asOf, gaps } = p;
  const past = (days: number) =>
    sum(history.points.filter((h) => h.date <= asOf && h.date > addDays(asOf, -days)).map((h) => h.sales ?? 0));

  let headline: React.ReactNode;
  if (range === "4w") {
    const next = sum(forecast.points.filter((x) => x.date > asOf).map((x) => x.forecast));
    headline = <>14 วันข้างหน้าคาดว่าขายได้รวม <b className="num">{money(next)}</b>{" "}
      <Trend value={next / past(14) - 1} label="เทียบ 14 วันที่ผ่านมา" /></>;
  } else if (range === "3m") {
    const next = sum(longForecast.points.map((x) => x.forecast));
    const end = longForecast.points[longForecast.points.length - 1].date;
    headline = <>3 เดือนข้างหน้า (ถึง {thaiDate(end)}) คาดว่าขายได้ประมาณ <b className="num">{money((next / longForecast.points.length) * 30)}</b> ต่อเดือน{" "}
      <Trend value={next / past(longForecast.points.length) - 1} label="เทียบช่วงเท่ากันที่ผ่านมา" /></>;
  } else {
    const months = seasonal.months.filter((m) => m.outlook != null);
    if (!months.length) {
      headline = <>ร้านนี้ข้อมูลปีก่อนไม่พอ จึงยังไม่มีภาพรวม 1 ปี</>;
    } else {
      const peak = months.reduce((a, b) => (b.outlook! > a.outlook! ? b : a));
      headline = <>12 เดือนข้างหน้าคาดว่าขายได้ประมาณ <b className="num">{money(sum(months.map((m) => m.outlook!)) / months.length)}</b> ต่อเดือน
        · ขายดีที่สุด <b>{thaiYearMonthLong(peak.month)}</b> (<span className="num">{money(peak.outlook!)}</span>)
        {" "}<span className="badge">ภาพรวมตามฤดูกาล ไม่ใช่ผลโมเดล deep learning</span></>;
    }
  }
  const next = gaps[0];
  return (
    <div className="chart-summary">
      <div>{headline}</div>
      {next && (
        <div className="summary-warn">
          ระวัง <b>{thaiDate(next.date)}</b> เงินสดอาจไม่พอ ขาดประมาณ <b className="num">{money(next.shortfall)}</b>
          {gaps.length > 1 && ` และอีก ${gaps.length - 1} ครั้งใน 14 วัน`}
        </div>
      )}
    </div>
  );
}

function Trend({ value, label }: { value: number; label: string }) {
  if (!Number.isFinite(value)) return null;
  const flat = Math.abs(value) < 0.02;
  const cls = flat ? "trend flat" : value > 0 ? "trend up" : "trend down";
  const text = flat ? `≈ ใกล้เคียงเดิม${change(value) === "0%" ? "" : ` (${change(value)})`}`
    : `${value > 0 ? "▲ เพิ่มขึ้น" : "▼ ลดลง"} ${change(value)}`;
  return <span className={cls}>{text} <span className="muted">{label}</span></span>;
}

// --- Daily chart (4 weeks / 3 months) --------------------------------------------

interface DayRow {
  date: string;
  actual: number | null;
  forecast: number | null;
  band: [number, number] | null;
  simulated: number | null; // synthetic sales after the data ends (ข้อมูลจำลอง) — details only
  open: boolean;
  promo: boolean;
  holiday: boolean;
  schoolHoliday: boolean;
  assumed: boolean; // promo/open calendar assumed from last year (3-month rollout)
}

function dayRows(range: "4w" | "3m", p: Props, details: boolean): DayRow[] {
  const { forecast, history, longForecast, asOf } = p;
  const hist = new Map(history.points.map((h) => [h.date, h]));
  const main = new Map(forecast.points.map((x) => [x.date, x]));
  const long = new Map(longForecast.points.map((x) => [x.date, x]));
  const simulated = new Map(history.synthetic.points.map((x) => [x.date, x.sales]));
  const back = RANGES.find((r) => r.key === range)!.back;
  const to = range === "4w" ? addDays(asOf, 14) : longForecast.points[longForecast.points.length - 1].date;
  const rows: DayRow[] = [];
  for (let d = addDays(asOf, -back + 1); d <= to; d = addDays(d, 1)) {
    const h = hist.get(d);
    const future = d > asOf;
    const f = range === "4w" ? main.get(d) : long.get(d);
    const row: DayRow = {
      date: d, actual: null, forecast: null, band: null, simulated: null,
      open: h?.open ?? true, promo: h?.promo ?? false, holiday: h?.holiday ?? false,
      schoolHoliday: h?.school_holiday ?? false, assumed: range === "3m" && d > DATA_END,
    };
    if (!future) row.actual = positive(h?.sales);
    else if (details && d <= DATA_END) row.actual = positive(main.get(d)?.actual);
    else if (details) row.simulated = positive(simulated.get(d));
    if (future && f && positive(f.forecast) && f.lower != null && f.upper != null) {
      row.forecast = f.forecast;
      row.band = [f.lower, f.upper];
    }
    if (d === asOf) row.forecast = row.actual; // join the lines at "today"
    rows.push(row);
  }
  return rows;
}

function spans(rows: DayRow[], key: "promo" | "assumed"): [string, string][] {
  const out: [string, string][] = [];
  rows.forEach((r, i) => {
    if (!r[key]) return;
    if (i > 0 && rows[i - 1][key]) out[out.length - 1][1] = r.date;
    else out.push([r.date, r.date]);
  });
  return out;
}

function DayTooltip({ active, payload, label }: { active?: boolean; payload?: { payload: DayRow }[]; label?: string }) {
  if (!active || !payload?.length || !label) return null;
  const r = payload[0].payload;
  const tags = [!r.open && "ร้านปิด", r.promo && "มีโปรโมชัน", r.holiday && "วันหยุดนักขัตฤกษ์", r.schoolHoliday && "ปิดเทอม"].filter(Boolean);
  return (
    <div className="chart-tooltip">
      <strong>{thaiWeekday(label)} {thaiDate(label)}</strong>
      {r.actual != null && <div>ยอดขายจริง <b className="num">{money(r.actual)}</b></div>}
      {r.simulated != null && <div>ยอดขายจำลอง <span className="num">{money(r.simulated)}</span> <span className="muted">(ไม่ใช่ข้อมูลจริง)</span></div>}
      {r.band && r.forecast != null && <div>คาดการณ์ <b className="num">{money(r.forecast)}</b></div>}
      {r.band && <div className="muted">ช่วง {money(r.band[0])} – {money(r.band[1])}</div>}
      {tags.length > 0 && <div className="tooltip-tags">{tags.join(" · ")}</div>}
    </div>
  );
}

function DailyChart({ range, p, details }: { range: "4w" | "3m"; p: Props; details: boolean }) {
  const { asOf, gaps, pastGaps } = p;
  const rows = useMemo(() => dayRows(range, p, details), [range, p, details]);
  const promo = useMemo(() => (details ? spans(rows, "promo") : []), [rows, details]);
  const assumed = useMemo(() => (details ? spans(rows, "assumed") : []), [rows, details]);
  const holidays = details ? rows.filter((r) => r.holiday).map((r) => r.date) : [];
  const inRange = (d: string) => d >= rows[0].date && d <= rows[rows.length - 1].date;
  const monthAxis = range === "3m";

  return (
    <>
      <div className="chart-legend">
        <span><i className="swatch" style={{ background: "var(--series-actual)" }} />ยอดขายจริง</span>
        <span><i className="swatch dashed" />{range === "3m" ? "คาดการณ์ 3 เดือน" : "คาดการณ์ 14 วัน"}</span>
        <span><i className="swatch band" />ช่วงที่น่าจะเป็น</span>
        {gaps.length > 0 && <span><i className="swatch" style={{ background: "var(--bad)" }} />วันที่เงินอาจไม่พอ</span>}
        {details && <>
          <span><i className="swatch promo" />วันโปรโมชัน</span>
          {pastGaps.length > 0 && <span><i className="swatch dashed past-gap" />วันที่เงินเคยไม่พอ</span>}
          {range === "3m" && <span><i className="swatch synthetic" />ตารางโปรโมชันจำลอง</span>}
          <span><i className="swatch dashed simulated" />ยอดขายจำลอง (ไม่ใช่ข้อมูลจริง)</span>
        </>}
      </div>
      <div style={{ width: "100%", height: 300 }}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 18, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            {assumed.map(([a, b]) => (
              <ReferenceArea key={`as-${a}`} x1={a} x2={b} fill="var(--text-3)" fillOpacity={0.08} stroke="none" ifOverflow="hidden" />
            ))}
            {promo.map(([a, b]) => (
              <ReferenceArea key={a} x1={a} x2={b} fill="var(--series-promo)" fillOpacity={0.14} stroke="none" ifOverflow="hidden" />
            ))}
            {holidays.map((d) => <ReferenceLine key={d} x={d} stroke="var(--text-3)" strokeDasharray="2 3" />)}
            <XAxis dataKey="date" tickFormatter={monthAxis ? thaiMonthShort : thaiDateShort}
              ticks={monthAxis ? monthStarts(rows.map((r) => r.date)) : undefined}
              tick={{ fill: "var(--text-2)", fontSize: 12 }} axisLine={{ stroke: "var(--border)" }} tickLine={false}
              minTickGap={monthAxis ? 8 : 24} />
            <YAxis tickFormatter={(v: number) => money(v)} tick={{ fill: "var(--text-2)", fontSize: 12 }}
              axisLine={false} tickLine={false} width={64} />
            <Tooltip content={<DayTooltip />} />
            <Area dataKey="band" stroke="none" fill="var(--series-band)" fillOpacity={0.18} connectNulls isAnimationActive={false} />
            <Line dataKey="actual" stroke="var(--series-actual)" strokeWidth={1.8} dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="simulated" stroke="var(--text-3)" strokeWidth={1.4} strokeDasharray="6 3 1 3" dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="forecast" stroke="var(--series-forecast)" strokeWidth={2.2} strokeDasharray="6 4" dot={false} connectNulls isAnimationActive={false} />
            <ReferenceLine x={asOf} stroke="var(--text-3)" strokeDasharray="3 3"
              label={{ value: "วันนี้", position: "top", fill: "var(--text-2)", fontSize: 12 }} />
            {gaps.filter((g) => inRange(g.date)).map((g) => <ReferenceLine key={g.date} x={g.date} stroke="var(--bad)" strokeWidth={2} />)}
            {details && pastGaps.filter((g) => inRange(g.date)).map((g) => (
              <ReferenceLine key={`past-${g.date}`} x={g.date} stroke="var(--warn)" strokeWidth={2} strokeDasharray="4 3" />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

// --- Monthly bars (1 year) ---------------------------------------------------------

interface MonthRow {
  month: string;
  actual: number | null; // real sales (past months, and the current month up to today)
  forecast: number | null; // rest of the current month (14-day model) or seasonal outlook
  err: [number, number] | null; // outlook − lower, upper − outlook
  kind: "past" | "current" | "outlook";
}

function monthRows(p: Props): MonthRow[] {
  const { history, forecast, seasonal, asOf } = p;
  const thisMonth = asOf.slice(0, 7);
  const byMonth = new Map<string, { sum: number; days: number; missing: boolean }>();
  history.points.filter((h) => h.date <= asOf).forEach((h) => {
    const m = h.date.slice(0, 7);
    const v = byMonth.get(m) ?? { sum: 0, days: 0, missing: false };
    v.sum += h.sales ?? 0;
    v.days += 1;
    v.missing ||= h.sales == null;
    byMonth.set(m, v);
  });
  const rows: MonthRow[] = [];
  for (const [m, v] of byMonth) {
    if (m === thisMonth) continue;
    if (v.days < daysInMonth(m)) continue; // partial month at the start of the history
    rows.push({ month: m, actual: v.missing ? null : v.sum, forecast: null, err: null, kind: "past" });
  }
  const cur = byMonth.get(thisMonth);
  const rest = sum(forecast.points.filter((x) => x.date > asOf && x.date.startsWith(thisMonth)).map((x) => x.forecast));
  rows.push({ month: thisMonth, actual: cur ? cur.sum : null, forecast: rest, err: null, kind: "current" });
  seasonal.months.forEach((m) => rows.push({
    month: m.month, actual: null, forecast: m.outlook,
    err: m.outlook != null && m.lower != null && m.upper != null ? [m.outlook - m.lower, m.upper - m.outlook] : null,
    kind: "outlook",
  }));
  return rows;
}

function MonthTooltip({ active, payload }: { active?: boolean; payload?: { payload: MonthRow }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{thaiYearMonthLong(r.month)}</strong>
      {r.kind === "past" && (r.actual != null ? <div>ยอดขายจริง <b className="num">{money(r.actual)}</b></div> : <div className="muted">ข้อมูลไม่ครบ</div>)}
      {r.kind === "current" && <>
        <div>จริงถึงวันนี้ <b className="num">{money(r.actual ?? 0)}</b></div>
        <div>คาดการณ์ที่เหลือ <span className="num">{money(r.forecast ?? 0)}</span></div>
        <div className="muted">รวมประมาณ {money((r.actual ?? 0) + (r.forecast ?? 0))}</div>
      </>}
      {r.kind === "outlook" && (r.forecast != null ? <>
        <div>ภาพรวม <b className="num">{money(r.forecast)}</b></div>
        {r.err && <div className="muted">ช่วง {money(r.forecast - r.err[0])} – {money(r.forecast + r.err[1])}</div>}
        <div className="tooltip-tags" style={{ color: "var(--text-3)" }}>ตามฤดูกาล ไม่ใช่ผลโมเดล deep learning</div>
      </> : <div className="muted">ข้อมูลปีก่อนไม่พอ</div>)}
    </div>
  );
}

function MonthlyChart({ p }: { p: Props }) {
  const rows = useMemo(() => monthRows(p), [p]);
  return (
    <>
      <div className="chart-legend">
        <span><i className="swatch bar" style={{ background: "var(--series-actual)", opacity: 0.75 }} />ยอดขายจริงรายเดือน</span>
        <span><i className="swatch bar" style={{ background: "var(--series-forecast)", opacity: 0.55 }} />ภาพรวม 12 เดือนข้างหน้า (ขีดคือช่วงที่น่าจะเป็น)</span>
      </div>
      <div style={{ width: "100%", height: 300 }}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 18, right: 12, bottom: 0, left: 0 }} barCategoryGap="18%">
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="month" tickFormatter={thaiYearMonth} interval={0} tick={{ fill: "var(--text-2)", fontSize: 11 }}
              axisLine={{ stroke: "var(--border)" }} tickLine={false} />
            <YAxis tickFormatter={(v: number) => money(v)} tick={{ fill: "var(--text-2)", fontSize: 12 }}
              axisLine={false} tickLine={false} width={64} />
            <Tooltip content={<MonthTooltip />} cursor={{ fill: "var(--surface-2)" }} />
            <ReferenceLine x={p.asOf.slice(0, 7)} stroke="var(--text-3)" strokeDasharray="3 3"
              label={{ value: "เดือนนี้", position: "top", fill: "var(--text-2)", fontSize: 12 }} />
            <Bar dataKey="actual" stackId="m" fill="var(--series-actual)" fillOpacity={0.75} isAnimationActive={false} />
            <Bar dataKey="forecast" stackId="m" fill="var(--series-forecast)" fillOpacity={0.55} radius={[3, 3, 0, 0]} isAnimationActive={false}>
              {rows.map((r) => <Cell key={r.month} />)}
              <ErrorBar dataKey="err" width={5} strokeWidth={1.2} stroke="var(--series-forecast)" direction="y" />
            </Bar>
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

// --- Main ----------------------------------------------------------------------------

export function SalesChart(props: Props) {
  const [range, setRange] = useState<RangeKey>("3m");
  const [details, setDetails] = useState(false);

  return (
    <div>
      <div className="chart-toolbar">
        {range !== "1y" && (
          <button className={`btn chip${details ? " on" : ""}`} onClick={() => setDetails((d) => !d)} aria-pressed={details}>
            {details ? "ซ่อนรายละเอียด" : "แสดงรายละเอียด"}
          </button>
        )}
        <div className="toggle" role="tablist" aria-label="ช่วงเวลา">
          {RANGES.map((r) => (
            <button key={r.key} className={range === r.key ? "on" : ""} onClick={() => setRange(r.key)}>{r.label}</button>
          ))}
        </div>
      </div>
      <Summary range={range} p={props} />
      {range === "1y" ? <MonthlyChart p={props} /> : <DailyChart range={range} p={props} details={details} />}
      {details && range !== "1y" && (
        <p className="muted small chart-note">
          รายละเอียด: แถบเขียว = วันโปรโมชัน · เส้นประเทา = วันหยุดนักขัตฤกษ์ · หลังวันนี้แสดงยอดขายจริงถึง 31 ก.ค. 2558 (ข้อมูลจบแค่นั้น)
          แล้วต่อด้วย<b>ยอดขายจำลอง</b> (เส้นเทาจุดขีด ไม่ใช่ข้อมูลจริง ไม่ได้ใช้วัดความแม่นยำ)
          {range === "3m" && " · แรเงาเทา = ตารางโปรโมชันจำลองแบบเดียวกับปีก่อน"}
        </p>
      )}
      <Accuracy range={range} forecast={props.forecast} longForecast={props.longForecast}
        seasonal={props.seasonal} results={props.results} asOf={props.asOf} />
    </div>
  );
}
