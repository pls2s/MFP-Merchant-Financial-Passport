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
import { money, thaiDate, thaiDateShort, thaiMonthShort, thaiWeekday } from "../format";
import type { Forecast, Gap, SalesHistory } from "../types";

const RANGES = [
  { key: "4w", label: "4 สัปดาห์", days: 28 },
  { key: "3m", label: "3 เดือน", days: 91 },
  { key: "1y", label: "1 ปี", days: 365 },
] as const;
type RangeKey = (typeof RANGES)[number]["key"];

interface Row {
  date: string;
  actual: number | null;
  predicted: number | null; // forecast made before the actual was known (past days)
  forecast: number | null; // forecast for the coming days
  band: [number, number] | null;
  open: boolean;
  promo: boolean;
  holiday: boolean;
  schoolHoliday: boolean;
}

const positive = (x: number | null | undefined) => (x != null && x > 0 ? x : null);

function buildRows(history: SalesHistory, forecast: Forecast, asOf: string, days: number, showFutureActual: boolean): Row[] {
  const fc = new Map(forecast.points.map((p) => [p.date, p]));
  const start = new Date(`${asOf}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - days + 1);
  const from = start.toISOString().slice(0, 10);

  return history.points
    .filter((h) => h.date >= from)
    .map((h) => {
      const p = fc.get(h.date);
      const future = h.date > asOf;
      return {
        date: h.date,
        actual: future ? (showFutureActual ? positive(p?.actual) : null) : positive(h.sales),
        predicted: !future ? positive(p?.forecast) : null,
        // The forecast line starts at "today" so it joins the actual line.
        forecast: future ? positive(p?.forecast) : h.date === asOf ? positive(h.sales) : null,
        band: future && positive(p?.forecast) && p?.lower != null && p?.upper != null ? [p.lower, p.upper] : null,
        open: h.open,
        promo: h.promo,
        holiday: h.holiday,
        schoolHoliday: h.school_holiday,
      };
    });
}

/** Consecutive promo days → [start, end] spans for shading. */
function promoSpans(rows: Row[]): [string, string][] {
  const spans: [string, string][] = [];
  rows.forEach((r, i) => {
    if (!r.promo) return;
    if (i > 0 && rows[i - 1].promo) spans[spans.length - 1][1] = r.date;
    else spans.push([r.date, r.date]);
  });
  return spans;
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { payload: Row }[]; label?: string }) {
  if (!active || !payload?.length || !label) return null;
  const r = payload[0].payload;
  const err = r.actual != null && r.predicted != null ? (r.predicted - r.actual) / r.actual : null;
  const tags = [
    !r.open && "ร้านปิด",
    r.promo && "มีโปรโมชัน",
    r.holiday && "วันหยุดนักขัตฤกษ์",
    r.schoolHoliday && "ปิดเทอม",
  ].filter(Boolean);
  return (
    <div className="chart-tooltip">
      <strong>{thaiWeekday(label)} {thaiDate(label)}</strong>
      {r.actual != null && <div>ยอดขายจริง <b className="num">{money(r.actual)}</b></div>}
      {r.predicted != null && (
        <div>
          โมเดลทายไว้ <span className="num">{money(r.predicted)}</span>
          {err != null && <span className="muted"> (คลาด {err >= 0 ? "+" : ""}{(err * 100).toFixed(1)}%)</span>}
        </div>
      )}
      {r.band && r.forecast != null && <div>คาดการณ์ <b className="num">{money(r.forecast)}</b></div>}
      {r.band && <div className="muted">ช่วง {money(r.band[0])} – {money(r.band[1])}</div>}
      {tags.length > 0 && <div className="tooltip-tags">{tags.join(" · ")}</div>}
    </div>
  );
}

export function SalesChart({ forecast, history, asOf, gaps }: {
  forecast: Forecast;
  history: SalesHistory;
  asOf: string;
  gaps: Gap[];
}) {
  const [range, setRange] = useState<RangeKey>("3m");
  const [showFutureActual, setShowFutureActual] = useState(false);
  const days = RANGES.find((r) => r.key === range)!.days;
  const rows = useMemo(
    () => buildRows(history, forecast, asOf, days, showFutureActual),
    [history, forecast, asOf, days, showFutureActual],
  );
  const spans = useMemo(() => promoSpans(rows), [rows]);
  const holidays = rows.filter((r) => r.holiday).map((r) => r.date);
  const long = range === "1y";

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
        <span><i className="swatch" style={{ background: "var(--series-predicted)" }} />โมเดลทายไว้ล่วงหน้า</span>
        <span><i className="swatch dashed" />คาดการณ์ 14 วันข้างหน้า</span>
        <span><i className="swatch band" />ช่วงคาดการณ์โดยประมาณ</span>
        <span><i className="swatch promo" />วันโปรโมชัน</span>
        <span><i className="swatch" style={{ background: "var(--bad)" }} />วันที่เงินอาจไม่พอ</span>
      </div>
      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 18, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            {spans.map(([a, b]) => (
              <ReferenceArea key={a} x1={a} x2={b} fill="var(--series-promo)" fillOpacity={0.14} stroke="none" ifOverflow="hidden" />
            ))}
            {holidays.map((d) => (
              <ReferenceLine key={d} x={d} stroke="var(--text-3)" strokeDasharray="2 3" />
            ))}
            <XAxis
              dataKey="date"
              tickFormatter={long ? thaiMonthShort : thaiDateShort}
              tick={{ fill: "var(--text-2)", fontSize: 12 }}
              axisLine={{ stroke: "var(--border)" }}
              tickLine={false}
              minTickGap={long ? 40 : 24}
            />
            <YAxis
              tickFormatter={(v: number) => money(v)}
              tick={{ fill: "var(--text-2)", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              width={64}
            />
            <Tooltip content={<ChartTooltip />} />
            <Area dataKey="band" stroke="none" fill="var(--series-band)" fillOpacity={0.16} connectNulls isAnimationActive={false} />
            <Line dataKey="actual" stroke="var(--series-actual)" strokeWidth={long ? 1.2 : 2} dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="predicted" stroke="var(--series-predicted)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="forecast" stroke="var(--series-forecast)" strokeWidth={2} strokeDasharray="6 4" dot={false} connectNulls isAnimationActive={false} />
            <ReferenceLine x={asOf} stroke="var(--text-3)" strokeDasharray="3 3"
              label={{ value: "วันนี้", position: "top", fill: "var(--text-2)", fontSize: 12 }} />
            {gaps.map((g) => <ReferenceLine key={g.date} x={g.date} stroke="var(--bad)" strokeWidth={2} />)}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small chart-note">
        เส้นสีส้มคือค่าที่โมเดลพยากรณ์ไว้ล่วงหน้าโดยยังไม่เห็นยอดขายจริงของวันนั้น (มีย้อนหลัง 28 วัน) ·
        เส้นประแนวตั้งสีเทาคือวันหยุดนักขัตฤกษ์ · ชี้ที่กราฟเพื่อดูรายละเอียดรายวัน
      </p>
      <label className="check">
        <input type="checkbox" checked={showFutureActual} onChange={(e) => setShowFutureActual(e.target.checked)} />
        แสดงยอดขายจริงในช่วงคาดการณ์ (ใช้ประเมินความแม่นยำ)
      </label>
    </div>
  );
}
