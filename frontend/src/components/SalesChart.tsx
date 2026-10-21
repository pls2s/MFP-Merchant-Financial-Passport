import { useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { money, monthStarts, percent, thaiDate, thaiDateShort, thaiMonthShort, thaiWeekday } from "../format";
import type { Forecast, Gap, LongForecast, ModelResult, SalesHistory, SeasonalOutlook } from "../types";
import { ForecastAccuracy } from "./ForecastAccuracy";

/**
 * Each range uses its own method, all backtested on real sales:
 *   4w  — main LSTM+GRU, 14 days ahead
 *   3m  — the same models rolled forward 14 days at a time, 84 days ahead
 *   1y  — seasonal outlook per month (same month last year × trend), NOT a deep-learning forecast;
 *         drawn as the month's average per open day so it is comparable with the daily actuals
 */
const RANGES = [
  { key: "4w", label: "4 สัปดาห์", back: 28 },
  { key: "3m", label: "3 เดือน", back: 91 },
  { key: "1y", label: "1 ปี", back: 365 },
] as const;
type RangeKey = (typeof RANGES)[number]["key"];

interface Row {
  date: string;
  actual: number | null;
  predicted: number | null; // what the method forecast before the actual was known (backtest)
  forecast: number | null;
  band: [number, number] | null;
  open: boolean;
  promo: boolean;
  holiday: boolean;
  schoolHoliday: boolean;
  synthetic: boolean; // promo/open assumed from last year
  simulated: number | null; // synthetic sales after the real data ends (ข้อมูลจำลอง, never "actual")
  monthly: boolean; // value is a month's average per open day (1-year outlook)
}

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

const positive = (x: number | null | undefined) => (x != null && x > 0 ? x : null);
const DATA_END = "2015-07-31"; // last day of real Rossmann sales
const addDays = (iso: string, n: number) => new Date(Date.parse(`${iso}T00:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10);
const daysInMonth = (ym: string) => new Date(Date.UTC(Number(ym.slice(0, 4)), Number(ym.slice(5, 7)), 0)).getUTCDate();

function buildRows(range: RangeKey, p: Props, showFutureActual: boolean): Row[] {
  const { forecast, history, longForecast, seasonal, asOf } = p;
  const back = RANGES.find((r) => r.key === range)!.back;
  const from = addDays(asOf, -back + 1);
  const hist = new Map(history.points.map((h) => [h.date, h]));
  const main = new Map(forecast.points.map((x) => [x.date, x]));
  const long = new Map(longForecast.points.map((x) => [x.date, x]));
  const longBack = new Map(longForecast.backtest.points.map((x) => [x.date, x]));
  const outlook = new Map(seasonal.months.map((m) => [m.month, m]));
  const outlookBack = new Map(seasonal.backtest.months.map((m) => [m.month, m]));
  const simulated = new Map(history.synthetic.points.map((x) => [x.date, x.sales]));
  const lastMonth = seasonal.months[seasonal.months.length - 1].month;
  // Open days per month from the real calendar; a future month uses the same month a year earlier.
  const openDays = new Map<string, number>();
  history.points.forEach((h) => { if (h.open) openDays.set(h.date.slice(0, 7), (openDays.get(h.date.slice(0, 7)) ?? 0) + 1); });
  const perOpenDay = (ym: string, total: number) => {
    const lastYear = `${Number(ym.slice(0, 4)) - 1}${ym.slice(4)}`;
    const days = openDays.get(ym) && ym <= asOf.slice(0, 7) ? openDays.get(ym)! : openDays.get(lastYear) ?? daysInMonth(ym);
    return total / days;
  };

  // Date span: history back to `from`, forward to the end of the chosen method's horizon.
  const to = range === "4w" ? addDays(asOf, 14)
    : range === "3m" ? longForecast.points[longForecast.points.length - 1].date
    : `${lastMonth}-${daysInMonth(lastMonth)}`;
  const rows: Row[] = [];
  for (let d = from; d <= to; d = addDays(d, 1)) {
    const h = hist.get(d);
    const future = d > asOf;
    const row: Row = {
      date: d, actual: null, predicted: null, forecast: null, band: null,
      open: h?.open ?? true, promo: h?.promo ?? false, holiday: h?.holiday ?? false,
      schoolHoliday: h?.school_holiday ?? false, synthetic: !h, monthly: false, simulated: null,
    };
    if (!future) row.actual = positive(h?.sales);
    else if (showFutureActual && d <= DATA_END) row.actual = positive(main.get(d)?.actual);
    else if (showFutureActual) row.simulated = positive(simulated.get(d));

    if (range === "4w") {
      const m = main.get(d);
      if (!future) row.predicted = positive(m?.forecast);
      else if (m && positive(m.forecast) && m.lower != null && m.upper != null) {
        row.forecast = m.forecast;
        row.band = [m.lower, m.upper];
      }
    } else if (range === "3m") {
      if (!future) row.predicted = positive(longBack.get(d)?.forecast);
      const l = long.get(d);
      if (future && l && positive(l.forecast)) {
        row.forecast = l.forecast;
        row.band = [l.lower, l.upper];
        row.synthetic = l.synthetic_inputs;
      }
    } else {
      const ym = d.slice(0, 7);
      const b = outlookBack.get(ym);
      if (!future && b?.outlook != null) { row.predicted = perOpenDay(ym, b.outlook); row.monthly = true; }
      const o = outlook.get(ym);
      if (future && o?.outlook != null && o.lower != null && o.upper != null) {
        row.forecast = perOpenDay(ym, o.outlook);
        row.band = [perOpenDay(ym, o.lower), perOpenDay(ym, o.upper)];
        row.monthly = true;
      } else if (future) {
        const m = main.get(d); // the days before the first outlook month
        if (m && positive(m.forecast)) row.forecast = m.forecast;
      }
    }
    if (d === asOf && row.actual != null) row.forecast = row.actual; // join the lines at "today"
    rows.push(row);
  }
  return rows;
}

/** Consecutive days with `key` set → [start, end] spans for shading. */
function spans(rows: Row[], key: "promo" | "synthetic"): [string, string][] {
  const out: [string, string][] = [];
  rows.forEach((r, i) => {
    if (!r[key]) return;
    if (i > 0 && rows[i - 1][key]) out[out.length - 1][1] = r.date;
    else out.push([r.date, r.date]);
  });
  return out;
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { payload: Row }[]; label?: string }) {
  if (!active || !payload?.length || !label) return null;
  const r = payload[0].payload;
  const unit = r.monthly ? " (เฉลี่ยต่อวันที่เปิดร้านของเดือน)" : "";
  const err = r.actual != null && r.predicted != null && !r.monthly ? (r.predicted - r.actual) / r.actual : null;
  const tags = [
    !r.open && "ร้านปิด",
    r.promo && "มีโปรโมชัน",
    r.holiday && "วันหยุดนักขัตฤกษ์",
    r.schoolHoliday && "ปิดเทอม",
    r.synthetic && r.forecast != null && !r.monthly && "ตารางโปรโมชันจำลอง",
  ].filter(Boolean);
  return (
    <div className="chart-tooltip">
      <strong>{thaiWeekday(label)} {thaiDate(label)}</strong>
      {r.actual != null && <div>ยอดขายจริง <b className="num">{money(r.actual)}</b></div>}
      {r.simulated != null && (
        <div>ยอดขายจำลอง <span className="num">{money(r.simulated)}</span> <span className="muted">(ไม่ใช่ข้อมูลจริง)</span></div>
      )}
      {r.predicted != null && (
        <div>
          ทายไว้ล่วงหน้า <span className="num">{money(r.predicted)}</span>{unit}
          {err != null && <span className="muted"> (คลาด {err >= 0 ? "+" : ""}{(err * 100).toFixed(1)}%)</span>}
        </div>
      )}
      {r.forecast != null && r.band && <div>คาดการณ์ <b className="num">{money(r.forecast)}</b>{unit}</div>}
      {r.band && <div className="muted">ช่วง {money(r.band[0])} – {money(r.band[1])}</div>}
      {tags.length > 0 && <div className="tooltip-tags">{tags.join(" · ")}</div>}
    </div>
  );
}

function LongAccuracy({ range, longForecast, seasonal }: { range: "3m" | "1y"; longForecast: LongForecast; seasonal: SeasonalOutlook }) {
  if (range === "3m") {
    const bt = longForecast.backtest;
    return (
      <div className="accuracy">
        <div className="accuracy-head">
          <strong>ทาย 3 เดือนแม่นแค่ไหน</strong>
          <span className="muted small">
            ทดสอบย้อนหลัง: ให้โมเดลทายต่อเนื่อง {bt.days} วันจาก {thaiDate(bt.origin)} (วันสุดท้ายของข้อมูลเทรน)
            แล้วเทียบกับยอดขายจริง — เส้นสีส้มในกราฟ
          </span>
        </div>
        <div className="accuracy-grid">
          <div>
            <div className="stat-label">คลาดเคลื่อนเฉลี่ย (ร้านนี้)</div>
            <div className="accuracy-value num">{bt.wape_store != null ? percent(bt.wape_store, 1) : "—"}</div>
            <div className="stat-sub">เฉลี่ยทุกร้าน {percent(bt.wape_all_stores, 1)}</div>
          </div>
          <div className="span-2">
            <div className="stat-label">ยิ่งทายไกลยิ่งคลาด (ทุกร้าน)</div>
            <div className="block-bars">
              {Object.entries(bt.wape_by_block).map(([k, v]) => (
                <div key={k} className="block-bar">
                  <span className="num">{percent(v, 1)}</span>
                  <div style={{ height: `${Math.min(v / 0.12, 1) * 48}px` }} />
                  <span className="muted">วัน {k}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <p className="disclaimer">
          42 วันแรกของการทดสอบเป็นช่วงที่ใช้เลือก epoch ตอนเทรน ตัวเลขช่วงนั้นจึงอาจดีเกินจริงเล็กน้อย ·
          หลัง 31 ก.ค. 2558 ใช้ตารางโปรโมชันจำลองแบบเดียวกับปีก่อน (แรเงาเทา) · แถบช่วงคาดการณ์ปรับจากผลทดสอบชุดเดียวกัน
        </p>
      </div>
    );
  }
  const bt = seasonal.backtest;
  const missing = seasonal.months.filter((m) => m.outlook == null).length;
  return (
    <div className="accuracy">
      <div className="accuracy-head">
        <strong>ภาพรวม 1 ปี <span className="badge">ไม่ใช่ผลโมเดล deep learning</span></strong>
        <span className="muted small">
          ยอดแต่ละเดือน = ยอดเดือนเดียวกันปีก่อน × การเปลี่ยนแปลงของ 12 สัปดาห์ล่าสุดเทียบปีก่อน ·
          ทดสอบย้อนหลัง 12 เดือนจาก {thaiDate(bt.origin)} — เส้นสีส้มในกราฟ
        </span>
      </div>
      <div className="accuracy-grid">
        <div>
          <div className="stat-label">คลาดเคลื่อนเฉลี่ยรายเดือน (ร้านนี้)</div>
          <div className="accuracy-value num">{bt.wape_store != null ? percent(bt.wape_store, 1) : "—"}</div>
          <div className="stat-sub">เฉลี่ยทุกร้าน {percent(bt.wape_all_stores, 1)}</div>
        </div>
        <div className="span-2">
          <div className="stat-label">อ่านอย่างไร</div>
          <div className="stat-sub" style={{ marginTop: 4 }}>
            วัดเป็นยอดรายเดือน จึงคลาดน้อยกว่ายอดรายวันโดยธรรมชาติ เทียบกับตัวเลข 14 วันตรง ๆ ไม่ได้ ·
            เส้นในกราฟคือยอดเฉลี่ยต่อวันที่เปิดร้านของแต่ละเดือน
            {missing > 0 && ` · ${missing} เดือนข้อมูลปีก่อนไม่พอ จึงไม่มีภาพรวม`}
          </div>
        </div>
      </div>
    </div>
  );
}

export function SalesChart(props: Props) {
  const { forecast, results, asOf, gaps, pastGaps, longForecast, seasonal } = props;
  const [range, setRange] = useState<RangeKey>("3m");
  const [showFutureActual, setShowFutureActual] = useState(true);
  const rows = useMemo(() => buildRows(range, props, showFutureActual), [range, props, showFutureActual]);
  const promo = useMemo(() => spans(rows, "promo"), [rows]);
  // Only the 3-month rollout uses the assumed promo calendar.
  const synthetic = useMemo(() => (range === "3m" ? spans(rows, "synthetic").filter(([a]) => a > asOf) : []), [rows, asOf, range]);
  const holidays = rows.filter((r) => r.holiday).map((r) => r.date);
  const monthAxis = range !== "4w";
  const inRange = (d: string) => rows.length > 0 && d >= rows[0].date && d <= rows[rows.length - 1].date;

  return (
    <div>
      <div className="chart-toolbar">
        <div className="toggle" role="tablist" aria-label="ช่วงเวลา">
          {RANGES.map((r) => (
            <button key={r.key} className={range === r.key ? "on" : ""} onClick={() => setRange(r.key)}>{r.label}</button>
          ))}
        </div>
      </div>
      <div className="chart-legend">
        <span><i className="swatch" style={{ background: "var(--series-actual)" }} />ยอดขายจริง</span>
        <span><i className="swatch" style={{ background: "var(--series-predicted)" }} />ทายไว้ล่วงหน้า (ทดสอบย้อนหลัง)</span>
        {showFutureActual && range !== "4w" && <span><i className="swatch dashed simulated" />ยอดขายจำลอง (ไม่ใช่ข้อมูลจริง)</span>}
        <span><i className="swatch dashed" />{range === "1y" ? "ภาพรวมรายเดือน (เฉลี่ยต่อวันที่เปิดร้าน)" : range === "3m" ? "คาดการณ์ 3 เดือน" : "คาดการณ์ 14 วัน"}</span>
        <span><i className="swatch band" />ช่วงคาดการณ์โดยประมาณ</span>
        <span><i className="swatch promo" />วันโปรโมชัน</span>
        {range === "3m" && <span><i className="swatch synthetic" />ตารางโปรโมชันจำลอง</span>}
        <span><i className="swatch" style={{ background: "var(--bad)" }} />วันที่เงินอาจไม่พอ</span>
        {pastGaps.length > 0 && <span><i className="swatch dashed past-gap" />วันที่เงินเคยไม่พอ</span>}
      </div>
      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 18, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            {synthetic.map(([a, b]) => (
              <ReferenceArea key={`syn-${a}`} x1={a} x2={b} fill="var(--text-3)" fillOpacity={0.08} stroke="none" ifOverflow="hidden" />
            ))}
            {promo.map(([a, b]) => (
              <ReferenceArea key={a} x1={a} x2={b} fill="var(--series-promo)" fillOpacity={0.14} stroke="none" ifOverflow="hidden" />
            ))}
            {holidays.map((d) => <ReferenceLine key={d} x={d} stroke="var(--text-3)" strokeDasharray="2 3" />)}
            <XAxis
              dataKey="date"
              tickFormatter={monthAxis ? thaiMonthShort : thaiDateShort}
              ticks={monthAxis ? monthStarts(rows.map((r) => r.date)) : undefined}
              tick={{ fill: "var(--text-2)", fontSize: 12 }}
              axisLine={{ stroke: "var(--border)" }}
              tickLine={false}
              minTickGap={monthAxis ? 8 : 24}
            />
            <YAxis tickFormatter={(v: number) => money(v)} tick={{ fill: "var(--text-2)", fontSize: 12 }}
              axisLine={false} tickLine={false} width={64} />
            <Tooltip content={<ChartTooltip />} />
            <Area dataKey="band" stroke="none" fill="var(--series-band)" fillOpacity={0.16} connectNulls
              type={range === "1y" ? "stepAfter" : "linear"} isAnimationActive={false} />
            <Line dataKey="actual" stroke="var(--series-actual)" strokeWidth={range === "1y" ? 1 : 1.6} dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="simulated" stroke="var(--text-3)" strokeWidth={range === "1y" ? 1 : 1.4} strokeDasharray="6 3 1 3"
              dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="predicted" stroke="var(--series-predicted)" strokeWidth={range === "1y" ? 2 : 1.6}
              type={range === "1y" ? "stepAfter" : "linear"} dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="forecast" stroke="var(--series-forecast)" strokeWidth={2} strokeDasharray="6 4"
              type={range === "1y" ? "stepAfter" : "linear"} dot={false} connectNulls isAnimationActive={false} />
            <ReferenceLine x={asOf} stroke="var(--text-3)" strokeDasharray="3 3"
              label={{ value: "วันนี้", position: "top", fill: "var(--text-2)", fontSize: 12 }} />
            {gaps.filter((g) => inRange(g.date)).map((g) => <ReferenceLine key={g.date} x={g.date} stroke="var(--bad)" strokeWidth={2} />)}
            {pastGaps.filter((g) => inRange(g.date)).map((g) => (
              <ReferenceLine key={`past-${g.date}`} x={g.date} stroke="var(--warn)" strokeWidth={2} strokeDasharray="4 3" />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small chart-note">
        เส้นสีส้มคือสิ่งที่วิธีพยากรณ์ของช่วงนี้ทายไว้ล่วงหน้าโดยยังไม่เห็นยอดขายจริง แล้วเทียบกับเส้นดำ ·
        เส้นประแนวตั้งสีเทาคือวันหยุดนักขัตฤกษ์ · ชี้ที่กราฟเพื่อดูรายละเอียดรายวัน
      </p>
      <label className="check">
        <input type="checkbox" checked={showFutureActual} onChange={(e) => setShowFutureActual(e.target.checked)} />
        แสดงยอดขายหลังวันนี้ — ยอดจริงถึง 31 ก.ค. 2558 (ข้อมูลจบแค่นั้น) และ<b>ยอดขายจำลอง</b>หลังจากนั้น
        (ไม่ใช่ข้อมูลจริง ไม่ได้ใช้วัดความแม่นยำ)
      </label>
      {range === "4w"
        ? <ForecastAccuracy forecast={forecast} asOf={asOf} results={results} />
        : <LongAccuracy range={range} longForecast={longForecast} seasonal={seasonal} />}
    </div>
  );
}
