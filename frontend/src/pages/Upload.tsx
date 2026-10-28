import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, CartesianGrid, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, isMock } from "../api";
import { Card, SampleBadge, Swatch } from "../components/ui";
import { money, percent, thaiDate, thaiDateShort } from "../format";
import type { UploadForecast } from "../types";

/**
 * Screen 4 — try the model on a shop it has never seen (cold start, report 9.2).
 * The sample (UCI Online Retail) is precomputed; an uploaded file runs the model live on the backend.
 */

type State =
  | { status: "idle" }
  | { status: "loading"; what: string }
  | { status: "error"; message: string }
  | { status: "ok"; data: UploadForecast };

function Chart({ data }: { data: UploadForecast }) {
  const last = data.history[data.history.length - 1].date;
  const rows = [
    ...data.history.map((h) => ({ date: h.date, actual: h.sales || null, forecast: null as number | null })),
    ...data.forecast.map((f) => ({ date: f.date, actual: null as number | null, forecast: f.forecast || null })),
  ];
  return (
    <>
      <div className="chart-legend">
        <span><Swatch kind="bar" color="var(--series-actual)" />ยอดขายจริงจากไฟล์ (รวมเป็นรายวัน)</span>
        <span><Swatch kind="bar" color="var(--series-forecast)" />ที่โมเดลทาย 14 วันข้างหน้า</span>
        <span className="muted">ช่องว่าง = ไม่มียอดขาย (ร้านปิด)</span>
      </div>
      <div style={{ width: "100%", height: 300 }}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={1}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="date" tickFormatter={thaiDateShort} minTickGap={40} tick={{ fill: "var(--text-2)", fontSize: 12 }}
              tickLine={false} axisLine={{ stroke: "var(--axis)" }} />
            <YAxis tickFormatter={money} width={64} tick={{ fill: "var(--text-2)", fontSize: 12 }} tickLine={false} axisLine={false} />
            <Tooltip labelFormatter={(d) => thaiDate(String(d))} formatter={(v, name) => [money(Number(v)), name === "actual" ? "ยอดจริง" : "ที่ทาย"]}
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 }} />
            <ReferenceLine x={last} stroke="var(--text-3)" strokeDasharray="4 4"
              label={{ value: "ข้อมูลล่าสุด", position: "insideTopLeft", fill: "var(--text-2)", fontSize: 11 }} />
            <Bar dataKey="actual" fill="var(--series-actual)" fillOpacity={0.8} isAnimationActive={false} />
            <Bar dataKey="forecast" fill="var(--series-forecast)" isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

function Result({ data }: { data: UploadForecast }) {
  const bt = data.backtest;
  const beats = bt.wape_model != null && bt.wape_naive != null && bt.wape_model < bt.wape_naive;
  const total = data.forecast.reduce((s, f) => s + f.forecast, 0);
  return (
    <>
      <div className="summary-grid">
        <section className="stat-card">
          <div className="stat-label">ข้อมูลในไฟล์</div>
          <div className="stat-value small-value">{data.days.toLocaleString("en-US")} วัน</div>
          <div className="stat-sub">{thaiDate(data.date_range.start)} – {thaiDate(data.date_range.end)} · มียอดขาย {data.open_days} วัน</div>
        </section>
        <section className="stat-card">
          <div className="stat-label">คาดว่า 14 วันข้างหน้า</div>
          <div className="stat-value">{money(total)}</div>
          <div className="stat-sub">หลัง {thaiDate(data.date_range.end)} · ปรับระดับ × {data.level_factor.toFixed(2)}</div>
        </section>
        <section className={`stat-card ${beats ? "tone-good" : "tone-bad"}`}>
          <div className="stat-label">ทดสอบย้อนหลัง {bt.days} วัน (WAPE ยิ่งต่ำยิ่งดี)</div>
          <div className="stat-value">{bt.wape_model != null ? percent(bt.wape_model, 1) : "—"}</div>
          <div className="stat-sub">
            วิธีง่าย (ยอดเท่าสัปดาห์ก่อน) {bt.wape_naive != null ? percent(bt.wape_naive, 1) : "—"} ·{" "}
            {beats ? <span className="good-text">✓ โมเดลแม่นกว่า</span> : <span className="bad-text">โมเดลแย่กว่า</span>}
          </div>
        </section>
      </div>

      <Card eyebrow={data.source === "live" ? "รันโมเดลจากไฟล์ที่อัปโหลด" : "คำนวณไว้ล่วงหน้า"} title={data.name}
        badges={<span className="badge accent">LSTM+GRU · cold start</span>}>
        <Chart data={data} />
        <ul className="summary-list" style={{ marginTop: 12 }}>
          {data.notes.map((n) => <li key={n}>{n}</li>)}
        </ul>
      </Card>

      <Card eyebrow="ทดสอบย้อนหลังกับข้อมูลของร้านนี้เอง" title="แม่นแค่ไหนกับร้านที่โมเดลไม่เคยเห็น">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="left">14 วันหลังวันที่</th><th>ปรับระดับ ×</th><th>โมเดล (ปรับระดับแล้ว)</th>
                <th>โมเดล (ไม่ปรับ)</th><th>ยอดเท่าสัปดาห์ก่อน</th>
              </tr>
            </thead>
            <tbody>
              {bt.blocks.map((b) => (
                <tr key={b.origin}>
                  <td className="left">{thaiDate(b.origin)}</td>
                  <td className="num">{b.level_factor.toFixed(2)}</td>
                  <td className={`num${b.wape_model != null && b.wape_naive != null && b.wape_model < b.wape_naive ? " sel" : ""}`}>
                    {b.wape_model != null ? percent(b.wape_model, 1) : "—"}
                  </td>
                  <td className="num">{b.wape_raw != null ? percent(b.wape_raw, 1) : "—"}</td>
                  <td className="num">{b.wape_naive != null ? percent(b.wape_naive, 1) : "—"}</td>
                </tr>
              ))}
              <tr className="highlight">
                <td className="left">รวม</td><td />
                <td className="num">{bt.wape_model != null ? percent(bt.wape_model, 1) : "—"}</td>
                <td className="num">{bt.wape_raw != null ? percent(bt.wape_raw, 1) : "—"}</td>
                <td className="num">{bt.wape_naive != null ? percent(bt.wape_naive, 1) : "—"}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="muted small chart-note">
          แต่ละช่วงใช้แค่ข้อมูลก่อนวันนั้น: ตัวคูณปรับระดับคำนวณจาก {bt.calib_blocks} ช่วงก่อนหน้า (ยอดจริงรวม ÷ ที่โมเดลทายรวม)
          · วัดเฉพาะวันที่มียอดขาย · เทียบกับร้าน Rossmann ที่โมเดลรู้จัก (WAPE ประมาณ 8%) ร้านใหม่จะคลาดมากกว่าเสมอ
        </p>
      </Card>
    </>
  );
}

