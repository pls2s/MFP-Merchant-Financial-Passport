import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { money, percent, thaiDate, thaiDateShort, thaiYearMonth, thaiYearMonthLong } from "../format";
import type { Forecast, LongForecast, ModelResult, SeasonalOutlook } from "../types";

/**
 * "How accurate is it?" — kept out of the main chart. Each range shows its own backtest:
 * what the method forecast before the actual was known (orange) against real sales (black).
 */

type Range = "4w" | "3m" | "1y";

const axis = { tick: { fill: "var(--text-2)", fontSize: 11 }, axisLine: false, tickLine: false } as const;

function MiniTooltip({ active, payload, label, monthly }: {
  active?: boolean; payload?: { payload: { actual: number | null; predicted: number | null } }[]; label?: string; monthly?: boolean;
}) {
  if (!active || !payload?.length || !label) return null;
  const { actual, predicted } = payload[0].payload;
  const err = actual && predicted ? (predicted - actual) / actual : null;
  return (
    <div className="chart-tooltip">
      <strong>{monthly ? thaiYearMonthLong(label) : thaiDate(label)}</strong>
      {actual != null && <div>ยอดขายจริง <b className="num">{money(actual)}</b></div>}
      {predicted != null && <div>ทายไว้ล่วงหน้า <span className="num">{money(predicted)}</span></div>}
      {err != null && <div className="muted">คลาด {err >= 0 ? "+" : ""}{(err * 100).toFixed(1)}%</div>}
    </div>
  );
}

