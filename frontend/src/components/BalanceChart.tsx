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
import { money, thaiDate, thaiDateShort, thaiWeekday } from "../format";
import type { CashBalance } from "../types";

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
    </div>
  );
}

/** B_t = B_{t-1} + S_t − E_t on synthetic expenses: history up to "today", projection after. */
export function BalanceChart({ balance, asOf }: { balance: CashBalance; asOf: string }) {
  const rows: Row[] = balance.points.map((p) => ({
    date: p.date,
    sales: p.sales,
    expenses: p.expenses,
    balance: p.balance,
    past: p.date <= asOf ? p.balance : null,
    projected: p.date >= asOf ? p.balance : null,
    isForecast: p.is_forecast,
  }));
  const lowest = rows.filter((r) => r.isForecast).reduce((a, b) => (b.balance < a.balance ? b : a));

  return (
    <div>
      <div className="chart-legend">
        <span><i className="swatch" style={{ background: "var(--series-balance)" }} />ยอดเงินคงเหลือ</span>
        <span><i className="swatch dashed balance" />ยอดเงินที่คาดการณ์</span>
        <span><i className="swatch bar" />รายจ่ายที่ครบกำหนดวันนั้น</span>
        <span><i className="swatch" style={{ background: "var(--bad)" }} />ระดับ 0 (เงินหมด)</span>
      </div>
      <div style={{ width: "100%", height: 260 }}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 18, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="date" tickFormatter={thaiDateShort} tick={{ fill: "var(--text-2)", fontSize: 12 }}
              axisLine={{ stroke: "var(--border)" }} tickLine={false} minTickGap={24} />
            <YAxis tickFormatter={(v: number) => money(v)} tick={{ fill: "var(--text-2)", fontSize: 12 }}
              axisLine={false} tickLine={false} width={64} />
            <Tooltip content={<BalanceTooltip />} />
            <Bar dataKey="expenses" fill="var(--series-expense)" fillOpacity={0.55} radius={[3, 3, 0, 0]} maxBarSize={14} isAnimationActive={false} />
            <ReferenceLine y={0} stroke="var(--bad)" strokeWidth={1.5} />
            <ReferenceLine x={asOf} stroke="var(--text-3)" strokeDasharray="3 3"
              label={{ value: "วันนี้", position: "top", fill: "var(--text-2)", fontSize: 12 }} />
            <Line dataKey="past" stroke="var(--series-balance)" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="projected" stroke="var(--series-balance)" strokeWidth={2} strokeDasharray="6 4"
              dot={(props: { cx?: number; cy?: number; payload?: Row; index?: number }) =>
                props.payload && props.payload.projected != null && props.payload.balance < 0
                  ? <circle key={props.index} cx={props.cx} cy={props.cy} r={4} fill="var(--bad)" stroke="var(--surface)" strokeWidth={1.5} />
                  : <g key={props.index} />}
              isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small chart-note">
        ยอดเงิน = ยอดเงินวันก่อน + ยอดขาย − รายจ่าย · ยอดเงินตั้งต้น {money(balance.opening_balance)} (20 มิ.ย. 2558) ·
        ต่ำสุดในช่วงคาดการณ์ <b className="num" style={{ color: lowest.balance < 0 ? "var(--bad)" : undefined }}>{money(lowest.balance)}</b> วันที่ {thaiDate(lowest.date)}
      </p>
    </div>
  );
}
