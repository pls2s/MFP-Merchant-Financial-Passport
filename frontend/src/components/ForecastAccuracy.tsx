import { money, percent, thaiDate } from "../format";
import type { Forecast, ModelResult } from "../types";

/** How well the model did on days it forecast before seeing the actual sales (up to "today"). */
export function ForecastAccuracy({ forecast, asOf, results }: {
  forecast: Forecast;
  asOf: string;
  results: ModelResult[];
}) {
  const days = forecast.points.filter((p) => p.date <= asOf && (p.actual ?? 0) > 0 && p.forecast > 0);
  if (!days.length) return null;

  const absErr = days.map((p) => Math.abs(p.forecast - p.actual!));
  const wape = absErr.reduce((a, b) => a + b, 0) / days.reduce((a, p) => a + p.actual!, 0);
  const within10 = days.filter((p, i) => absErr[i] / p.actual! <= 0.1).length;
  const worst = days.reduce((w, p, i) => (absErr[i] / p.actual! > Math.abs(w.forecast - w.actual!) / w.actual! ? p : w), days[0]);
  const worstErr = (worst.forecast - worst.actual!) / worst.actual!;
  const allStores = results.find((r) => r.model === "ensemble" && r.split === "test");

  return (
    <div className="accuracy">
      <div className="accuracy-head">
        <strong>โมเดลทายร้านนี้แม่นแค่ไหน</strong>
        <span className="muted small">
          ทดสอบย้อนหลัง {days.length} วันที่ร้านเปิด ({thaiDate(days[0].date)} – {thaiDate(days[days.length - 1].date)})
          โดยโมเดลพยากรณ์ล่วงหน้าสูงสุด 14 วัน ไม่เห็นยอดขายจริงของวันนั้น
        </span>
      </div>
      <div className="accuracy-grid">
        <div>
          <div className="stat-label">คลาดเคลื่อนเฉลี่ย (WAPE)</div>
          <div className="accuracy-value num">{percent(wape, 1)}</div>
          {allStores && <div className="stat-sub">เฉลี่ยทุกร้าน {percent(allStores.wape, 1)}</div>}
        </div>
        <div>
          <div className="stat-label">วันที่ทายคลาดไม่เกิน 10%</div>
          <div className="accuracy-value num">{within10}/{days.length} วัน</div>
          <div className="stat-sub">{percent(within10 / days.length, 0)} ของวันที่ร้านเปิด</div>
        </div>
        <div>
          <div className="stat-label">วันที่ทายพลาดมากที่สุด</div>
          <div className="accuracy-value">{thaiDate(worst.date)}</div>
          <div className="stat-sub num">
            จริง {money(worst.actual!)} · ทาย {money(worst.forecast)} ({worstErr >= 0 ? "+" : ""}{(worstErr * 100).toFixed(0)}%)
          </div>
        </div>
      </div>
    </div>
  );
}
