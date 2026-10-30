import { useMemo, useState, type ReactNode } from "react";
import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  Line,
  ComposedChart,
  ErrorBar,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  addDays, change, compact, daysInMonth, money, monthStarts, pillRows, thaiDate, thaiDateShort, thaiMonthShort,
  thaiWeekday, thaiYearMonth, thaiYearMonthLong,
} from "../format";
import type { Forecast, Gap, LongForecast, ModelResult, SalesHistory, SeasonalOutlook } from "../types";
import { Accuracy } from "./Accuracy";
import { GapPill } from "./GapMarker";
import { RANGES, type RangeKey, type SalesLayer } from "./chartOptions";
import { DataTable, Disclosure, LegendChip, Swatch, type ViewMode } from "./ui";

/**
 * Sales chart, simple by default. Daily views draw a solid actual line and a dashed forecast line that
 * break on closed days (never drop to zero); the forecast band sits faintly behind them.
 *   4w — actual + main LSTM+GRU 14-day forecast
 *   3m — actual + the same models rolled forward 84 days
 *   1y — monthly bars: last 12 months actual, next 12 months seasonal outlook (NOT deep learning)
 * Range and layers come from the page; each layer (promo days, holidays, past
 * shortfalls, real sales after today, synthetic sales after the data ends) toggles on its own.
 * Backtests live in <Accuracy>, below the chart.
 */

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
    const months = seasonal.months.filter((m) => m.backtested && m.outlook != null);
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
  actual: number | null; // real sales up to today (bar)
  laterActual: number | null; // real sales after today, up to the data end (line over the forecast bars) — details only
  forecast: number | null;
  band: [number, number] | null;
  simulated: number | null; // synthetic sales after the data ends (ข้อมูลจำลอง) — details only
  open: boolean;
  promo: boolean;
  holiday: boolean;
  schoolHoliday: boolean;
  assumed: boolean; // promo/open calendar assumed from last year (3-month rollout)
}

function dayRows(range: "4w" | "3m", p: Props, layers: ReadonlySet<SalesLayer>): DayRow[] {
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
      date: d, actual: null, laterActual: null, forecast: null, band: null, simulated: null,
      open: h?.open ?? true, promo: h?.promo ?? false, holiday: h?.holiday ?? false,
      schoolHoliday: h?.school_holiday ?? false, assumed: range === "3m" && d > DATA_END,
    };
    if (!future) row.actual = positive(h?.sales);
    else if (d <= DATA_END) row.laterActual = layers.has("laterActual") ? positive(main.get(d)?.actual) : null;
    else if (layers.has("simulated")) row.simulated = positive(simulated.get(d));
    // join the two lines: the simulated line starts from the last real day
    if (layers.has("simulated") && layers.has("laterActual") && d === DATA_END) row.simulated = row.laterActual;
    if (future && f && positive(f.forecast) && f.lower != null && f.upper != null) {
      row.forecast = f.forecast;
      row.band = [f.lower, f.upper];
    }
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
      {r.laterActual != null && <div>ยอดขายจริง <b className="num">{money(r.laterActual)}</b></div>}
      {r.simulated != null && <div>ยอดขายจำลอง <span className="num">{money(r.simulated)}</span> <span className="muted">(ไม่ใช่ข้อมูลจริง)</span></div>}
      {r.band && r.forecast != null && <div>คาดการณ์ <b className="num">{money(r.forecast)}</b></div>}
      {r.band && <div className="muted">ช่วง {money(r.band[0])} – {money(r.band[1])}</div>}
      {tags.length > 0 && <div className="tooltip-tags">{tags.join(" · ")}</div>}
    </div>
  );
}

