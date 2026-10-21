import { useState } from "react";
import {
  Bar,
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
import { addDays, money, monthStarts, pillRows, thaiDate, thaiDateShort, thaiMonthShort, thaiWeekday } from "../format";
import type { BalanceHorizon, CashBalance, Gap, LongGap } from "../types";
import { GapPill } from "./GapMarker";

// Same ranges as the sales chart: days back from today; the projection runs to the end of each horizon.
const RANGES = [
  { key: "4w", label: "4 สัปดาห์", back: 28 },
  { key: "3m", label: "3 เดือน", back: 91 },
  { key: "1y", label: "1 ปี", back: Infinity },
] as const;
type RangeKey = (typeof RANGES)[number]["key"];

const SOURCE: Record<BalanceHorizon, string> = {
  actual: "ยอดขายจริง",
  "14d": "ยอดขายคาดการณ์ 14 วัน",
  "3m": "ยอดขายคาดการณ์ 3 เดือน",
  "1y": "ยอดขายจากภาพรวมรายเดือน",
};

const isFar = (h: BalanceHorizon) => h === "3m" || h === "1y";

interface Row {
  date: string;
  sales: number;
  expenses: number;
  balance: number;
  past: number | null;
  projected: number | null; // 14-day projection
  far: number | null; // beyond 14 days (3-month rollout, then monthly outlook) — less certain
  horizon: BalanceHorizon;
}

function BalanceTooltip({ active, payload, label }: { active?: boolean; payload?: { payload: Row }[]; label?: string }) {
  if (!active || !payload?.length || !label) return null;
  const r = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{thaiWeekday(label)} {thaiDate(label)}</strong>
      <div>{SOURCE[r.horizon]} +{money(r.sales)}</div>
      {r.expenses > 0 && <div>รายจ่าย −{money(r.expenses)}</div>}
      <div>
        ยอดเงินคงเหลือ <b className="num" style={{ color: r.balance < 0 ? "var(--bad)" : undefined }}>{money(r.balance)}</b>
      </div>
      {isFar(r.horizon) && <div className="muted">ไกลกว่า 14 วัน ความแม่นยำต่ำลง</div>}
      {r.balance < 0 && (
        <div className="tooltip-tags" style={{ color: "var(--bad)" }}>{r.horizon === "actual" ? "เงินเคยไม่พอ" : "เงินอาจไม่พอ"}</div>
      )}
    </div>
  );
}

/** Red dot on every day the balance is below zero (past and projected; faded beyond 14 days). */
function NegativeDot(props: { cx?: number; cy?: number; payload?: Row; index?: number }) {
  const { cx, cy, payload, index } = props;
  if (!payload || payload.balance >= 0 || cx == null || cy == null) return <g key={index} />;
  return <circle key={index} cx={cx} cy={cy} r={3.5} fill={payload.horizon === "actual" ? "var(--warn)" : "var(--bad)"}
    fillOpacity={isFar(payload.horizon) ? 0.55 : 1} stroke="var(--surface)" strokeWidth={1.2} />;
}

/** About five round axis ticks (step 1, 2, 2.5 or 5 × 10^k) covering lo..hi, including 0. */
function niceTicks(lo: number, hi: number): number[] {
  const raw = (hi - lo) / 5;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw)!;
  const ticks: number[] = [];
  for (let t = Math.floor(lo / step) * step; t < hi + step; t += step) ticks.push(t);
  return ticks;
}

