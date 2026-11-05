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
import { addDays, compact, money, monthStarts, pillRows, thaiDate, thaiDateShort, thaiMonthShort, thaiWeekday } from "../format";
import type { BalanceHorizon, CashBalance, Gap, LongGap } from "../types";
import { GapPill } from "./GapMarker";
import type { BalanceLayer, RangeKey } from "./chartOptions";
import { DataTable, LegendChip, Swatch, type ViewMode } from "./ui";

// Same ranges as the sales chart: days back from today; the projection runs to the end of each horizon.
const BACK: Record<RangeKey, number> = { "4w": 28, "3m": 91, "1y": Infinity };

const SOURCE: Record<BalanceHorizon, string> = {
  actual: "ยอดขายจริง",
  "14d": "ยอดขายคาดการณ์ 14 วัน",
  "3m": "ยอดขายคาดการณ์ 3 เดือน",
  "1y": "ยอดขายจากภาพรวมรายเดือน",
};

const isFar = (h: BalanceHorizon) => h === "3m" || h === "1y";

type BalanceSeries = "past" | "projected" | "far";

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
export function BalanceChart({ balance, asOf, gaps, range, layers, view }: {
  balance: CashBalance;
  asOf: string;
  gaps: Gap[];
  range: RangeKey;
  layers: ReadonlySet<BalanceLayer>;
  view: ViewMode;
}) {
  const [hidden, setHidden] = useState<ReadonlySet<BalanceSeries>>(new Set());
  const toggle = (k: BalanceSeries) => setHidden((h) => {
    const next = new Set(h);
    if (!next.delete(k)) next.add(k);
    return next;
  });
  const back = BACK[range];
  const from = Number.isFinite(back) ? addDays(asOf, -back + 1) : "";
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
  const pastGaps = layers.has("pastGaps") ? balance.past_gaps.filter((g) => inRange(g.date)) : [];
  const longGaps: LongGap[] = balance.long_gaps.filter((g) => inRange(g.date));
  // one outlined callout for the worst later shortfall; the others show as faded red dots + the note
  const worstLong = longGaps.reduce<LongGap | null>((w, g) => (!w || g.shortfall > w.shortfall ? g : w), null);
  const showLong = layers.has("longGaps") && worstLong;
  const lowest = rows.filter((r) => r.horizon === "14d").reduce((a, b) => (b.balance < a.balance ? b : a));
  const monthAxis = range !== "4w";
  const dates = rows.map((r) => r.date);
  const pills = pillRows(gaps.map((g) => g.date), dates, monthAxis ? 25 : 8);
  const showExpenses = layers.has("expenses");
  const yTicks = niceTicks(Math.min(0, ...rows.map((r) => r.balance)),
    Math.max(...rows.map((r) => Math.max(r.balance, showExpenses ? r.expenses : 0))) * (gaps.length || showLong ? 1.4 : 1.05));
  const gapDates = new Set([...gaps, ...balance.past_gaps, ...balance.long_gaps].map((g) => g.date));

  const note = (
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
  );

  if (view === "table") {
    return (
      <div>
        <DataTable
          columns={[
            { key: "date", label: "วันที่", align: "left" },
            { key: "sales", label: "ยอดขาย (+)" },
            { key: "expenses", label: "รายจ่าย (−)" },
            { key: "balance", label: "ยอดเงินคงเหลือ" },
            { key: "source", label: "ที่มาของยอดขาย", align: "left" },
          ]}
          rows={rows.map((r) => ({
            date: thaiDate(r.date),
            sales: money(r.sales),
            expenses: r.expenses > 0 ? money(r.expenses) : null,
            balance: <span style={{ color: r.balance < 0 ? "var(--bad)" : undefined }}>{r.balance < 0 && "⚠ "}{money(r.balance)}</span>,
            source: SOURCE[r.horizon],
          }))}
          highlight={(i) => (rows[i].balance < 0 ? (rows[i].horizon === "actual" ? "warn" : "bad") : gapDates.has(rows[i].date) ? "warn" : undefined)}
        />
        {note}
      </div>
    );
  }

  return (
    <div>
      <div className="chart-legend">
        <LegendChip on={!hidden.has("past")} onClick={() => toggle("past")}><Swatch kind="line" color="var(--series-balance)" />ยอดเงินคงเหลือ</LegendChip>
        <LegendChip on={!hidden.has("projected")} onClick={() => toggle("projected")}><Swatch kind="line" color="var(--series-balance)" dashed />คาดการณ์ 14 วัน</LegendChip>
        {monthAxis && <LegendChip on={!hidden.has("far")} onClick={() => toggle("far")}><Swatch kind="line" color="var(--series-balance)" dashed opacity={0.45} />คาดการณ์ไกลกว่า 14 วัน (แม่นน้อยลง)</LegendChip>}
        {showExpenses && <span><Swatch kind="bar" color="var(--series-expense)" />รายจ่ายที่ครบกำหนดวันนั้น</span>}
        {pastGaps.length > 0 && <span><Swatch kind="line" color="var(--warn)" dashed />วันที่เงินเคยไม่พอ</span>}
        <span><Swatch kind="line" color="var(--bad)" />⚠ วันที่เงินอาจไม่พอ · ระดับ 0</span>
      </div>
      <div style={{ width: "100%", height: 320 }} role="img" aria-label={`กราฟยอดเงินคงเหลือ (ข้อมูลจำลอง) ต่ำสุดใน 14 วันข้างหน้า ${money(lowest.balance)} วันที่ ${thaiDate(lowest.date)}`}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 18, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            {monthAxis && (
              <ReferenceArea x1={addDays(shortEnd, 1)} x2={end} fill="var(--text-3)" fillOpacity={0.07} stroke="none" ifOverflow="hidden"
                label={{ value: "ไกลกว่า 14 วัน · แม่นน้อยลง", position: "insideBottomRight", fill: "var(--text-3)", fontSize: 11 }} />
            )}
            <XAxis dataKey="date" tickFormatter={monthAxis ? thaiMonthShort : thaiDateShort} tick={{ fill: "var(--text-3)", fontSize: 12, fontWeight: 500 }}
              ticks={monthAxis ? monthStarts(dates) : undefined}
              axisLine={{ stroke: "var(--border)" }} tickLine={false} minTickGap={monthAxis ? 8 : 24} />
            <YAxis tickFormatter={compact} tick={{ fill: "var(--text-3)", fontSize: 12, fontWeight: 500 }}
              axisLine={false} tickLine={false} width={48}
              domain={[yTicks[0], yTicks[yTicks.length - 1]]} ticks={yTicks} />
            <Tooltip content={<BalanceTooltip />} />
            {showExpenses && (
              <Bar dataKey="expenses" fill="var(--series-expense)" fillOpacity={0.55} radius={[3, 3, 0, 0]} maxBarSize={14} isAnimationActive={false} />
            )}
            <ReferenceLine y={0} stroke="var(--bad)" strokeWidth={1.5} />
            {pastGaps.map((g) => (
              <ReferenceLine key={`past-${g.date}`} x={g.date} stroke="var(--warn)" strokeWidth={1.5} strokeDasharray="4 3" />
            ))}
            {gaps.map((g, i) => (
              <ReferenceLine key={g.date} x={g.date} stroke="var(--bad)" strokeWidth={1.5} strokeDasharray="3 3"
                label={{ content: <GapPill gap={g} row={pills[i]} flip={dates.indexOf(g.date) > dates.length * 0.5} /> }} />
            ))}
            {showLong && worstLong && (
              <ReferenceLine x={worstLong.date} stroke="var(--bad)" strokeOpacity={0.5} strokeDasharray="3 3"
                label={{ content: <GapPill gap={worstLong} row={gaps.length ? Math.max(...pills) + 1 : 0} outline flip={dates.indexOf(worstLong.date) > dates.length * 0.5} /> }} />
            )}
            <ReferenceLine x={asOf} stroke="var(--text-3)" strokeDasharray="3 3"
              label={{ value: "วันนี้", position: "top", fill: "var(--text-3)", fontSize: 12 }} />
            <Line dataKey="past" hide={hidden.has("past")} stroke="var(--series-balance)" strokeWidth={monthAxis ? 1.5 : 2} dot={NegativeDot} isAnimationActive={false} />
            <Line dataKey="projected" hide={hidden.has("projected")} stroke="var(--series-balance)" strokeWidth={2} strokeDasharray="6 4" dot={NegativeDot} isAnimationActive={false} />
            <Line dataKey="far" hide={hidden.has("far")} stroke="var(--series-balance)" strokeOpacity={0.45} strokeWidth={1.5} strokeDasharray="6 4"
              dot={NegativeDot} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {note}
    </div>
  );
}
