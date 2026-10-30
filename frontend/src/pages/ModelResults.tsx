import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { Card, ChipGroup, ErrorState, Segmented, Skeleton, Swatch } from "../components/ui";
import { compact, money, percent } from "../format";
import type { ModelResult } from "../types";
import { useAsync } from "../useAsync";

// Colour follows the model, never its rank — hiding a model does not repaint the others.
const MODELS = [
  { key: "seasonal_naive", label: "Seasonal naive", color: "var(--text-3)" },
  { key: "lightgbm", label: "LightGBM", color: "var(--series-lgbm)" },
  { key: "lstm", label: "LSTM", color: "var(--series-lstm)" },
  { key: "gru", label: "GRU", color: "var(--series-gru)" },
  { key: "ensemble", label: "LSTM+GRU (โมเดลหลัก)", color: "var(--series-forecast)" },
] as const;
type ModelKey = (typeof MODELS)[number]["key"];

const METRICS = {
  wape: { label: "WAPE", hint: "ความคลาดเคลื่อนรวม ÷ ยอดขายจริงรวม (ยิ่งต่ำยิ่งดี)", fmt: (v: number) => percent(v), axis: (v: number) => percent(v, 0) },
  mae: { label: "MAE", hint: "คลาดเคลื่อนเฉลี่ยต่อวัน (หน่วยยอดขาย)", fmt: money, axis: compact },
  rmse: { label: "RMSE", hint: "ให้น้ำหนักวันที่พลาดมากเป็นพิเศษ", fmt: money, axis: compact },
} as const;
type Metric = keyof typeof METRICS;

function BarTip({ active, payload, metric }: { active?: boolean; payload?: { payload: { label: string; r: ModelResult } }[]; metric: Metric }) {
  if (!active || !payload?.length) return null;
  const { label, r } = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      <div><b className="num">{METRICS[metric].fmt(r[metric])}</b> <span className="muted">{METRICS[metric].label}</span></div>
      <div className="muted">ประเมิน {r.n_days.toLocaleString("en-US")} วัน</div>
    </div>
  );
}