function DailyTable({ rows, gaps }: { rows: DayRow[]; gaps: Gap[] }) {
  const gapAt = new Map(gaps.map((g) => [g.date, g]));
  return (
    <DataTable
      columns={[
        { key: "date", label: "วันที่", align: "left" },
        { key: "actual", label: "ยอดขายจริง" },
        { key: "forecast", label: "คาดการณ์" },
        { key: "band", label: "ช่วงคาดการณ์โดยประมาณ" },
        { key: "extra", label: "ยอดจริง/จำลอง หลังวันนี้" },
        { key: "tags", label: "หมายเหตุ", align: "left" },
      ]}
      rows={rows.map((r) => {
        const g = gapAt.get(r.date);
        const tags = [!r.open && "ร้านปิด", r.promo && "โปรโมชัน", r.holiday && "วันหยุด", r.schoolHoliday && "ปิดเทอม",
          r.assumed && "ตารางโปรโมชันจำลอง", g && `⚠ เงินอาจไม่พอ ขาด ${money(g.shortfall)}`].filter(Boolean);
        return {
          date: `${thaiWeekday(r.date).replace("วัน", "")} ${thaiDate(r.date)}`,
          actual: r.actual != null ? money(r.actual) : null,
          forecast: r.forecast != null ? money(r.forecast) : null,
          band: r.band ? `${money(r.band[0])} – ${money(r.band[1])}` : null,
          extra: r.laterActual != null ? `จริง ${money(r.laterActual)}` : r.simulated != null ? `จำลอง ${money(r.simulated)}` : null,
          tags: tags.join(" · ") || null,
        };
      })}
      highlight={(i) => (gapAt.has(rows[i].date) ? "bad" : !rows[i].open ? "muted" : undefined)}
    />
  );
}

type DailySeries = "actual" | "forecast" | "band";

