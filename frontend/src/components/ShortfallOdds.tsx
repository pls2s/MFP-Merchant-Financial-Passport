import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { money, oddsText, thaiDate, thaiDateShort } from "../format";
import type { ShortfallRisk } from "../types";

/**
 * "โอกาสที่เงินจะไม่พอ" — the share of simulated 14-day sales paths (MC dropout of the LSTM+GRU
 * ensemble × day-to-day noise from Validation) in which the balance drops below zero.
 * Computed offline by ai.gap_detection.shortfall_risk; nothing runs live here.
 */

export function OddsPill({ p }: { p: number | undefined }) {
  if (p == null) return null;
  const tone = p >= 0.5 ? "danger" : p >= 0.2 ? "warn" : "";
  return <span className={`badge ${tone}`} title="โอกาสที่เงินจะไม่พอวันนั้น จากการจำลองยอดขาย">โอกาส {oddsText(p)}</span>;
}

function Tip({ active, payload }: { active?: boolean; payload?: { payload: ShortfallRisk["days"][number] }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{thaiDate(d.date)}</strong>
      <div>โอกาสเงินไม่พอ <b className="num">{oddsText(d.p_shortfall)}</b></div>
      <div className="muted">ยอดเงินสิ้นวัน (กลาง) <span className="num">{money(d.balance_p50)}</span></div>
      <div className="muted">80% ของสถานการณ์อยู่ระหว่าง <span className="num">{money(d.balance_p10)} – {money(d.balance_p90)}</span></div>
    </div>
  );
}

export function ShortfallOdds({ risk }: { risk: ShortfallRisk }) {
  const c = risk.check;
  const better = 1 - c.brier_probability / c.brier_yes_no_warning;
  return (
    <div className="odds">
      <div className="odds-head">
        <div>
          <div className="stat-label">โอกาสที่เงินจะไม่พออย่างน้อย 1 วันใน 14 วันข้างหน้า</div>
          <div className={`odds-value ${risk.p_any >= 0.5 ? "bad-text" : risk.p_any >= 0.2 ? "warn-text" : "good-text"}`}>
            {oddsText(risk.p_any)}
          </div>
        </div>
        <p className="muted small">
          จากการจำลองยอดขาย 14 วันข้างหน้า {risk.n_paths} แบบ แล้วนับว่ากี่แบบที่ยอดเงินติดลบ · แท่ง = โอกาสรายวัน
        </p>
      </div>
      <div style={{ width: "100%", height: 150 }}>
        <ResponsiveContainer>
          <BarChart data={risk.days} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="date" tickFormatter={thaiDateShort} tick={{ fill: "var(--text-2)", fontSize: 11 }} tickLine={false}
              axisLine={{ stroke: "var(--axis)" }} interval={1} />
            <YAxis domain={[0, 1]} ticks={[0, 0.5, 1]} tickFormatter={(v) => `${v * 100}%`} width={40}
              tick={{ fill: "var(--text-2)", fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip content={<Tip />} cursor={{ fill: "var(--hover)" }} />
            <Bar dataKey="p_shortfall" radius={[3, 3, 0, 0]} isAnimationActive={false}>
              {risk.days.map((d) => (
                <Cell key={d.date} fill={d.p_shortfall >= 0.5 ? "var(--bad)" : d.p_shortfall >= 0.2 ? "var(--warn)" : "var(--text-3)"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="how">
        <summary>หา % จากไหน</summary>
        <ol>
          <li>
            <b>Deep learning ทายยอดขายซ้ำหลายรอบ</b> — โมเดลหลัก (LSTM + GRU, 5 seed = 10 โมเดล) ทายยอดขาย 14 วันข้างหน้า
            ตัวละ 20 รอบ โดย<b>เปิด dropout ไว้ตอนทาย</b> (Monte Carlo dropout) แต่ละรอบปิดส่วนของโมเดลแบบสุ่ม 20%
            คำตอบจึงต่างกันเล็กน้อยในจุดที่โมเดลไม่มั่นใจ ได้ {risk.n_paths} แบบ
          </li>
          <li>
            <b>ใส่ความผันผวนรายวันที่โมเดลทายไม่ได้</b> — คูณแต่ละแบบด้วย error จริง 14 วันติดกัน (ยอดจริง ÷ ที่ทาย)
            ที่สุ่มจากช่วง Validation ของทุกร้าน ใช้ทั้งก้อน 14 วันเพื่อให้สัปดาห์ที่ขายไม่ดีมักไม่ดีต่อเนื่องเหมือนของจริง
          </li>
          <li>
            <b>คำนวณยอดเงินแต่ละแบบ</b> — ยอดเงินวันนี้ + ยอดขายแบบนั้น − รายจ่ายจำลอง (สูตรเดียวกับการแจ้งเตือน)
            แล้ว <b>% = จำนวนแบบที่ยอดเงินติดลบในวันนั้น ÷ {risk.n_paths}</b>
          </li>
        </ol>
        <p>
          <b>ตรวจย้อนหลังกับช่วง Test</b> ({c.origins.map(thaiDateShort).join(", ")} · ทุกร้านยกเว้นร้านสาธิต · {c.store_days.toLocaleString("en-US")} ร้าน-วัน,
          เงินไม่พอจริง {c.events.toLocaleString("en-US")} ครั้ง):
          ช่วง 80% ของยอดขายจำลองครอบยอดจริง <b>{Math.round(c.sales_interval_80_coverage * 100)}%</b> ของวัน ·
          ความคลาดเคลื่อนของ % (Brier score) <b className="num">{c.brier_probability.toFixed(4)}</b> เทียบกับเตือนแบบ ใช่/ไม่ใช่{" "}
          <b className="num">{c.brier_yes_no_warning.toFixed(4)}</b>
          {better > 0 ? ` (ดีกว่า ${Math.round(better * 100)}%)` : ""} และเดาค่าเฉลี่ยอย่างเดียว <b className="num">{c.brier_base_rate.toFixed(4)}</b> — ยิ่งต่ำยิ่งดี
        </p>
        {c.sales_interval_80_coverage < 0.78 && (
          <p>
            <b>ข้อจำกัด:</b> ช่วงยอดขายจำลองยังแคบกว่าที่ควร (ครอบ {Math.round(c.sales_interval_80_coverage * 100)}% แทน 80%)
            % ที่อยู่กลาง ๆ จึงอาจต่ำกว่าความเสี่ยงจริง — ใช้ดูว่าวันไหนเสี่ยงกว่าวันไหน มากกว่าอ่านเป็นตัวเลขแม่นยำ
          </p>
        )}
        <p className="muted small">
          รายจ่ายและยอดเงินเป็นข้อมูลจำลอง % นี้จึงเป็นโอกาสของร้านจำลอง ไม่ใช่การรับประกัน และไม่ได้ใช้ตัดสินสินเชื่อ
        </p>
      </details>
    </div>
  );
}