function MiniLines({ data }: { data: { date: string; actual: number | null; predicted: number | null }[] }) {
  return (
    <div style={{ width: "100%", height: 170 }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="date" tickFormatter={thaiDateShort} minTickGap={28} {...axis} />
          <YAxis tickFormatter={(v: number) => money(v)} width={56} {...axis} />
          <Tooltip content={<MiniTooltip />} />
          <Line dataKey="actual" stroke="var(--series-actual)" strokeWidth={1.6} dot={false} connectNulls isAnimationActive={false} />
          <Line dataKey="predicted" stroke="var(--series-predicted)" strokeWidth={1.6} dot={false} connectNulls isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Legend() {
  return (
    <div className="chart-legend">
      <span><i className="swatch" style={{ background: "var(--series-actual)" }} />ยอดขายจริง</span>
      <span><i className="swatch" style={{ background: "var(--series-predicted)" }} />ที่ทายไว้ล่วงหน้า (ยังไม่เห็นยอดจริง)</span>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className="accuracy-value num">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function FourWeeks({ forecast, asOf, results }: { forecast: Forecast; asOf: string; results: ModelResult[] }) {
  const past = forecast.points.filter((p) => p.date <= asOf);
  const days = past.filter((p) => (p.actual ?? 0) > 0 && p.forecast > 0);
  if (!days.length) return null;
  const absErr = days.map((p) => Math.abs(p.forecast - p.actual!));
  const wape = absErr.reduce((a, b) => a + b, 0) / days.reduce((a, p) => a + p.actual!, 0);
  const within10 = days.filter((p, i) => absErr[i] / p.actual! <= 0.1).length;
  const worst = days.reduce((w, p, i) => (absErr[i] / p.actual! > Math.abs(w.forecast - w.actual!) / w.actual! ? p : w), days[0]);
  const worstErr = (worst.forecast - worst.actual!) / worst.actual!;
  const allStores = results.find((r) => r.model === "ensemble" && r.split === "test");
  const data = past.map((p) => ({
    date: p.date, actual: (p.actual ?? 0) > 0 ? p.actual! : null, predicted: p.forecast > 0 ? p.forecast : null,
  }));
  return (
    <>
      <p className="muted small accuracy-intro">
        ย้อนหลัง {days.length} วันที่ร้านเปิด ({thaiDate(days[0].date)} – {thaiDate(days[days.length - 1].date)})
        โมเดลทายล่วงหน้าสูงสุด 14 วัน โดยยังไม่เห็นยอดขายจริงของวันนั้น
      </p>
      <Legend />
      <MiniLines data={data} />
      <div className="accuracy-grid">
        <Stat label="คลาดเคลื่อนเฉลี่ย (WAPE)" value={percent(wape, 1)}
          sub={allStores ? `เฉลี่ยทุกร้าน ${percent(allStores.wape, 1)}` : undefined} />
        <Stat label="วันที่ทายคลาดไม่เกิน 10%" value={`${within10}/${days.length} วัน`}
          sub={`${percent(within10 / days.length, 0)} ของวันที่ร้านเปิด`} />
        <Stat label="วันที่ทายพลาดมากที่สุด" value={thaiDate(worst.date)}
          sub={`จริง ${money(worst.actual!)} · ทาย ${money(worst.forecast)} (${worstErr >= 0 ? "+" : ""}${(worstErr * 100).toFixed(0)}%)`} />
      </div>
    </>
  );
}

function ThreeMonths({ longForecast }: { longForecast: LongForecast }) {
  const bt = longForecast.backtest;
  const data = bt.points.map((p) => ({
    date: p.date, actual: p.actual > 0 ? p.actual : null, predicted: p.forecast > 0 ? p.forecast : null,
  }));
  return (
    <>
      <p className="muted small accuracy-intro">
        ให้โมเดลทายต่อเนื่อง {bt.days} วันจาก {thaiDate(bt.origin)} (วันสุดท้ายของข้อมูลเทรน) แล้วเทียบกับยอดขายจริง
      </p>
      <Legend />
      <MiniLines data={data} />
      <div className="accuracy-grid">
        <Stat label="คลาดเคลื่อนเฉลี่ย (ร้านนี้)" value={bt.wape_store != null ? percent(bt.wape_store, 1) : "—"}
          sub={`เฉลี่ยทุกร้าน ${percent(bt.wape_all_stores, 1)}`} />
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
        แถบช่วงคาดการณ์ในกราฟหลักปรับจากผลทดสอบชุดนี้
      </p>
    </>
  );
}

function OneYear({ seasonal }: { seasonal: SeasonalOutlook }) {
  const bt = seasonal.backtest;
  const data = bt.months.map((m) => ({ date: m.month, actual: m.actual, predicted: m.outlook }));
  return (
    <>
      <p className="muted small accuracy-intro">
        ภาพรวม 1 ปีไม่ใช่ผลโมเดล deep learning: ยอดแต่ละเดือน = ยอดเดือนเดียวกันปีก่อน × การเปลี่ยนแปลงของ 12 สัปดาห์ล่าสุด ·
        ทดสอบย้อนหลัง 12 เดือนจาก {thaiDate(bt.origin)}
      </p>
      <Legend />
      <div style={{ width: "100%", height: 170 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barGap={2}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="date" tickFormatter={thaiYearMonth} interval={0} {...axis} />
            <YAxis tickFormatter={(v: number) => money(v)} width={56} {...axis} />
            <Tooltip content={<MiniTooltip monthly />} cursor={{ fill: "var(--surface-2)" }} />
            <Bar dataKey="actual" fill="var(--series-actual)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="predicted" fill="var(--series-predicted)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="accuracy-grid">
        <Stat label="คลาดเคลื่อนเฉลี่ยรายเดือน (ร้านนี้)" value={bt.wape_store != null ? percent(bt.wape_store, 1) : "—"}
          sub={`เฉลี่ยทุกร้าน ${percent(bt.wape_all_stores, 1)}`} />
        <div className="span-2">
          <div className="stat-label">อ่านอย่างไร</div>
          <div className="stat-sub" style={{ marginTop: 4 }}>
            วัดเป็นยอดรายเดือน จึงคลาดน้อยกว่ายอดรายวันโดยธรรมชาติ เทียบกับตัวเลขของ 14 วันตรง ๆ ไม่ได้
          </div>
        </div>
      </div>
    </>
  );
}

export function Accuracy({ range, forecast, longForecast, seasonal, results, asOf }: {
  range: Range;
  forecast: Forecast;
  longForecast: LongForecast;
  seasonal: SeasonalOutlook;
  results: ModelResult[];
  asOf: string;
}) {
  const title = range === "4w" ? "ทาย 14 วันแม่นแค่ไหน" : range === "3m" ? "ทาย 3 เดือนแม่นแค่ไหน" : "ภาพรวม 1 ปีแม่นแค่ไหน";
  return (
    <div className="accuracy">
      <div className="accuracy-head">
        <strong>{title} <span className="muted small" style={{ fontWeight: 400 }}>· ทดสอบย้อนหลังกับยอดขายจริง</span></strong>
      </div>
      {range === "4w" && <FourWeeks forecast={forecast} asOf={asOf} results={results} />}
      {range === "3m" && <ThreeMonths longForecast={longForecast} />}
      {range === "1y" && <OneYear seasonal={seasonal} />}
    </div>
  );
}
