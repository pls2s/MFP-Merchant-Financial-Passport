import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { BalanceChart } from "../components/BalanceChart";
import { Copilot } from "../components/Copilot";
import { ForecastAccuracy } from "../components/ForecastAccuracy";
import { Offers } from "../components/Offers";
import { SalesChart } from "../components/SalesChart";
import { Card, ErrorState, ExperimentalBadge, Skeleton, SyntheticBadge } from "../components/ui";
import { money, thaiDate, thaiDatesInText } from "../format";
import type { CashBalance, CashFlowGaps, CreditSignal, Forecast, ModelResult, SalesHistory } from "../types";
import { useAsync } from "../useAsync";

const COMPONENTS: { key: keyof CreditSignal["components"]; label: string; weight: number }[] = [
  { key: "consistency", label: "ความสม่ำเสมอ", weight: 30 },
  { key: "trend", label: "แนวโน้มยอดขาย", weight: 20 },
  { key: "active_days", label: "วันที่มียอดขาย", weight: 20 },
  { key: "cash_buffer", label: "เงินสำรอง", weight: 20 },
  { key: "gap_frequency", label: "ความถี่เงินขาด", weight: 10 },
];

interface PassportData {
  asOf: string;
  forecast: Forecast;
  history: SalesHistory;
  balance: CashBalance;
  gaps: CashFlowGaps;
  credit: CreditSignal;
  results: ModelResult[];
}

async function loadPassport(id: number): Promise<PassportData> {
  const [asOf, forecast, history, balance, gaps, credit, results] = await Promise.all([
    api.asOf(), api.forecast(id), api.salesHistory(id), api.cashBalance(id),
    api.cashFlowGaps(id), api.creditSignal(id), api.modelResults(),
  ]);
  return { asOf, forecast, history, balance, gaps, credit, results };
}

function SummaryCards({ asOf, forecast, gaps, credit }: PassportData) {
  const recent = forecast.points.filter((p) => p.date <= asOf);
  const recentSales = recent.reduce((sum, p) => sum + (p.actual ?? 0), 0);
  const next = gaps.gaps[0];
  return (
    <div className="grid-3">
      <section className="card">
        <div className="stat-label">ยอดขาย {recent.length} วันล่าสุด</div>
        <div className="stat-value num">{money(recentSales)}</div>
        <div className="stat-sub">{thaiDate(recent[0].date)} – {thaiDate(asOf)}</div>
      </section>
      <section className="card">
        <div className="stat-label">สัญญาณการเงิน <ExperimentalBadge /></div>
        <div className="stat-value num">{credit.score}<span className="muted" style={{ fontSize: "1rem" }}>/100</span></div>
        <div className="stat-sub">จากพฤติกรรมยอดขายและเงินสดที่คาดการณ์</div>
      </section>
      <section className="card">
        <div className="stat-label">เงินอาจไม่พอครั้งถัดไป <SyntheticBadge /></div>
        {next ? (
          <>
            <div className="stat-value bad">{thaiDate(next.date)}</div>
            <div className="stat-sub">ขาดประมาณ <strong className="num">{money(next.shortfall)}</strong></div>
          </>
        ) : (
          <>
            <div className="stat-value good">ไม่พบ</div>
            <div className="stat-sub">ใน 14 วันข้างหน้า</div>
          </>
        )}
      </section>
    </div>
  );
}

