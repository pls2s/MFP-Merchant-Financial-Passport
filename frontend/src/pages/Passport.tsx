import { lazy, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { BalanceChart } from "../components/BalanceChart";
import {
  BALANCE_LAYERS, RANGES, SALES_LAYERS, type BalanceLayer, type RangeKey, type SalesLayer,
} from "../components/chartOptions";
import { Copilot } from "../components/Copilot";
import { Offers } from "../components/Offers";
import { SalesChart } from "../components/SalesChart";
import { OddsPill, ShortfallOdds } from "../components/ShortfallOdds";
import type { SkylineDay } from "../components/three/CashSkyline3D";
import { Scene3D } from "../components/three/Scene3D";
import {
  Card, ChipGroup, ErrorState, ExperimentalBadge, Segmented, Skeleton, SyntheticBadge, ViewToggle, type ViewMode,
} from "../components/ui";
import { addDays, money, oddsOn, oddsText, thaiDate, thaiDateShort, thaiDatesInText, thaiWeekday } from "../format";
import type {
  CashBalance, CashFlowGaps, CreditSignal, Forecast, Gap, LongForecast, LongGap, ModelResult, SalesHistory, SeasonalOutlook,
  ShortfallRisk,
} from "../types";
import { useAsync } from "../useAsync";

const CashSkyline3D = lazy(() => import("../components/three/CashSkyline3D"));

const COMPONENTS: { key: keyof CreditSignal["components"]; label: string; weight: number }[] = [
  { key: "consistency", label: "ความสม่ำเสมอ", weight: 30 },
  { key: "trend", label: "แนวโน้มยอดขาย", weight: 20 },
  { key: "active_days", label: "วันที่มียอดขาย", weight: 20 },
  { key: "cash_buffer", label: "เงินสำรอง", weight: 20 },
  { key: "gap_frequency", label: "ความถี่เงินขาด", weight: 10 },
];

const SECTIONS = [
  { id: "overview", label: "ภาพรวม" },
  { id: "sales", label: "ยอดขาย" },
  { id: "balance", label: "ยอดเงิน" },
  { id: "alerts", label: "การแจ้งเตือน" },
  { id: "signal", label: "สัญญาณการเงิน" },
  { id: "copilot", label: "ผู้ช่วย" },
];

interface PassportData {
  asOf: string;
  forecast: Forecast;
  history: SalesHistory;
  balance: CashBalance;
  gaps: CashFlowGaps;
  credit: CreditSignal;
  results: ModelResult[];
  longForecast: LongForecast;
  seasonal: SeasonalOutlook;
  risk: ShortfallRisk;
}

async function loadPassport(id: number): Promise<PassportData> {
  const [asOf, forecast, history, balance, gaps, credit, results, longForecast, seasonal, risk] = await Promise.all([
    api.asOf(), api.forecast(id), api.salesHistory(id), api.cashBalance(id),
    api.cashFlowGaps(id), api.creditSignal(id), api.modelResults(), api.longForecast(id), api.seasonalOutlook(id),
    api.shortfallRisk(id),
  ]);
  return { asOf, forecast, history, balance, gaps, credit, results, longForecast, seasonal, risk };
}

// --- Summary ---------------------------------------------------------------------------

function ScoreRing({ score }: { score: number }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  return (
    <svg className="score-ring" viewBox="0 0 84 84" role="img" aria-label={`สัญญาณการเงิน ${score} จาก 100`}>
      <circle cx="42" cy="42" r={r} className="ring-track" />
      <circle cx="42" cy="42" r={r} className="ring-fill" strokeDasharray={`${(score / 100) * c} ${c}`} transform="rotate(-90 42 42)" />
      <text x="42" y="47" textAnchor="middle" className="ring-text">{score}</text>
    </svg>
  );
}

function SummaryCards({ asOf, forecast, gaps, credit, balance, risk }: PassportData) {
  const recent = forecast.points.filter((p) => p.date <= asOf);
  const recentSales = recent.reduce((sum, p) => sum + (p.actual ?? 0), 0);
  const nextSales = forecast.points.filter((p) => p.date > asOf).reduce((s, p) => s + p.forecast, 0);
  const next = gaps.gaps[0];
  return (
    <div className="summary-grid">
      <section className="stat-card">
        <div className="stat-label">ยอดขาย {recent.length} วันล่าสุด</div>
        <div className="stat-value">{money(recentSales)}</div>
        <div className="stat-sub">{thaiDate(recent[0].date)} – {thaiDate(asOf)}</div>
        <div className="stat-sub">คาดว่า 14 วันข้างหน้า <b className="num">{money(nextSales)}</b></div>
      </section>
      <section className="stat-card with-ring">
        <div>
          <div className="stat-label">สัญญาณการเงิน <ExperimentalBadge /></div>
          <div className="stat-value">{credit.score}<small>/100</small></div>
          <div className="stat-sub">จากพฤติกรรมยอดขายและเงินสดที่คาดการณ์</div>
        </div>
        <ScoreRing score={credit.score} />
      </section>
      <section className={`stat-card ${next ? "tone-bad" : "tone-good"}`}>
        <div className="stat-label">เงินอาจไม่พอครั้งถัดไป <SyntheticBadge /></div>
        {next ? (
          <>
            <div className="stat-value bad-text">⚠ {thaiDate(next.date)}</div>
            <div className="stat-sub">ขาดประมาณ <strong className="num">{money(next.shortfall)}</strong> · <OddsPill p={oddsOn(risk, next.date)} /></div>
          </>
        ) : (
          <>
            <div className="stat-value good-text">✓ ไม่พบ</div>
            <div className="stat-sub">ใน 14 วันข้างหน้า</div>
          </>
        )}
        <div className="stat-sub">โอกาสเงินไม่พอใน 14 วัน <b className="num">{oddsText(risk.p_any)}</b></div>
        {balance.past_gaps.length > 0 && (
          <div className="stat-sub warn-text">ที่ผ่านมาเคยเงินไม่พอ {balance.past_gaps.length} ครั้ง</div>
        )}
      </section>
    </div>
  );
}

// --- 3D skyline + day detail -------------------------------------------------------------

function skylineDays(balance: CashBalance, gaps: Gap[], asOf: string): SkylineDay[] {
  const end = addDays(asOf, 14);
  const gapDates = new Set(gaps.map((g) => g.date));
  return balance.points
    .filter((p) => p.date > asOf && p.date <= end)
    .map((p) => ({ date: p.date, sales: p.sales, expenses: p.expenses, balance: p.balance, gap: gapDates.has(p.date) }));
}

function Skyline({ data }: { data: PassportData }) {
  const days = useMemo(() => skylineDays(data.balance, data.gaps.gaps, data.asOf), [data]);
  const firstGap = days.findIndex((d) => d.gap);
  const [selected, setSelected] = useState<number | null>(firstGap >= 0 ? firstGap : null);
  const day = selected != null ? days[selected] : null;
  const gap = day ? data.gaps.gaps.find((g) => g.date === day.date) : undefined;

  return (
    <Card id="overview" className="skyline-card" eyebrow="14 วันข้างหน้า · มุมมอง 3 มิติ" title="เงินเข้า–เงินออก รายวัน" badges={<SyntheticBadge />}>
      <div className="skyline">
        <div className="skyline-scene">
          <Scene3D height={340} fallback={<div className="scene3d-fallback">เปิดภาพ 3 มิติไม่ได้ในเบราว์เซอร์นี้ เลือกวันจากแถบด้านล่างแทนได้</div>}>
            <CashSkyline3D days={days} selected={selected} onSelect={setSelected} />
          </Scene3D>
          <div className="scene-caption">
            <span><i className="swatch bar" style={{ "--c": "var(--series-forecast)" } as React.CSSProperties} />ยอดขายคาดการณ์</span>
            <span><i className="swatch bar" style={{ "--c": "var(--series-expense)" } as React.CSSProperties} />รายจ่ายจำลอง</span>
            <span><i className="swatch ring" />⚠ วันที่เงินอาจไม่พอ</span>
            <span className="muted">ลาก = หมุน · คลิกแท่ง = ดูตัวเลข</span>
          </div>
          <div className="day-strip" role="listbox" aria-label="เลือกวัน">
            {days.map((d, i) => (
              <button key={d.date} role="option" aria-selected={selected === i}
                className={`day${selected === i ? " on" : ""}${d.gap ? " gap" : ""}`} onClick={() => setSelected(selected === i ? null : i)}>
                <small>{thaiWeekday(d.date).replace("วัน", "").slice(0, 2)}</small>
                <b>{Number(d.date.slice(8))}</b>
              </button>
            ))}
          </div>
        </div>
        <div className="day-panel" aria-live="polite">
          {day ? (
            <>
              <div className="eyebrow">{thaiWeekday(day.date)}</div>
              <h3>{thaiDate(day.date)}</h3>
              <dl className="ledger">
                <div><dt>ยอดขายคาดการณ์</dt><dd className="num good-text">+{money(day.sales)}</dd></div>
                <div><dt>รายจ่ายที่ครบกำหนด <span className="badge synthetic">จำลอง</span></dt><dd className="num">−{money(day.expenses)}</dd></div>
                <div className="total"><dt>ยอดเงินคงเหลือสิ้นวัน</dt>
                  <dd className={`num ${day.balance < 0 ? "bad-text" : ""}`}>{money(day.balance)}</dd></div>
              </dl>
              <p className="small" style={{ margin: "0 0 8px" }}>
                โอกาสเงินไม่พอวันนี้ <OddsPill p={oddsOn(data.risk, day.date)} />
              </p>
              {gap ? (
                <div className="alert bad compact">
                  <div className="alert-title">⚠ เงินสดอาจไม่พอ ขาดประมาณ {money(gap.shortfall)}</div>
                  <ul className="contributors">
                    {gap.contributors.map((c, i) => (
                      <li key={`${c.due_date}-${c.type}-${i}`}><span>{c.label}</span><span className="num">{money(c.amount)}</span></li>
                    ))}
                  </ul>
                </div>
              ) : day.balance < 0 ? (
                <p className="bad-text small">ยอดเงินยังติดลบต่อเนื่องจากวันที่เงินเริ่มไม่พอ</p>
              ) : (
                <p className="good-text small">✓ เงินสดพอในวันนี้</p>
              )}
            </>
          ) : (
            <div className="day-empty">
              <div className="eyebrow">รายละเอียดรายวัน</div>
              <p>คลิกแท่งในภาพ 3 มิติ หรือเลือกวันจากแถบด้านล่าง เพื่อดูเงินเข้า เงินออก และยอดเงินคงเหลือของวันนั้น</p>
              <p className="muted small">
                ต่ำสุดในช่วงนี้ <b className="num">{money(Math.min(...days.map((d) => d.balance)))}</b> ·
                {" "}{thaiDateShort(days[0].date)} – {thaiDateShort(days[days.length - 1].date)}
              </p>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

// --- Alerts ------------------------------------------------------------------------------

type AlertTab = "next" | "past" | "later";

function GapAlerts({ gaps, pastGaps, longGaps, risk }: { gaps: CashFlowGaps; pastGaps: Gap[]; longGaps: LongGap[]; risk: ShortfallRisk }) {
  const [tab, setTab] = useState<AlertTab>("next");
  return (
    <Card id="alerts" eyebrow="เงินสด" title="การแจ้งเตือนเงินสด" badges={<SyntheticBadge />}
      action={
        <Segmented label="ช่วงของการแจ้งเตือน" value={tab} onChange={setTab} options={[
          { key: "next", label: <>14 วันข้างหน้า <span className="count">{gaps.gaps.length}</span></> },
          { key: "past", label: <>ที่ผ่านมา <span className="count">{pastGaps.length}</span></> },
          { key: "later", label: <>หลัง 14 วัน <span className="count">{longGaps.length}</span></> },
        ]} />
      }>
      {tab === "next" && <ShortfallOdds risk={risk} />}
      {tab === "next" && (gaps.gaps.length === 0 ? (
        <div className="alert good">✓ ไม่พบช่วงที่เงินสดอาจไม่พอใน 14 วันข้างหน้า</div>
      ) : (
        <div className="alert-grid">
          {gaps.gaps.map((g) => (
            <div key={g.date} className="alert bad">
              <div className="alert-title">
                ⚠ วันที่ {thaiDate(g.date)} เงินสดอาจไม่พอ ขาดประมาณ {money(g.shortfall)}
                <OddsPill p={oddsOn(risk, g.date)} />
              </div>
              <div className="muted small">รายจ่ายที่เป็นสาเหตุ (เรียงจากมากไปน้อย)</div>
              <ul className="contributors">
                {g.contributors.map((c, i) => {
                  const share = c.amount / g.contributors.reduce((s, x) => s + x.amount, 0);
                  return (
                    <li key={`${c.due_date}-${c.type}-${i}`}>
                      <span>
                        {c.label} <span className="due">ครบกำหนด {thaiDate(c.due_date)}</span>
                        <span className="share"><span style={{ width: `${share * 100}%` }} /></span>
                      </span>
                      <span className="num">{money(c.amount)}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      ))}
      {tab === "past" && (pastGaps.length === 0 ? (
        <div className="alert good">✓ ตั้งแต่ 1 ม.ค. 2558 เงินสดไม่เคยไม่พอ</div>
      ) : (
        <>
          <p className="muted small" style={{ marginTop: 0 }}>ที่ผ่านมาเงินสดเคยไม่พอ {pastGaps.length} ครั้ง (ตั้งแต่ 1 ม.ค. 2558) · ล่าสุดก่อน</p>
          <ul className="past-gaps">
            {[...pastGaps].reverse().map((g) => (
              <li key={g.date}>
                <span>
                  {thaiDate(g.date)}
                  {g.contributors[0] && <span className="due"> · {g.contributors[0].label} {money(g.contributors[0].amount)}</span>}
                </span>
                <span className="num">ขาด {money(g.shortfall)}</span>
              </li>
            ))}
          </ul>
        </>
      ))}
      {tab === "later" && (longGaps.length === 0 ? (
        <div className="alert good">✓ ไม่พบวันที่เงินอาจไม่พอหลัง 14 วันข้างหน้า</div>
      ) : (
        <>
          <p className="muted small" style={{ marginTop: 0 }}>
            สถานการณ์คร่าว ๆ จากยอดขายที่ทายต่อเนื่อง 3 เดือน แล้วต่อด้วยภาพรวมรายเดือน กับรายจ่ายจำลองรอบเดิม — ไม่ใช่คำเตือนแน่นอน
          </p>
          <ul className="past-gaps later">
            {longGaps.map((g) => (
              <li key={g.date}>
                <span>
                  {thaiDate(g.date)} <span className="badge">{g.horizon === "3m" ? "คาดการณ์ 3 เดือน" : "ภาพรวมรายเดือน"}</span>
                  {g.contributors[0] && <span className="due"> · {g.contributors[0].label} {money(g.contributors[0].amount)}</span>}
                </span>
                <span className="num">อาจขาด {money(g.shortfall)}</span>
              </li>
            ))}
          </ul>
        </>
      ))}
      <p className="disclaimer">
        รายจ่ายและยอดเงินคงเหลือเป็นข้อมูลจำลอง · ยอดเงินตั้งต้น {money(gaps.opening_balance)} (1 ม.ค. 2558)
      </p>
    </Card>
  );
}

// --- Credit signal -----------------------------------------------------------------------

function Factors({ credit }: { credit: CreditSignal }) {
  return (
    <Card id="signal" eyebrow="สัญญาณทดลอง (experimental)" title="สัญญาณการเงิน" badges={<ExperimentalBadge />}>
      <div className="signal-layout">
        <div className="signal-score">
          <ScoreRing score={credit.score} />
          <div className="muted small">คะแนนรวมจาก 5 องค์ประกอบ</div>
        </div>
        <div className="signal-meters">
          {COMPONENTS.map((c) => (
            <div key={c.key} className="meter">
              <span>{c.label} <span className="muted small">น้ำหนัก {c.weight}%</span></span>
              <div className="meter-track"><div className="meter-fill" style={{ width: `${credit.components[c.key] * 100}%` }} /></div>
              <span className="num small">{credit.components[c.key].toFixed(2)}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="grid-2 factors">
        <div className="factor-box pos">
          <h3>✓ จุดแข็ง</h3>
          {credit.positive_factors.length ? (
            <ul className="factor-list pos">{credit.positive_factors.map((f) => <li key={f}>{f}</li>)}</ul>
          ) : <p className="muted">—</p>}
        </div>
        <div className="factor-box neg">
          <h3>! จุดที่ควรระวัง</h3>
          {credit.risk_indicators.length ? (
            <ul className="factor-list neg">{credit.risk_indicators.map((f) => <li key={f}>{thaiDatesInText(f)}</li>)}</ul>
          ) : <p className="muted">—</p>}
        </div>
      </div>
      <p className="disclaimer">
        สัญญาณทดลองแบบโปร่งใสจาก 5 องค์ประกอบ ไม่ใช่คะแนนเครดิต และไม่ได้ใช้ตัดสินสินเชื่อ ·
        ข้อมูล {thaiDate(credit.data_coverage.start)} – {thaiDate(credit.data_coverage.end)}
      </p>
    </Card>
  );
}

// --- Page --------------------------------------------------------------------------------

export function Passport() {
  const id = Number(useParams().id);
  const [state, retry] = useAsync(() => loadPassport(id), [id]);
  const [range, setRange] = useState<RangeKey>("3m");
  const [view, setView] = useState<ViewMode>("chart");
  const [salesLayers, setSalesLayers] = useState<Set<SalesLayer>>(new Set());
  const [balanceLayers, setBalanceLayers] = useState<Set<BalanceLayer>>(new Set(["expenses", "pastGaps", "longGaps"]));

  return (
    <>
      <div className="page-head">
        <Link to="/" className="back">← เลือกร้านอื่น</Link>
        <div className="title-row">
          <span className="avatar lg">{id}</span>
          <div>
            <div className="eyebrow">Financial Passport</div>
            <h1>ร้านตัวอย่าง #{id}</h1>
          </div>
          {state.status === "ok" && <span className="asof">ข้อมูลถึงวันที่ <b>{thaiDate(state.data.asOf)}</b></span>}
        </div>
      </div>

      {state.status === "loading" && (
        <>
          <div className="summary-grid"><Skeleton height={130} /><Skeleton height={130} /><Skeleton height={130} /></div>
          <Skeleton height={380} />
        </>
      )}
      {state.status === "error" && <Card><ErrorState error={state.error} onRetry={retry} /></Card>}
      {state.status === "ok" && (
        <>
          <nav className="section-nav" aria-label="ส่วนของหน้า">
            {SECTIONS.map((s) => <a key={s.id} href={`#${s.id}`}>{s.label}</a>)}
          </nav>

          <SummaryCards {...state.data} />
          <Skyline data={state.data} />

          <div className="filter-bar sticky" role="toolbar" aria-label="ตัวกรองกราฟ">
            <span className="filter-label">ช่วงเวลา</span>
            <Segmented label="ช่วงเวลา" options={RANGES} value={range} onChange={setRange} />
            <span className="filter-label">แสดงเป็น</span>
            <ViewToggle value={view} onChange={setView} />
            <span className="muted small filter-hint">ใช้กับกราฟยอดขายและยอดเงินด้านล่าง</span>
          </div>

          <Card id="sales" eyebrow="พยากรณ์ด้วย deep learning" title="ยอดขายจริงและยอดขายที่คาดการณ์"
            badges={<span className="badge accent">LSTM+GRU</span>}>
            {range !== "1y" && (
              <ChipGroup label="ชั้นข้อมูลบนกราฟยอดขาย" options={SALES_LAYERS} value={salesLayers} onChange={setSalesLayers} />
            )}
            <SalesChart range={range} layers={salesLayers} view={view}
              forecast={state.data.forecast} history={state.data.history}
              longForecast={state.data.longForecast} seasonal={state.data.seasonal} results={state.data.results}
              asOf={state.data.asOf} gaps={state.data.gaps.gaps} pastGaps={state.data.balance.past_gaps} />
          </Card>

          <Card id="balance" eyebrow="เงินสด" title="ยอดเงินคงเหลือที่คาดการณ์" badges={<SyntheticBadge />}>
            {view === "chart" && (
              <ChipGroup label="ชั้นข้อมูลบนกราฟยอดเงิน" options={BALANCE_LAYERS} value={balanceLayers} onChange={setBalanceLayers} />
            )}
            <BalanceChart balance={state.data.balance} asOf={state.data.asOf} gaps={state.data.gaps.gaps}
              range={range} layers={balanceLayers} view={view} />
          </Card>

          <GapAlerts gaps={state.data.gaps} pastGaps={state.data.balance.past_gaps} longGaps={state.data.balance.long_gaps}
            risk={state.data.risk} />
          <Factors credit={state.data.credit} />
          <div id="copilot"><Copilot merchantId={id} /></div>
          <Offers gaps={state.data.gaps.gaps} />
        </>
      )}
    </>
  );
}