export function Upload() {
  const [state, setState] = useState<State>({ status: "idle" });
  const [params] = useSearchParams();
  const load = (what: string, p: Promise<UploadForecast>) => {
    setState({ status: "loading", what });
    p.then((data) => setState({ status: "ok", data }), (e: Error) => setState({ status: "error", message: e.message }));
  };
  // /upload?sample=1 opens straight on the sample (handy for the demo)
  useEffect(() => {
    if (params.get("sample") === "1") load("ข้อมูลตัวอย่าง", api.uploadSample());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <div className="page-head">
        <div className="title-row">
          <div>
            <div className="eyebrow">ร้านที่โมเดลไม่เคยเห็น · cold start</div>
            <h1>ลองพยากรณ์ร้านอื่นจากไฟล์ยอดขาย</h1>
          </div>
        </div>
        <p className="muted">
          ใช้โมเดล LSTM+GRU ที่เทรนจากร้าน Rossmann โดยไม่เทรนใหม่ แล้วทดสอบย้อนหลังกับข้อมูลของร้านนั้นเอง
        </p>
      </div>

      <Card title="เลือกข้อมูล">
        <div className="upload-options">
          <div className="upload-option">
            <h3>ข้อมูลตัวอย่าง <SampleBadge /></h3>
            <p className="muted small">
              UCI Online Retail — ร้านขายส่งออนไลน์ในอังกฤษ 541,909 รายการ (ธ.ค. 2553 – ธ.ค. 2554, CC BY 4.0)
              เป็นข้อมูลจริงสาธารณะ ไม่ใช่ร้านค้าไทย · ผลคำนวณไว้ล่วงหน้า
            </p>
            <button className="btn primary" onClick={() => load("ข้อมูลตัวอย่าง", api.uploadSample())}
              disabled={state.status === "loading"}>
              ใช้ข้อมูลตัวอย่าง
            </button>
          </div>
          <div className="upload-option">
            <h3>อัปโหลดไฟล์ของร้าน</h3>
            <p className="muted small">
              .csv หรือ .xlsx ไม่เกิน 30 MB · คอลัมน์ <code>date</code> + <code>sales</code> (รายวัน)
              หรือ <code>InvoiceDate</code> + <code>Quantity</code> + <code>UnitPrice</code> (รายบิล) ·
              อย่างน้อย 70 วัน · ไฟล์ส่งไปประมวลผลที่ backend ของระบบนี้เท่านั้น
            </p>
            <input type="file" accept=".csv,.xlsx" disabled={isMock || state.status === "loading"} aria-label="เลือกไฟล์ยอดขาย"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) load(file.name, api.upload(file));
                e.target.value = "";
              }} />
            {isMock && <p className="muted small">โหมด mock อัปโหลดไม่ได้ (ต้องมี backend) — ใช้ข้อมูลตัวอย่างแทน</p>}
            {!isMock && <p className="muted small">ครั้งแรกอาจใช้เวลาราว 1 นาที (โหลดโมเดล 10 ตัว)</p>}
          </div>
        </div>
        {state.status === "loading" && <p className="state"><span className="spinner" /> กำลังประมวลผล {state.what}…</p>}
        {state.status === "error" && <div className="alert bad" style={{ marginTop: 12 }}>{state.message}</div>}
      </Card>

      {state.status === "ok" && <Result data={state.data} />}
    </>
  );
}