export function ModelResults() {
  const [state, retry] = useAsync(api.modelResults, []);
  const [split, setSplit] = useState<"test" | "val">("test");
  const [metric, setMetric] = useState<Metric>("wape");
  const [visible, setVisible] = useState<Set<ModelKey>>(new Set(MODELS.map((m) => m.key)));

  const all = state.status === "ok"
    ? MODELS.map((m) => ({ ...m, r: state.data.find((r) => r.model === m.key && r.split === split) }))
        .filter((m): m is (typeof m & { r: ModelResult }) => !!m.r)
    : [];
  const rows = all.filter((m) => visible.has(m.key));
  const best = all.length ? all.reduce((a, b) => (b.r[metric] < a.r[metric] ? b : a)) : null;
  const naive = all.find((m) => m.key === "seasonal_naive");
  const main = all.find((m) => m.key === "ensemble");

  return (
    <>
      <div className="page-head">
        <div className="title-row">
          <div>
            <div className="eyebrow">Workstream 1 · Deep learning</div>
            <h1>ผลการทดลองโมเดลพยากรณ์</h1>
          </div>
        </div>
        <p className="muted">พยากรณ์ยอดขายรายวันล่วงหน้า 14 วัน · ร้าน Rossmann 1,115 ร้าน</p>
      </div>

      {main && naive && (
        <div className="summary-grid">
          <section className="stat-card">
            <div className="stat-label">WAPE โมเดลหลัก ({split === "test" ? "Test" : "Validation"})</div>
            <div className="stat-value">{percent(main.r.wape)}</div>
            <div className="stat-sub">เป้าหมาย ≤ 20% · {main.r.wape <= 0.2 ? <span className="good-text">ผ่านเป้า</span> : <span className="bad-text">ยังไม่ผ่าน</span>}</div>
          </section>
          <section className="stat-card">
            <div className="stat-label">ดีกว่า seasonal naive</div>
            <div className="stat-value">{(naive.r.wape / main.r.wape).toFixed(1)}<small>×</small></div>
            <div className="stat-sub">naive {percent(naive.r.wape)} → LSTM+GRU {percent(main.r.wape)}</div>
          </section>
          <section className="stat-card">
            <div className="stat-label">ดีที่สุดตาม {METRICS[metric].label}</div>
            <div className="stat-value small-value">{best?.label}</div>
            <div className="stat-sub">{best && METRICS[metric].fmt(best.r[metric])}</div>
          </section>
        </div>
      )}

      <div className="filter-bar" role="toolbar" aria-label="ตัวกรองผลโมเดล">
        <span className="filter-label">ชุดข้อมูล</span>
        <Segmented label="ชุดข้อมูล" value={split} onChange={setSplit}
          options={[{ key: "test", label: "Test" }, { key: "val", label: "Validation" }]} />
        <span className="filter-label">ตัวชี้วัด</span>
        <Segmented label="ตัวชี้วัด" value={metric} onChange={setMetric}
          options={(Object.keys(METRICS) as Metric[]).map((k) => ({ key: k, label: METRICS[k].label }))} />
      </div>

      <Card eyebrow={METRICS[metric].hint} title={`เปรียบเทียบโมเดล · ${METRICS[metric].label}`}>
        <ChipGroup label="โมเดลที่แสดง" value={visible} onChange={setVisible}
          options={MODELS.map((m) => ({ key: m.key, label: m.label, swatch: <Swatch kind="bar" color={m.color} /> }))} />
        {state.status === "loading" && <Skeleton height={260} />}
        {state.status === "error" && <ErrorState error={state.error} onRetry={retry} />}
        {state.status === "ok" && (
          <>
            <div style={{ width: "100%", height: 280, marginTop: 8 }} role="img"
              aria-label={`กราฟแท่งเปรียบเทียบ ${METRICS[metric].label} ของแต่ละโมเดล`}>
              <ResponsiveContainer>
                <BarChart layout="vertical" data={rows.map((m) => ({ label: m.label.replace(" (โมเดลหลัก)", ""), value: m.r[metric], color: m.color, r: m.r }))}
                  margin={{ top: 24, right: 56, bottom: 0, left: 0 }} barCategoryGap="28%">
                  <CartesianGrid stroke="var(--grid)" horizontal={false} />
                  <XAxis type="number" tickFormatter={METRICS[metric].axis} tick={{ fill: "var(--text-3)", fontSize: 12, fontWeight: 500 }} axisLine={false} tickLine={false}
                    domain={metric === "wape" ? [0, 0.25] : [0, "auto"]} ticks={metric === "wape" ? [0, 0.05, 0.1, 0.15, 0.2, 0.25] : undefined} />
                  <YAxis type="category" dataKey="label" tick={{ fill: "var(--text-2)", fontSize: 12 }} axisLine={{ stroke: "var(--axis)" }} tickLine={false} interval={0} width={104} />
                  <Tooltip content={<BarTip metric={metric} />} cursor={{ fill: "var(--hover)" }} />
                  {metric === "wape" && (
                    <ReferenceLine x={0.2} stroke="var(--text-3)" strokeDasharray="4 4"
                      label={{ value: "เป้า WAPE ≤ 20%", position: "top", fill: "var(--text-2)", fontSize: 12 }} />
                  )}
                  <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={32} isAnimationActive={false}>
                    {rows.map((m) => <Cell key={m.key} fill={m.color} />)}
                    <LabelList dataKey="value" position="right" formatter={(v) => METRICS[metric].fmt(Number(v))} fill="var(--text)" fontSize={12} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="table-wrap" style={{ marginTop: 16 }}>
              <table>
                <thead>
                  <tr><th className="left">โมเดล</th><th>WAPE</th><th>MAE</th><th>RMSE</th><th>จำนวนวันที่ประเมิน</th></tr>
                </thead>
                <tbody>
                  {all.map(({ key, label, color, r }) => (
                    <tr key={key} className={`${key === "ensemble" ? "highlight" : ""}${visible.has(key) ? "" : " muted"}`}>
                      <td className="left">
                        <Swatch kind="bar" color={color} /> {key === "ensemble" ? <>LSTM+GRU <span className="badge accent">โมเดลหลัก</span></> : label}
                      </td>
                      <td className={`num${metric === "wape" ? " sel" : ""}`}>{percent(r.wape)}</td>
                      <td className={`num${metric === "mae" ? " sel" : ""}`}>{money(r.mae)}</td>
                      <td className={`num${metric === "rmse" ? " sel" : ""}`}>{money(r.rmse)}</td>
                      <td className="num">{r.n_days.toLocaleString("en-US")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>
      <Card title="สรุป">
        <ul className="summary-list">
          <li>ทุกโมเดลที่เทรนผ่านเป้า WAPE ≤ 20% และดีกว่า seasonal naive เกือบ 3 เท่า</li>
          <li>ทดสอบ 5 random seed: LSTM+GRU ทัดเทียม LightGBM (8.32% ± 0.22 เทียบกับ 8.30% ± 0.06)</li>
          <li>WAPE = ผลรวมความคลาดเคลื่อนสัมบูรณ์ ÷ ผลรวมยอดขายจริง วัดเฉพาะวันที่ร้านเปิด</li>
        </ul>
      </Card>
    </>
  );
}