function GapAlerts({ gaps }: { gaps: CashFlowGaps }) {
  return (
    <Card title="การแจ้งเตือนเงินสด" badges={<SyntheticBadge />}>
      {gaps.gaps.length === 0 ? (
        <div className="alert good">ไม่พบช่วงที่เงินสดอาจไม่พอใน 14 วันข้างหน้า</div>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {gaps.gaps.map((g) => (
            <div key={g.date} className="alert bad">
              <div className="alert-title">
                วันที่ {thaiDate(g.date)} เงินสดอาจไม่พอ ขาดประมาณ {money(g.shortfall)}
              </div>
              <div className="muted small">รายจ่ายที่เป็นสาเหตุ (เรียงจากมากไปน้อย)</div>
              <ul className="contributors">
                {g.contributors.map((c, i) => (
                  <li key={`${c.due_date}-${c.type}-${i}`}>
                    <span>
                      {c.label} <span className="due">ครบกำหนด {thaiDate(c.due_date)}</span>
                    </span>
                    <span className="num">{money(c.amount)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      <p className="disclaimer">
        รายจ่ายและยอดเงินคงเหลือเป็นข้อมูลจำลอง · ยอดเงินตั้งต้น {money(gaps.opening_balance)}
      </p>
    </Card>
  );
}

function Factors({ credit }: { credit: CreditSignal }) {
  return (
    <Card title="สัญญาณการเงิน" badges={<ExperimentalBadge />}>
      <div className="grid-2">
        <div>
          <h3 style={{ marginBottom: 8 }}>จุดแข็ง</h3>
          {credit.positive_factors.length ? (
            <ul className="factor-list pos">{credit.positive_factors.map((f) => <li key={f}>{f}</li>)}</ul>
          ) : <p className="muted">—</p>}
        </div>
        <div>
          <h3 style={{ marginBottom: 8 }}>จุดที่ควรระวัง</h3>
          {credit.risk_indicators.length ? (
            <ul className="factor-list neg">{credit.risk_indicators.map((f) => <li key={f}>{thaiDatesInText(f)}</li>)}</ul>
          ) : <p className="muted">—</p>}
        </div>
      </div>
      <div style={{ marginTop: 18 }}>
        {COMPONENTS.map((c) => (
          <div key={c.key} className="meter">
            <span>{c.label} <span className="muted small">({c.weight}%)</span></span>
            <div className="meter-track"><div className="meter-fill" style={{ width: `${credit.components[c.key] * 100}%` }} /></div>
            <span className="num muted small">{credit.components[c.key].toFixed(2)}</span>
          </div>
        ))}
      </div>
      <p className="disclaimer">
        สัญญาณทดลองแบบโปร่งใสจาก 5 องค์ประกอบ ไม่ใช่คะแนนเครดิต และไม่ได้ใช้ตัดสินสินเชื่อ ·
        ข้อมูล {thaiDate(credit.data_coverage.start)} – {thaiDate(credit.data_coverage.end)}
      </p>
    </Card>
  );
}

export function Passport() {
  const id = Number(useParams().id);
  const [state, retry] = useAsync(() => loadPassport(id), [id]);

  return (
    <>
      <div className="page-head">
        <Link to="/" className="small">← เลือกร้านอื่น</Link>
      </div>
      <div className="page-head">
        <h1>ร้านตัวอย่าง #{id}</h1>
        {state.status === "ok" && <p>ข้อมูลถึงวันที่ {thaiDate(state.data.asOf)}</p>}
      </div>

      {state.status === "loading" && (
        <>
          <div className="grid-3"><Skeleton height={110} /><Skeleton height={110} /><Skeleton height={110} /></div>
          <Skeleton height={340} />
        </>
      )}
      {state.status === "error" && <Card><ErrorState error={state.error} onRetry={retry} /></Card>}
      {state.status === "ok" && (
        <>
          <SummaryCards {...state.data} />
          <Card title="ยอดขายจริงและยอดขายที่คาดการณ์" badges={<span className="badge">LSTM+GRU</span>}>
            <SalesChart forecast={state.data.forecast} history={state.data.history}
              asOf={state.data.asOf} gaps={state.data.gaps.gaps} />
            <ForecastAccuracy forecast={state.data.forecast} asOf={state.data.asOf} results={state.data.results} />
          </Card>
          <Card title="ยอดเงินคงเหลือที่คาดการณ์" badges={<SyntheticBadge />}>
            <BalanceChart balance={state.data.balance} asOf={state.data.asOf} />
          </Card>
          <GapAlerts gaps={state.data.gaps} />
          <Factors credit={state.data.credit} />
          <Copilot merchantId={id} />
          <Offers gaps={state.data.gaps.gaps} />
        </>
      )}
    </>
  );
}