/** B_t = B_{t-1} + S_t − E_t on synthetic expenses: history up to "today", projection after. */
export function BalanceChart({ balance, asOf, gaps }: { balance: CashBalance; asOf: string; gaps: Gap[] }) {
  const [range, setRange] = useState<RangeKey>("4w");
  const spec = RANGES.find((r) => r.key === range)!;
  const from = Number.isFinite(spec.back) ? addDays(asOf, -spec.back + 1) : "";
  const shortEnd = addDays(asOf, 14);
  const end = range === "4w" ? shortEnd : range === "3m"
    ? balance.points.filter((p) => p.horizon === "3m").at(-1)!.date
    : balance.points[balance.points.length - 1].date;
  const rows: Row[] = balance.points
    .filter((p) => p.date >= from && p.date <= end)
    .map((p) => ({
      date: p.date,
      sales: p.sales,
      expenses: p.expenses,
      balance: p.balance,
      past: p.date <= asOf ? p.balance : null,
      projected: p.date >= asOf && p.date <= shortEnd ? p.balance : null,
      far: p.date >= shortEnd ? p.balance : null,
      horizon: p.horizon,
    }));
  const inRange = (d: string) => d >= rows[0].date && d <= end;
  const pastGaps = balance.past_gaps.filter((g) => inRange(g.date));
  const longGaps: LongGap[] = balance.long_gaps.filter((g) => inRange(g.date));
  // one outlined callout for the worst later shortfall; the others show as faded red dots + the note
  const worstLong = longGaps.reduce<LongGap | null>((w, g) => (!w || g.shortfall > w.shortfall ? g : w), null);
  const lowest = rows.filter((r) => r.horizon === "14d").reduce((a, b) => (b.balance < a.balance ? b : a));
  const monthAxis = range !== "4w";
  const dates = rows.map((r) => r.date);
  const pills = pillRows(gaps.map((g) => g.date), dates, monthAxis ? 25 : 8);
  const yTicks = niceTicks(Math.min(0, ...rows.map((r) => r.balance)),
    Math.max(...rows.map((r) => Math.max(r.balance, r.expenses))) * (gaps.length || worstLong ? 1.4 : 1.05));

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
        <span><i className="swatch dashed balance" />คาดการณ์ 14 วัน</span>
        {monthAxis && <span><i className="swatch dashed balance" style={{ opacity: 0.45 }} />คาดการณ์ไกลกว่า 14 วัน (แม่นน้อยลง)</span>}
        <span><i className="swatch bar" />รายจ่ายที่ครบกำหนดวันนั้น</span>
        {pastGaps.length > 0 && <span><i className="swatch dashed past-gap" />วันที่เงินเคยไม่พอ</span>}
        <span><i className="swatch bar" style={{ background: "var(--bad)", opacity: 1 }} />วันที่เงินอาจไม่พอ · ระดับ 0</span>
      </div>
      <div style={{ width: "100%", height: 300 }}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 18, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            {monthAxis && (
              <ReferenceArea x1={addDays(shortEnd, 1)} x2={end} fill="var(--text-3)" fillOpacity={0.07} stroke="none" ifOverflow="hidden"
                label={{ value: "ไกลกว่า 14 วัน · แม่นน้อยลง", position: "insideBottomRight", fill: "var(--text-3)", fontSize: 11 }} />
            )}
            <XAxis dataKey="date" tickFormatter={monthAxis ? thaiMonthShort : thaiDateShort} tick={{ fill: "var(--text-2)", fontSize: 12 }}
              ticks={monthAxis ? monthStarts(dates) : undefined}
              axisLine={{ stroke: "var(--border)" }} tickLine={false} minTickGap={monthAxis ? 8 : 24} />
            <YAxis tickFormatter={(v: number) => money(v)} tick={{ fill: "var(--text-2)", fontSize: 12 }}
              axisLine={false} tickLine={false} width={64}
              domain={[yTicks[0], yTicks[yTicks.length - 1]]} ticks={yTicks} />
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
            {worstLong && (
              <ReferenceLine x={worstLong.date} stroke="var(--bad)" strokeOpacity={0.5} strokeDasharray="3 3"
                label={{ content: <GapPill gap={worstLong} row={gaps.length ? Math.max(...pills) + 1 : 0} outline flip={dates.indexOf(worstLong.date) > dates.length * 0.5} /> }} />
            )}
            <ReferenceLine x={asOf} stroke="var(--text-3)" strokeDasharray="3 3"
              label={{ value: "วันนี้", position: "top", fill: "var(--text-2)", fontSize: 12 }} />
            <Line dataKey="past" stroke="var(--series-balance)" strokeWidth={monthAxis ? 1.5 : 2} dot={NegativeDot} isAnimationActive={false} />
            <Line dataKey="projected" stroke="var(--series-balance)" strokeWidth={2} strokeDasharray="6 4" dot={NegativeDot} isAnimationActive={false} />
            <Line dataKey="far" stroke="var(--series-balance)" strokeOpacity={0.45} strokeWidth={1.5} strokeDasharray="6 4"
              dot={NegativeDot} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small chart-note">
        ยอดเงิน = ยอดเงินวันก่อน + ยอดขาย − รายจ่าย · ยอดเงินตั้งต้น {money(balance.opening_balance)} ({thaiDate(balance.points[0].date)}) ·
        เจ้าของร้านถอนเงินส่วนที่เกินเงินสำรองทุกวันที่ 25 · ต่ำสุดใน 14 วันข้างหน้า{" "}
        <b className="num" style={{ color: lowest.balance < 0 ? "var(--bad)" : undefined }}>{money(lowest.balance)}</b> วันที่ {thaiDate(lowest.date)}
        {monthAxis && <>
          {" "}· หลัง {thaiDate(shortEnd)}{" "}
          {worstLong
            ? <>อาจขาดอีก <b>{longGaps.length} ครั้ง</b> (มากสุด {money(worstLong.shortfall)} วันที่ {thaiDate(worstLong.date)})</>
            : "ไม่พบวันที่เงินอาจไม่พอ"}
          {" "}— ใช้ยอดขาย{range === "3m" ? "ที่โมเดลทายต่อเนื่อง 3 เดือน" : "ที่ทายต่อเนื่อง 3 เดือน แล้วต่อด้วยภาพรวมรายเดือน"}
          {" "}กับรายจ่ายจำลองรอบเดิม จึงเป็นสถานการณ์คร่าว ๆ ไม่ใช่คำเตือนแน่นอน
        </>}
      </p>
    </div>
  );
}
