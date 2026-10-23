import { useState } from "react";
import { Bar, BarChart, Cell, LabelList, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { Card, ErrorState, Skeleton } from "../components/ui";
import { money, percent } from "../format";
import { useAsync } from "../useAsync";

const MODELS = [
  { key: "seasonal_naive", label: "Seasonal naive", color: "var(--text-3)" },
  { key: "lightgbm", label: "LightGBM", color: "var(--series-lgbm)" },
  { key: "lstm", label: "LSTM", color: "#1baf7a" },
  { key: "gru", label: "GRU", color: "#eda100" },
  { key: "ensemble", label: "LSTM+GRU (โมเดลหลัก)", color: "var(--accent)" },
];

export function ModelResults() {
  const [state, retry] = useAsync(api.modelResults, []);
  const [split, setSplit] = useState<"test" | "val">("test");

  const rows = state.status === "ok"
    ? MODELS.map((m) => ({ ...m, r: state.data.find((r) => r.model === m.key && r.split === split) }))
        .filter((m) => m.r)
    : [];

  return (
    <>
      <div className="page-head">
        <h1>ผลการทดลองโมเดลพยากรณ์</h1>
        <p>พยากรณ์ยอดขายรายวันล่วงหน้า 14 วัน · ร้าน Rossmann 1,115 ร้าน</p>
      </div>
      <Card
        title="เปรียบเทียบโมเดล"
        action={
          <div className="toggle" role="tablist">
            <button className={split === "test" ? "on" : ""} onClick={() => setSplit("test")}>Test</button>
            <button className={split === "val" ? "on" : ""} onClick={() => setSplit("val")}>Validation</button>
          </div>
        }
      >
        {state.status === "loading" && <Skeleton height={260} />}
        {state.status === "error" && <ErrorState error={state.error} onRetry={retry} />}
        {state.status === "ok" && (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>โมเดล</th><th>WAPE</th><th>MAE</th><th>RMSE</th><th>จำนวนวันที่ประเมิน</th></tr>
                </thead>
                <tbody>
                  {rows.map(({ key, label, r }) => (
                    <tr key={key} className={key === "ensemble" ? "highlight" : ""}>
                      <td>{label}</td>
                      <td className="num">{percent(r!.wape)}</td>
                      <td className="num">{money(r!.mae)}</td>
                      <td className="num">{money(r!.rmse)}</td>
                      <td className="num">{r!.n_days.toLocaleString("en-US")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ width: "100%", height: 240, marginTop: 20 }}>
              <ResponsiveContainer>
                <BarChart data={rows.map((m) => ({ label: m.label.replace(" (โมเดลหลัก)", ""), wape: m.r!.wape, color: m.color }))}
                  margin={{ top: 20, right: 8, bottom: 0, left: 0 }}>
                  <XAxis dataKey="label" tick={{ fill: "var(--text-2)", fontSize: 12 }} axisLine={{ stroke: "var(--border)" }} tickLine={false} interval={0} />
                  <YAxis tickFormatter={(v: number) => percent(v, 0)} tick={{ fill: "var(--text-2)", fontSize: 12 }} axisLine={false} tickLine={false} width={44} domain={[0, 0.25]} ticks={[0, 0.05, 0.1, 0.15, 0.2, 0.25]} />
                  <ReferenceLine y={0.2} stroke="var(--text-3)" strokeDasharray="4 4"
                    label={{ value: "เป้า WAPE ≤ 20%", position: "insideTopRight", fill: "var(--text-2)", fontSize: 12 }} />
                  <Bar dataKey="wape" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                    {rows.map((m) => <Cell key={m.key} fill={m.color} />)}
                    <LabelList dataKey="wape" position="top" formatter={(v) => percent(Number(v))} fill="var(--text)" fontSize={12} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </Card>
      <Card title="สรุป">
        <ul style={{ margin: 0, paddingLeft: 20 }}>
          <li>ทุกโมเดลที่เทรนผ่านเป้า WAPE ≤ 20% และดีกว่า seasonal naive เกือบ 3 เท่า</li>
          <li>ทดสอบ 5 random seed: LSTM+GRU ทัดเทียม LightGBM (8.32% ± 0.22 เทียบกับ 8.30% ± 0.06)</li>
          <li>WAPE = ผลรวมความคลาดเคลื่อนสัมบูรณ์ ÷ ผลรวมยอดขายจริง วัดเฉพาะวันที่ร้านเปิด</li>
        </ul>
      </Card>
    </>
  );
}
