import { useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { money, monthStarts, pillRows, thaiDate, thaiDateShort, thaiMonthShort, thaiWeekday } from "../format";
import type { CashBalance, Gap } from "../types";
import { GapPill } from "./GapMarker";

const RANGES = [
  { key: "6w", label: "6 สัปดาห์", days: 42 },
  { key: "all", label: "ตั้งแต่ ม.ค.", days: Infinity },
] as const;
type RangeKey = (typeof RANGES)[number]["key"];

interface Row {
  date: string;
  sales: number;
  expenses: number;
  balance: number;
  past: number | null;
  projected: number | null;
  isForecast: boolean;
}

function BalanceTooltip({ active, payload, label }: { active?: boolean; payload?: { payload: Row }[]; label?: string }) {
  if (!active || !payload?.length || !label) return null;
  const r = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{thaiWeekday(label)} {thaiDate(label)}</strong>
      <div>{r.isForecast ? "ยอดขายคาดการณ์" : "ยอดขายจริง"} +{money(r.sales)}</div>
      {r.expenses > 0 && <div>รายจ่าย −{money(r.expenses)}</div>}
      <div>
        ยอดเงินคงเหลือ <b className="num" style={{ color: r.balance < 0 ? "var(--bad)" : undefined }}>{money(r.balance)}</b>
      </div>
      {r.balance < 0 && <div className="tooltip-tags" style={{ color: "var(--bad)" }}>{r.isForecast ? "เงินอาจไม่พอ" : "เงินเคยไม่พอ"}</div>}
    </div>
  );
}

/** Red dot on every day the balance is below zero (past and projected). */
function NegativeDot(props: { cx?: number; cy?: number; payload?: Row; index?: number }) {
  const { cx, cy, payload, index } = props;
  if (!payload || payload.balance >= 0 || cx == null || cy == null) return <g key={index} />;
  return <circle key={index} cx={cx} cy={cy} r={3.5} fill={payload.isForecast ? "var(--bad)" : "var(--warn)"}
    stroke="var(--surface)" strokeWidth={1.2} />;
}

/** B_t = B_{t-1} + S_t − E_t on synthetic expenses: history up to "today", projection after. */
export function BalanceChart({ balance, asOf, gaps }: { balance: CashBalance; asOf: string; gaps: Gap[] }) {
  const [range, setRange] = useState<RangeKey>("all");
  const days = RANGES.find((r) => r.key === range)!.days;
  const from = Number.isFinite(days)
    ? new Date(Date.parse(`${asOf}T00:00:00Z`) - (days - 15) * 86_400_000).toISOString().slice(0, 10)
    : "";
  const rows: Row[] = balance.points
    .filter((p) => p.date >= from)
    .map((p) => ({
      date: p.date,
      sales: p.sales,
      expenses: p.expenses,
      balance: p.balance,
      past: p.date <= asOf ? p.balance : null,
      projected: p.date >= asOf ? p.balance : null,
      isForecast: p.is_forecast,
    }));
  const pastGaps = balance.past_gaps.filter((g) => g.date >= (rows[0]?.date ?? ""));
  const lowest = rows.filter((r) => r.isForecast).reduce((a, b) => (b.balance < a.balance ? b : a));
  const long = range === "all";
  const dates = rows.map((r) => r.date);
  const pills = pillRows(gaps.map((g) => g.date), dates, long ? 25 : 8);

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
        <span><i className="swatch" style={{ background: "var(--series-balance)" }} />ยอดเงินคงเหลือ</span>
        <span><i className="swatch dashed balance" />ยอดเงินที่คาดการณ์</span>
        <span><i className="swatch bar" />รายจ่ายที่ครบกำหนดวันนั้น</span>
        <span><i className="swatch dashed past-gap" />วันที่เงินเคยไม่พอ</span>
        <span><i className="swatch" style={{ background: "var(--bad)" }} />วันที่เงินอาจไม่พอ · ระดับ 0</span>
      </div>
      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 18, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="date" tickFormatter={long ? thaiMonthShort : thaiDateShort} tick={{ fill: "var(--text-2)", fontSize: 12 }}
              ticks={long ? monthStarts(rows.map((r) => r.date)) : undefined}
              axisLine={{ stroke: "var(--border)" }} tickLine={false} minTickGap={long ? 8 : 24} />
            <YAxis tickFormatter={(v: number) => money(v)} tick={{ fill: "var(--text-2)", fontSize: 12 }}
              axisLine={false} tickLine={false} width={64}
              domain={[(min: number) => Math.floor(Math.min(min, 0) / 5000) * 5000,
                (max: number) => Math.ceil((max * (gaps.length ? 1.3 : 1.05)) / 5000) * 5000]} />
            <Tooltip content={<BalanceTooltip />} />
            <Bar dataKey="expenses" fill="var(--series-expense)" fillOpacity={0.55} radius={[3, 3, 0, 0]} maxBarSize={14} isAnimationActive={false} />
            <ReferenceLine y={0} stroke="var(--bad)" strokeWidth={1.5} />
            {pastGaps.map((g) => (
              <ReferenceLine key={`past-${g.date}`} x={g.date} stroke="var(--warn)" strokeWidth={1.5} strokeDasharray="4 3" />
            ))}
            {gaps.map((g, i) => (
              <ReferenceLine key={g.date} x={g.date} stroke="var(--bad)" strokeWidth={1.5} strokeDasharray="3 3"
                label={{ content: <GapPill gap={g} row={pills[i]} flip={dates.indexOf(g.date) > dates.length * 0.5} /> }} />
            ))}
            <ReferenceLine x={asOf} stroke="var(--text-3)" strokeDasharray="3 3"
              label={{ value: "วันนี้", position: "top", fill: "var(--text-2)", fontSize: 12 }} />
            <Line dataKey="past" stroke="var(--series-balance)" strokeWidth={long ? 1.5 : 2} dot={NegativeDot} isAnimationActive={false} />
            <Line dataKey="projected" stroke="var(--series-balance)" strokeWidth={2} strokeDasharray="6 4" dot={NegativeDot} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small chart-note">
        ยอดเงิน = ยอดเงินวันก่อน + ยอดขาย − รายจ่าย · ยอดเงินตั้งต้น {money(balance.opening_balance)} ({thaiDate(balance.points[0].date)}) ·
        เจ้าของร้านถอนเงินส่วนที่เกินเงินสำรองทุกวันที่ 25 · ต่ำสุดในช่วงคาดการณ์{" "}
        <b className="num" style={{ color: lowest.balance < 0 ? "var(--bad)" : undefined }}>{money(lowest.balance)}</b> วันที่ {thaiDate(lowest.date)}
      </p>
    </div>
  );
}
