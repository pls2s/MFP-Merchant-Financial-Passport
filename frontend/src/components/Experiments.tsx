import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api";
import { percent } from "../format";
import type { ModelExperiments, ModelResult } from "../types";
import { useAsync } from "../useAsync";
import { MODELS } from "./chartOptions";
import { Card, ErrorState, Segmented, Skeleton, Swatch } from "./ui";

/**
 * Robustness results under the main comparison: seed stability / seed averaging, ablation,
 * learning curves and the Favorita generalization test. All precomputed by
 * `ai.cashflow_forecast.experiments` — nothing is trained here.
 */

const TRAINED = MODELS.filter((m) => m.key !== "seasonal_naive");
const colorOf = (key: string) => MODELS.find((m) => m.key === key)?.color ?? "var(--text-3)";
const shortLabel = (key: string) => (key === "ensemble" ? "LSTM+GRU" : MODELS.find((m) => m.key === key)?.label ?? key);
const pts = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(2)}`;

const AXIS = { tick: { fill: "var(--text-2)", fontSize: 12 }, tickLine: false } as const;

function Legend({ keys }: { keys: readonly string[] }) {
  return (
    <div className="chart-legend">
      {keys.map((k) => <span key={k}><Swatch kind="line" color={colorOf(k)} />{shortLabel(k)}</span>)}
    </div>
  );
}

// --- Seeds ----------------------------------------------------------------------------

function SeedTip({ active, payload, label }: { active?: boolean; payload?: { dataKey: string; value: number }[]; label?: number }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <strong>เฉลี่ย {label} seed</strong>
      {payload.map((p) => <div key={p.dataKey}>{shortLabel(p.dataKey)} <b className="num">{percent(p.value)}</b></div>)}
    </div>
  );
}

function Seeds({ data }: { data: ModelExperiments }) {
  const ks = [1, 2, 3, 4, 5];
  const rows = ks.map((k) => Object.fromEntries([
    ["k", k], ...TRAINED.map((m) => [m.key, data.seed_ensemble_k.find((r) => r.model === m.key && r.k === k)?.mean]),
  ]));
  const at = (model: string, k: number) => data.seed_ensemble_k.find((r) => r.model === model && r.k === k);
  const final = (model: string, split: "val" | "test") => data.seed_ensemble.find((r) => r.model === model && r.split === split);

  return (
    <Card eyebrow="ความเสถียรข้าม random seed" title="เฉลี่ยหลาย seed ช่วยลดความแกว่งของ deep learning">
      <p className="muted small" style={{ marginTop: 0 }}>
        เทรนทุกโมเดลซ้ำ 5 seed (42, 1, 2, 3, 4) แล้วเฉลี่ยผลพยากรณ์ k seed ทุกชุดที่เป็นไปได้ เส้นคือ Test WAPE เฉลี่ย
      </p>
      <Legend keys={TRAINED.map((m) => m.key)} />
      <div style={{ width: "100%", height: 260 }}>
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="k" {...AXIS} axisLine={{ stroke: "var(--axis)" }} tickFormatter={(k) => `${k} seed`} />
            <YAxis {...AXIS} axisLine={false} width={56} domain={["auto", "auto"]} tickFormatter={(v) => percent(v, 1)} />
            <Tooltip content={<SeedTip />} />
            {TRAINED.map((m) => (
              <Line key={m.key} dataKey={m.key} stroke={m.color} strokeWidth={m.key === "ensemble" ? 3 : 2}
                dot={{ r: 3, fill: m.color, stroke: "none" }} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="table-wrap" style={{ marginTop: 12 }}>
        <table>
          <thead>
            <tr>
              <th className="left">โมเดล</th><th>1 seed (เฉลี่ย ± SD)</th><th>เฉลี่ย 5 seed · Test</th><th>เฉลี่ย 5 seed · Validation</th>
            </tr>
          </thead>
          <tbody>
            {TRAINED.map((m) => {
              const one = at(m.key, 1);
              return (
                <tr key={m.key} className={m.key === "ensemble" ? "highlight" : ""}>
                  <td className="left"><Swatch kind="line" color={m.color} /> {shortLabel(m.key)}</td>
                  <td className="num">{one ? `${percent(one.mean)} ± ${((one.std ?? 0) * 100).toFixed(2)}` : "—"}</td>
                  <td className="num">{percent(final(m.key, "test")?.wape ?? NaN)}</td>
                  <td className="num">{percent(final(m.key, "val")?.wape ?? NaN)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small chart-note">
        โมเดลหลักเลือกจาก Validation: LSTM+GRU 5 seed ได้ val WAPE ต่ำสุด · เมื่อเทียบกับ LightGBM 5 seed แบบ bootstrap ตามร้าน
        ส่วนต่าง −0.07 จุด (95% CI −0.14 ถึง −0.01) — ดีกว่าเล็กน้อยแต่สม่ำเสมอ ไม่ใช่ชนะขาด
      </p>
    </Card>
  );
}

// --- Ablation -------------------------------------------------------------------------

const ABLATION_LABELS: Record<string, string> = {
  no_window_norm: "ไม่ normalize ต่อ window",
  no_store_embedding: "ไม่มี store embedding",
  no_neighbour_features: "ไม่มีฟีเจอร์วันก่อน/วันถัดไป",
  unweighted_loss: "loss ไม่ถ่วงน้ำหนัก",
};

function Ablation({ data }: { data: ModelExperiments }) {
  const [split, setSplit] = useState<"test" | "val">("test");
  const wape = (variant: string) => data.ablation.find((r) => r.variant === variant && r.split === split)?.wape ?? NaN;
  const full = wape("full");
  const rows = Object.keys(ABLATION_LABELS)
    .map((v) => ({ label: ABLATION_LABELS[v], delta: wape(v) - full, wape: wape(v) }))
    .sort((a, b) => b.delta - a.delta);

  return (
    <Card eyebrow="Ablation study · LSTM seed 42" title="ตัดองค์ประกอบออกทีละอย่าง error เปลี่ยนเท่าไร"
      action={<Segmented label="ชุดข้อมูล" value={split} onChange={setSplit}
        options={[{ key: "test", label: "Test" }, { key: "val", label: "Validation" }]} />}>
      <p className="muted small" style={{ marginTop: 0 }}>
        แท่งไปทางขวา = error เพิ่มเมื่อตัดออก (องค์ประกอบนั้นช่วย) · โมเดลเต็มได้ {percent(full)}
      </p>
      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 88, bottom: 4, left: 8 }}>
            <CartesianGrid stroke="var(--grid)" horizontal={false} />
            <XAxis type="number" {...AXIS} axisLine={{ stroke: "var(--axis)" }} tickFormatter={(v) => pts(v)} />
            <YAxis type="category" dataKey="label" {...AXIS} axisLine={false} width={190} />
            <ReferenceLine x={0} stroke="var(--axis)" />
            <Bar dataKey="delta" radius={3} maxBarSize={22} isAnimationActive={false}>
              {rows.map((r) => <Cell key={r.label} fill={r.delta > 0 ? "var(--series-lstm)" : "var(--text-3)"} />)}
              <LabelList dataKey="delta" position="right" formatter={(v) => `${pts(Number(v))} จุด`} fill="var(--text)" fontSize={12} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small chart-note">
        ส่วนต่างที่เล็กกว่าความแกว่งข้าม seed ของ LSTM (SD 0.40 จุด) สรุปไม่ได้ว่ามีผล — ใช้ผล Test อธิบายเท่านั้น ไม่ได้ใช้เลือกโมเดล
      </p>
    </Card>
  );
}

// --- Learning curves ------------------------------------------------------------------

function Curves({ data }: { data: ModelExperiments }) {
  const configs = Object.entries(data.chosen_configs);
  const epochs = Math.max(...data.learning_curves.filter((p) => configs.some(([, c]) => c === p.config)).map((p) => p.epoch));
  const rows = Array.from({ length: epochs }, (_, i) => Object.fromEntries([
    ["epoch", i + 1],
    ...configs.map(([cell, c]) => [cell, data.learning_curves.find((p) => p.config === c && p.epoch === i + 1)?.val_wape]),
  ]));
  const best = configs.map(([cell, c]) => {
    const curve = data.learning_curves.filter((p) => p.config === c);
    const top = curve.reduce((a, b) => (b.val_wape < a.val_wape ? b : a));
    return { cell, config: c, epoch: top.epoch, wape: top.val_wape, epochs: curve.length };
  });

  return (
    <Card eyebrow="Learning curves · config ที่เลือก" title="Validation WAPE ระหว่างเทรน">
      <Legend keys={configs.map(([cell]) => cell)} />
      <div style={{ width: "100%", height: 240 }}>
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="epoch" {...AXIS} axisLine={{ stroke: "var(--axis)" }}
              label={{ value: "epoch", position: "insideBottomRight", offset: -2, fill: "var(--text-3)", fontSize: 11 }} />
            <YAxis {...AXIS} axisLine={false} width={56} domain={["auto", "auto"]} tickFormatter={(v) => percent(v, 1)} />
            <Tooltip formatter={(v, name) => [percent(Number(v)), shortLabel(String(name))]} labelFormatter={(e) => `epoch ${e}`}
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 }} />
            {configs.map(([cell]) => (
              <Line key={cell} dataKey={cell} stroke={colorOf(cell)} strokeWidth={2} dot={{ r: 2.5, fill: colorOf(cell), stroke: "none" }}
                connectNulls={false} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small chart-note">
        {best.map((b) => `${shortLabel(b.cell)} (${b.config}) ดีสุด ${percent(b.wape)} ที่ epoch ${b.epoch} หยุดที่ epoch ${b.epochs}`).join(" · ")}
        {" "}— early stopping (patience 4) คืนน้ำหนักของ epoch ที่ดีที่สุด
      </p>
    </Card>
  );
}

// --- Favorita -------------------------------------------------------------------------

function Favorita({ rows }: { rows: ModelResult[] }) {
  const get = (model: string, split: "val" | "test") => rows.find((r) => r.model === model && r.split === split);
  const bestTest = Math.min(...rows.filter((r) => r.split === "test").map((r) => r.wape));
  return (
    <Card eyebrow="ทดสอบกับข้อมูลชุดอื่น" title="Favorita Store Sales (54 สาขา, เอกวาดอร์)">
      <p className="muted small" style={{ marginTop: 0 }}>
        ใช้ config ที่เลือกจาก Rossmann โดยไม่ปรับจูนใหม่ แบ่งข้อมูลแบบเดียวกัน (42 วัน Validation, 42 วัน Test) · seed 42
      </p>
      <div className="table-wrap">
        <table>
          <thead><tr><th className="left">โมเดล</th><th>Validation WAPE</th><th>Test WAPE</th><th>จำนวนวันที่ประเมิน</th></tr></thead>
          <tbody>
            {MODELS.map((m) => {
              const t = get(m.key, "test");
              if (!t) return null;
              return (
                <tr key={m.key}>
                  <td className="left"><Swatch kind="bar" color={m.color} /> {m.key === "ensemble" ? "LSTM+GRU (seed 42)" : m.label}</td>
                  <td className="num">{percent(get(m.key, "val")?.wape ?? NaN)}</td>
                  <td className={`num${t.wape === bestTest ? " sel" : ""}`}>{percent(t.wape)}</td>
                  <td className="num">{t.n_days.toLocaleString("en-US")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small chart-note">
        ทุกโมเดลผ่านเป้า WAPE ≤ 20% · บน Favorita LightGBM ดีที่สุดบน Test — deep learning มีข้อมูลเรียนน้อยกว่ามาก (ประมาณ 68,000 windows เทียบกับ 834,000)
      </p>
    </Card>
  );
}

export function Experiments() {
  const [state, retry] = useAsync(api.modelExperiments, []);
  if (state.status === "loading") return <Skeleton height={300} />;
  if (state.status === "error") return <Card><ErrorState error={state.error} onRetry={retry} /></Card>;
  return (
    <>
      <Seeds data={state.data} />
      <Ablation data={state.data} />
      <div className="grid-2">
        <Curves data={state.data} />
        <Favorita rows={state.data.favorita} />
      </div>
    </>
  );
}
