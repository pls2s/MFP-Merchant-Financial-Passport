import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { Card, SampleBadge, Swatch } from "../components/ui";
import { money, percent, thaiDate, thaiDateShort } from "../format";
import type { ColumnMapping, ReadReport, UploadForecast, UploadInspect } from "../types";

/**
 * Screen 4 — try the model on a shop it has never seen (cold start, report 9.2).
 * The sample (UCI Online Retail) is precomputed. An uploaded file goes through two steps:
 * inspect (backend reads it, guesses the columns, reports what it read — no model), then, once the
 * person confirms the columns, the model runs live on the backend.
 */

type State =
  | { status: "idle" }
  | { status: "loading"; what: string; since: number }
  | { status: "error"; message: string }
  | { status: "inspected"; file: File; inspect: UploadInspect; checking: boolean }
  | { status: "ok"; data: UploadForecast };

const ROLE_LABELS: Record<keyof ColumnMapping, string> = {
  date: "วันที่", sales: "ยอดขาย", quantity: "จำนวน", price: "ราคาต่อหน่วย",
};

function ReportSummary({ report }: { report: ReadReport }) {
  return (
    <ul className="read-report">
      <li>
        อ่านวันที่แบบ <b>{report.date_format}</b> · ได้ <b>{report.days.toLocaleString("en-US")} วัน</b>{" "}
        ({thaiDate(report.date_range.start)} – {thaiDate(report.date_range.end)}) · มียอดขาย {report.open_days} วัน
      </li>
      <li>ยอดขายจาก <b>{report.amount_source}</b> · ใช้ {report.rows_used.toLocaleString("en-US")} จาก {report.rows.toLocaleString("en-US")} แถว</li>
      {report.skipped.map((s) => (
        <li key={s.reason} className="warn-text">
          ข้าม {s.count.toLocaleString("en-US")} แถว — {s.reason} (แถว {s.rows.join(", ")}{s.count > s.rows.length ? ", …" : ""})
        </li>
      ))}
      {report.notes.map((n) => <li key={n}>{n}</li>)}
    </ul>
  );
}

function Inspect({ file, inspect, checking, onMapping, onForecast }: {
  file: File; inspect: UploadInspect; checking: boolean;
  onMapping: (m: Partial<ColumnMapping>) => void; onForecast: () => void;
}) {
  const m = inspect.mapping;
  const byTransaction = !m.sales && !!m.quantity && !!m.price;
  const used = new Set(Object.values(byTransaction ? { d: m.date, q: m.quantity, p: m.price } : { d: m.date, s: m.sales }));
  const select = (role: keyof ColumnMapping) => (
    <label className="select-wrap" key={role}>
      <span className="muted small">{ROLE_LABELS[role]}</span>
      <select className="select" value={m[role] ?? ""} disabled={checking}
        onChange={(e) => onMapping({ ...m, [role]: e.target.value || null })}>
        <option value="">— เลือกคอลัมน์ —</option>
        {inspect.columns.map((c) => <option key={c} value={c}>{c}{inspect.guessed[role] === c ? " (เดา)" : ""}</option>)}
      </select>
    </label>
  );
  const r = inspect.report;
  return (
    <Card eyebrow={`ขั้นที่ 1 · ตรวจไฟล์ ${file.name}`} title="ตรวจว่าระบบอ่านไฟล์ถูกต้อง ก่อนพยากรณ์">
      <div className="table-wrap scroll" style={{ maxHeight: 220 }}>
        <table className="preview">
          <thead><tr>{inspect.columns.map((c) => <th key={c} className={`left${used.has(c) ? " mapped" : ""}`}>{c}</th>)}</tr></thead>
          <tbody>
            {inspect.preview.map((row, i) => (
              <tr key={i}>{inspect.columns.map((c) => <td key={c} className={`left${used.has(c) ? " mapped" : ""}`}>{row[c] ?? ""}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">ตัวอย่าง {inspect.preview.length} แถวแรก · คอลัมน์ที่ใช้มีพื้นสี · encoding {inspect.encoding}</p>

      <div className="filter-bar">
        <span className="filter-label">ยอดขายมาจาก</span>
        <button className={`chip${!byTransaction ? " on" : ""}`} disabled={checking}
          onClick={() => onMapping({ ...m, quantity: null, price: null, sales: m.sales ?? inspect.guessed.sales })}>คอลัมน์ยอดขาย</button>
        <button className={`chip${byTransaction ? " on" : ""}`} disabled={checking}
          onClick={() => onMapping({ ...m, sales: null, quantity: m.quantity ?? inspect.guessed.quantity, price: m.price ?? inspect.guessed.price })}>
          จำนวน × ราคาต่อหน่วย
        </button>
      </div>
      <div className="mapping">
        {select("date")}
        {byTransaction ? [select("quantity"), select("price")] : select("sales")}
        {checking && <span className="muted small"><span className="spinner" /> กำลังอ่านใหม่…</span>}
      </div>

      {!inspect.ok && <div className="alert bad">{inspect.error}</div>}
      {r && (
        <>
          <ReportSummary report={r} />
          <div style={{ width: "100%", height: 120 }}>
            <ResponsiveContainer>
              <BarChart data={inspect.daily} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap={0}>
                <XAxis dataKey="date" tickFormatter={thaiDateShort} minTickGap={50} tick={{ fill: "var(--text-2)", fontSize: 11 }}
                  tickLine={false} axisLine={{ stroke: "var(--axis)" }} />
                <YAxis hide />
                <Tooltip labelFormatter={(d) => thaiDate(String(d))} formatter={(v) => [money(Number(v)), "ยอดขาย"]}
                  contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 }} />
                <Bar dataKey="sales" fill="var(--series-actual)" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="muted small">ยอดขายรายวันที่อ่านได้ — ถ้ารูปร่างหรือช่วงวันที่ดูผิด ให้เปลี่ยนคอลัมน์ด้านบน</p>
          {!r.enough_days && (
            <div className="alert bad">ต้องมีข้อมูลอย่างน้อย {r.min_days} วัน (อ่านได้ {r.days} วัน) จึงจะพยากรณ์และทดสอบย้อนหลังได้</div>
          )}
        </>
      )}
      <div style={{ marginTop: 12 }}>
        <button className="btn primary" disabled={checking || !inspect.ok || !r?.enough_days} onClick={onForecast}>
          ขั้นที่ 2 · ถูกต้องแล้ว พยากรณ์เลย
        </button>
      </div>
    </Card>
  );
}

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
        {data.read_report && <ReportSummary report={data.read_report} />}
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

const ACCEPT = [".csv", ".xlsx"];
const MAX_MB = 30;

/** A small daily-sales template so people can see the expected layout. */
function downloadTemplate() {
  const start = new Date(Date.UTC(2024, 0, 1));
  const rows = ["date,sales"];
  for (let i = 0; i < 84; i++) {
    const d = new Date(start.getTime() + i * 86_400_000);
    const sunday = d.getUTCDay() === 0;
    rows.push(`${d.toISOString().slice(0, 10)},${sunday ? 0 : 4000 + ((i * 37) % 900)}`);
  }
  const url = URL.createObjectURL(new Blob([rows.join("\n") + "\n"], { type: "text/csv" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: "sales_template.csv" });
  a.click();
  URL.revokeObjectURL(url);
}

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return <span className="num">{Math.round((now - since) / 1000)} วินาที</span>;
}

function DropZone({ disabled, onFile }: { disabled: boolean; onFile: (f: File) => void }) {
  const [over, setOver] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const pick = (f: File | undefined) => {
    if (!f) return;
    if (!ACCEPT.some((ext) => f.name.toLowerCase().endsWith(ext))) return setProblem("รองรับเฉพาะ .csv และ .xlsx");
    if (f.size > MAX_MB * 1024 * 1024) return setProblem(`ไฟล์ใหญ่เกิน ${MAX_MB} MB`);
    setProblem(null);
    onFile(f);
  };
  return (
    <>
      <label className={`dropzone${over ? " over" : ""}${disabled ? " disabled" : ""}`}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) pick(e.dataTransfer.files[0]); }}>
        <input type="file" accept={ACCEPT.join(",")} disabled={disabled} aria-label="เลือกไฟล์ยอดขาย"
          onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
        <span className="dropzone-icon" aria-hidden>⇪</span>
        <b>ลากไฟล์มาวางที่นี่ หรือคลิกเพื่อเลือก</b>
        <span className="muted small">.csv หรือ .xlsx ไม่เกิน {MAX_MB} MB</span>
      </label>
      {problem && <p className="bad-text small">{problem}</p>}
    </>
  );
}

