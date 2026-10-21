import { useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { money, thaiDate, thaiDateShort } from "../format";
import type { Forecast, Gap } from "../types";

interface Row {
  date: string;
  actual: number | null;
  forecast: number | null;
  band: [number, number] | null;
}

/** Actual sales up to `asOf`, forecast + interval after it. Closed days (0) are skipped, not drawn as drops. */
function rows(forecast: Forecast, asOf: string, showFutureActual: boolean): Row[] {
  const positive = (x: number | null | undefined) => (x && x > 0 ? x : null);
  return forecast.points.map((p) => {
    const future = p.date > asOf;
    return {
      date: p.date,
      actual: !future || showFutureActual ? positive(p.actual) : null,
      // The forecast line starts at "today" so it joins the actual line.
      forecast: future ? positive(p.forecast) : p.date === asOf ? positive(p.actual) : null,
      band: future && positive(p.forecast) && p.lower != null && p.upper != null ? [p.lower, p.upper] : null,
    };
  });
}

function ChartTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: { payload: Row }[];
  label?: string;
}) {
  if (!active || !payload?.length || !label) return null;
  const row = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{thaiDate(label)}</strong>
      {row.actual != null && <div>ยอดขายจริง {money(row.actual)}</div>}
      {row.forecast != null && row.band && <div>คาดการณ์ {money(row.forecast)}</div>}
      {row.band && <div className="muted">ช่วง {money(row.band[0])} – {money(row.band[1])}</div>}
      {row.actual == null && row.forecast == null && <div className="muted">ร้านปิด</div>}
    </div>
  );
}

export function SalesChart({ forecast, asOf, gaps }: { forecast: Forecast; asOf: string; gaps: Gap[] }) {
  const [showFutureActual, setShowFutureActual] = useState(false);
  const data = rows(forecast, asOf, showFutureActual);

  return (
    <div>
      <div className="chart-legend">
        <span><i className="swatch" style={{ background: "var(--series-actual)" }} />ยอดขายจริง</span>
        <span><i className="swatch dashed" />ยอดขายคาดการณ์</span>
        <span><i className="swatch band" />ช่วงคาดการณ์โดยประมาณ</span>
        <span><i className="swatch" style={{ background: "var(--bad)" }} />วันที่เงินอาจไม่พอ</span>
      </div>
      <div style={{ width: "100%", height: 300 }}>
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 16, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={thaiDateShort}
              tick={{ fill: "var(--text-2)", fontSize: 12 }}
              axisLine={{ stroke: "var(--border)" }}
              tickLine={false}
              minTickGap={24}
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
            <Line dataKey="actual" stroke="var(--series-actual)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            <Line
              dataKey="forecast"
              stroke="var(--series-forecast)"
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <ReferenceLine
              x={asOf}
              stroke="var(--text-3)"
              strokeDasharray="3 3"
              label={{ value: "วันนี้", position: "top", fill: "var(--text-2)", fontSize: 12 }}
            />
            {gaps.map((g) => (
              <ReferenceLine key={g.date} x={g.date} stroke="var(--bad)" strokeWidth={2} />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <label className="check">
        <input type="checkbox" checked={showFutureActual} onChange={(e) => setShowFutureActual(e.target.checked)} />
        แสดงยอดขายจริงในช่วงคาดการณ์ (ใช้ประเมินความแม่นยำ)
      </label>
    </div>
  );
}