function DailyChart({ range, p, layers, view }: { range: "4w" | "3m"; p: Props; layers: ReadonlySet<SalesLayer>; view: ViewMode }) {
  const { asOf, gaps, pastGaps } = p;
  const [hidden, setHidden] = useState<ReadonlySet<DailySeries>>(new Set());
  const toggle = (k: DailySeries) => setHidden((h) => {
    const next = new Set(h);
    if (!next.delete(k)) next.add(k);
    return next;
  });
  const rows = useMemo(() => dayRows(range, p, layers), [range, p, layers]);
  const promo = useMemo(() => (layers.has("promo") ? spans(rows, "promo") : []), [rows, layers]);
  const assumed = useMemo(() => (layers.has("promo") ? spans(rows, "assumed") : []), [rows, layers]);
  const holidays = layers.has("holiday") ? rows.filter((r) => r.holiday).map((r) => r.date) : [];
  const inRange = (d: string) => d >= rows[0].date && d <= rows[rows.length - 1].date;
  const monthAxis = range === "3m";
  const dates = rows.map((r) => r.date);
  const shown = gaps.filter((g) => inRange(g.date));
  const gapDays = new Set(shown.map((g) => g.date));
  const pills = pillRows(shown.map((g) => g.date), dates, range === "3m" ? 25 : 8);

  if (view === "table") return <DailyTable rows={rows} gaps={shown} />;

  // Lines break on closed days, so a day with closed days on both sides needs a dot to be visible at all.
  const dayDot = (key: "actual" | "forecast", color: string) => (d: { cx?: number; cy?: number; index?: number; payload?: DayRow }) => {
    const i = d.index ?? 0;
    const isGap = key === "forecast" && d.payload != null && gapDays.has(d.payload.date);
    const alone = rows[i - 1]?.[key] == null && rows[i + 1]?.[key] == null;
    if (d.cx == null || d.cy == null || d.payload?.[key] == null || (!isGap && !alone)) return <g key={i} />;
    return <circle key={i} cx={d.cx} cy={d.cy} r={isGap ? 4.5 : 2.5} fill={isGap ? "var(--bad)" : color} stroke="none" />;
  };

  return (
    <>
      <div className="chart-legend">
        <LegendChip on={!hidden.has("actual")} onClick={() => toggle("actual")}><Swatch kind="line" color="var(--series-actual)" />ยอดขายจริง</LegendChip>
        <LegendChip on={!hidden.has("forecast")} onClick={() => toggle("forecast")}><Swatch kind="line" color="var(--series-forecast)" dashed />{range === "3m" ? "คาดการณ์ 3 เดือน" : "คาดการณ์ 14 วัน"}</LegendChip>
        <LegendChip on={!hidden.has("band")} onClick={() => toggle("band")}><Swatch kind="area" color="var(--series-band)" />ช่วงคาดการณ์โดยประมาณ</LegendChip>
        {gaps.length > 0 && <span><Swatch kind="line" color="var(--bad)" dashed />⚠ วันที่เงินอาจไม่พอ</span>}
        {layers.has("promo") && <span><Swatch kind="area" color="var(--series-promo)" />วันโปรโมชัน</span>}
        {layers.has("promo") && range === "3m" && <span><Swatch kind="area" color="var(--text-3)" />ตารางโปรโมชันจำลอง</span>}
        {layers.has("holiday") && <span><Swatch kind="line" color="var(--text-3)" dashed />วันหยุดนักขัตฤกษ์</span>}
        {layers.has("pastGaps") && pastGaps.length > 0 && <span><Swatch kind="line" color="var(--warn)" dashed />วันที่เงินเคยไม่พอ</span>}
        {layers.has("laterActual") && <span><Swatch kind="line" color="var(--series-actual)" />ยอดจริงหลังวันนี้ (ถึง 31 ก.ค.)</span>}
        {layers.has("simulated") && <span><Swatch kind="line" color="var(--series-simulated)" dashed />ยอดขายจำลอง (ไม่ใช่ข้อมูลจริง)</span>}
        <span className="muted">เส้นขาด = ร้านปิด</span>
      </div>
      <div style={{ width: "100%", height: 320 }} role="img" aria-label={`กราฟยอดขายจริงและคาดการณ์ ${range === "3m" ? "3 เดือน" : "4 สัปดาห์"}${shown[0] ? ` ระวังวันที่ ${thaiDate(shown[0].date)} เงินสดอาจไม่พอ ขาดประมาณ ${money(shown[0].shortfall)}` : ""}`}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 18, right: 12, bottom: 0, left: 0 }}>
            {/* top headroom so the warning pills do not sit on the lines */}
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
              tick={{ fill: "var(--text-3)", fontSize: 12, fontWeight: 500 }} axisLine={{ stroke: "var(--border)" }} tickLine={false}
              minTickGap={monthAxis ? 8 : 24} />
            <YAxis tickFormatter={compact} tick={{ fill: "var(--text-3)", fontSize: 12, fontWeight: 500 }}
              axisLine={false} tickLine={false} width={48}
              domain={[0, (max: number) => Math.ceil((max * (shown.length ? 1.3 : 1.05)) / 1000) * 1000]} />
            <Tooltip content={<DayTooltip />} cursor={{ stroke: "var(--border-strong)" }} />
            <Area dataKey="band" hide={hidden.has("band")} stroke="none" fill="var(--series-band)" fillOpacity={0.16} connectNulls isAnimationActive={false} />
            <Line dataKey="actual" hide={hidden.has("actual")} stroke="var(--series-actual)" strokeWidth={2} connectNulls={false}
              dot={dayDot("actual", "var(--series-actual)")} activeDot={{ r: 4 }} isAnimationActive={false} />
            <Line dataKey="forecast" hide={hidden.has("forecast")} stroke="var(--series-forecast)" strokeWidth={2} strokeDasharray="6 4" connectNulls={false}
              dot={dayDot("forecast", "var(--series-forecast)")} activeDot={{ r: 4 }} isAnimationActive={false} />
            {/* Details: what actually happened (real, then synthetic) over the forecast. */}
            <Line dataKey="laterActual" stroke="var(--series-actual)" strokeWidth={2} connectNulls
              dot={{ r: 2.5, fill: "var(--series-actual)", stroke: "none" }} isAnimationActive={false} />
            <Line dataKey="simulated" stroke="var(--series-simulated)" strokeWidth={2} strokeDasharray="8 3 2 3" connectNulls
              dot={range === "4w" ? { r: 2.5, fill: "var(--series-simulated)", stroke: "none" } : false} isAnimationActive={false} />
            <ReferenceLine x={asOf} stroke="var(--text-3)" strokeDasharray="3 3"
              label={{ value: "วันนี้", position: "top", fill: "var(--text-3)", fontSize: 12 }} />
            {shown.map((g, i) => (
              <ReferenceLine key={g.date} x={g.date} stroke="var(--bad)" strokeWidth={1.5} strokeDasharray="3 3"
                label={{ content: <GapPill gap={g} row={pills[i]} flip={dates.indexOf(g.date) > dates.length * 0.5} /> }} />
            ))}
            {layers.has("pastGaps") && pastGaps.filter((g) => inRange(g.date)).map((g) => (
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
  seasonal.months.filter((m) => m.backtested).forEach((m) => rows.push({
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

function MonthlyChart({ p, view }: { p: Props; view: ViewMode }) {
  const rows = useMemo(() => monthRows(p), [p]);
  if (view === "table") {
    return (
      <DataTable
        columns={[
          { key: "month", label: "เดือน", align: "left" },
          { key: "actual", label: "ยอดขายจริง" },
          { key: "forecast", label: "คาดการณ์ / ภาพรวม" },
          { key: "range", label: "ช่วงคาดการณ์โดยประมาณ" },
          { key: "kind", label: "ที่มา", align: "left" },
        ]}
        rows={rows.map((r) => ({
          month: thaiYearMonthLong(r.month),
          actual: r.actual != null ? money(r.actual) : r.kind === "past" ? "ข้อมูลไม่ครบ" : null,
          forecast: r.forecast != null ? money(r.forecast) : r.kind === "outlook" ? "ข้อมูลปีก่อนไม่พอ" : null,
          range: r.err && r.forecast != null ? `${money(r.forecast - r.err[0])} – ${money(r.forecast + r.err[1])}` : null,
          kind: r.kind === "past" ? "ยอดจริง" : r.kind === "current" ? "จริงถึงวันนี้ + คาดการณ์ 14 วัน" : "ตามฤดูกาล (ไม่ใช่ deep learning)",
        }))}
        highlight={(i) => (rows[i].kind === "outlook" ? "muted" : undefined)}
      />
    );
  }
  return (
    <>
      <div className="chart-legend">
        <span><Swatch kind="bar" color="var(--series-actual)" />ยอดขายจริงรายเดือน</span>
        <span><Swatch kind="bar" color="var(--series-forecast)" opacity={0.35} />ภาพรวม 12 เดือนข้างหน้า (ขีดคือช่วงคาดการณ์โดยประมาณ)</span>
      </div>
      <div style={{ width: "100%", height: 320 }} role="img" aria-label="กราฟแท่งยอดขายจริงรายเดือนและภาพรวม 12 เดือนข้างหน้า">
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 18, right: 12, bottom: 0, left: 0 }} barCategoryGap="18%">
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="month" tickFormatter={thaiYearMonth} interval={0} tick={{ fill: "var(--text-3)", fontSize: 11, fontWeight: 500 }}
              axisLine={{ stroke: "var(--border)" }} tickLine={false} />
            <YAxis tickFormatter={compact} tick={{ fill: "var(--text-3)", fontSize: 12, fontWeight: 500 }}
              axisLine={false} tickLine={false} width={48} />
            <Tooltip content={<MonthTooltip />} cursor={{ fill: "var(--surface-2)" }} />
            <ReferenceLine x={p.asOf.slice(0, 7)} stroke="var(--text-3)" strokeDasharray="3 3"
              label={{ value: "เดือนนี้", position: "top", fill: "var(--text-3)", fontSize: 12 }} />
            <Bar dataKey="actual" stackId="m" fill="var(--series-actual)" isAnimationActive={false} />
            <Bar dataKey="forecast" stackId="m" fill="var(--series-forecast)" fillOpacity={0.35} radius={[3, 3, 0, 0]} isAnimationActive={false}>
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

export function SalesChart({ range, layers, view, details, ...props }: Props & {
  range: RangeKey;
  layers: ReadonlySet<SalesLayer>;
  view: ViewMode;
  details?: ReactNode;
}) {
  const [showAccuracy, setShowAccuracy] = useState(false);
  const daily = range !== "1y";
  const notes = [
    daily && layers.has("laterActual") && <>หลังวันนี้ เส้นทึบมีจุด = ยอดขายจริงถึง 31 ก.ค. 2558 (ข้อมูลจบแค่นั้น)</>,
    daily && layers.has("simulated") && <>เส้นเทาจุดขีด = <b>ยอดขายจำลอง</b> หลังข้อมูลจริงจบ (ไม่ใช่ข้อมูลจริง ไม่ได้ใช้วัดความแม่นยำ)</>,
    daily && range === "3m" && layers.has("promo") && <>แรเงาเทา = ตารางโปรโมชันจำลองแบบเดียวกับปีก่อน</>,
  ].filter(Boolean);

  return (
    <div>
      <Summary range={range} p={props} />
      {daily
        ? <DailyChart range={range} p={props} layers={layers} view={view} />
        : <MonthlyChart p={props} view={view} />}
      {details}
      {notes.length > 0 && (
        <p className="muted small chart-note">
          {notes.map((n, i) => <span key={i}>{i > 0 && " · "}{n}</span>)}
        </p>
      )}
      <Disclosure open={showAccuracy} onToggle={() => setShowAccuracy((s) => !s)}>โมเดลทายร้านนี้แม่นแค่ไหน</Disclosure>
      {showAccuracy && (
        <Accuracy range={range} forecast={props.forecast} longForecast={props.longForecast}
          seasonal={props.seasonal} results={props.results} asOf={props.asOf} />
      )}
    </div>
  );
}