export function Upload() {
  const [state, setState] = useState<State>({ status: "idle" });
  const [params] = useSearchParams();
  const load = (what: string, p: Promise<UploadForecast>) => {
    setState({ status: "loading", what, since: Date.now() });
    p.then((data) => setState({ status: "ok", data }), (e: Error) => setState({ status: "error", message: e.message }));
  };
  const check = (file: File, mapping?: Partial<ColumnMapping>) => {
    if (state.status === "inspected") setState({ ...state, checking: true });
    else setState({ status: "loading", what: `ตรวจไฟล์ ${file.name}`, since: Date.now() });
    api.inspectUpload(file, mapping).then(
      (inspect) => setState({ status: "inspected", file, inspect, checking: false }),
      (e: Error) => setState({ status: "error", message: e.message }),
    );
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
              ไฟล์รายวัน (วันที่ + ยอดขาย) หรือรายบิล (วันที่ + จำนวน + ราคา) หัวคอลัมน์ไทยหรืออังกฤษก็ได้ ·
              วันที่ วว/ดด/ปปปป, ปี พ.ศ. และตัวเลขมี comma อ่านได้ · อย่างน้อย 70 วัน ·
              ระบบจะให้ตรวจก่อนพยากรณ์ · ไฟล์ส่งไปประมวลผลที่ backend ของระบบนี้เท่านั้น
            </p>
            <DropZone disabled={state.status === "loading"} onFile={(f) => check(f)} />
            <p className="muted small">
              ประมวลผลที่ backend (ต้องเปิดอยู่ แม้หน้าอื่นจะใช้โหมด mock) · ครั้งแรกราว 1 นาที (โหลดโมเดล 10 ตัว) ครั้งต่อไปไม่กี่วินาที ·{" "}
              <button className="link-btn" onClick={downloadTemplate}>ดาวน์โหลดไฟล์แม่แบบ (.csv)</button>
            </p>
          </div>
        </div>
        {state.status === "loading" && (
          <p className="state"><span className="spinner" /> กำลังประมวลผล {state.what}… <Elapsed since={state.since} /></p>
        )}
        {state.status === "error" && <div className="alert bad" style={{ marginTop: 12 }}>{state.message}</div>}
      </Card>

      {state.status === "inspected" && (
        <Inspect file={state.file} inspect={state.inspect} checking={state.checking}
          onMapping={(m) => check(state.file, m)}
          onForecast={() => load(state.file.name, api.upload(state.file, state.inspect.mapping))} />
      )}
      {state.status === "ok" && <Result data={state.data} />}
    </>
  );
}
