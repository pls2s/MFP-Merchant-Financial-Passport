import { lazy, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api, MockMissingError, NotFoundError } from "../api";
import { BalanceChart } from "../components/BalanceChart";
import {
  BALANCE_LAYERS, RANGES, SALES_LAYERS, type BalanceLayer, type RangeKey, type SalesLayer,
} from "../components/chartOptions";
import { Copilot } from "../components/Copilot";
import { Offers } from "../components/Offers";
import { SalesChart } from "../components/SalesChart";
import type { SkylineDay } from "../components/three/CashSkyline3D";
import { Scene3D } from "../components/three/Scene3D";
import {
  Card, ChipGroup, Disclosure, ErrorState, ExperimentalBadge, Icon, InfoDialog, Segmented, Skeleton, Swatch, SyntheticBadge, ViewToggle, type ViewMode,
} from "../components/ui";
import { addDays, change, daysBetween, money, thaiDate, thaiDateShort, thaiDatesInText, thaiWeekday } from "../format";
import type {
  CashBalance, CashFlowGaps, CreditSignal, Forecast, Gap, LongGap, SalesHistory,
} from "../types";
import { useAsync, type AsyncState } from "../useAsync";

const CashSkyline3D = lazy(() => import("../components/three/CashSkyline3D"));

const COMPONENTS: { key: keyof CreditSignal["components"]; label: string; weight: number }[] = [
  { key: "consistency", label: "ความสม่ำเสมอ", weight: 30 },
  { key: "trend", label: "แนวโน้มยอดขาย", weight: 20 },
  { key: "active_days", label: "วันที่มียอดขาย", weight: 20 },
  { key: "cash_buffer", label: "เงินสำรอง", weight: 20 },
  { key: "gap_frequency", label: "ความถี่เงินขาด", weight: 10 },
];

const SECTIONS = [
  { id: "sales", label: "ยอดขาย" },
  { id: "alerts", label: "เตือนเงินสด" },
  { id: "balance", label: "เงินคงเหลือ" },
  { id: "signal", label: "ปัจจัย" },
];

const ALL_SALES_LAYERS = SALES_LAYERS.map((l) => l.key);

// Each endpoint is loaded separately, so one failing only takes down the sections that need it.
type Query<T> = [AsyncState<T>, () => void];

/** Several queries as one: loading until all are ready, and retry re-runs the failed ones. */
function join<T extends unknown[]>(...queries: { [K in keyof T]: Query<T[K]> }): Query<T> {
  const list = queries as Query<unknown>[];
  const failed = list.filter(([state]) => state.status === "error");
  const retry = () => failed.forEach(([, again]) => again());
  const first = failed[0]?.[0];
  if (first?.status === "error") return [first, retry];
  if (list.some(([state]) => state.status === "loading")) return [{ status: "loading" }, retry];
  return [{ status: "ok", data: list.map(([state]) => (state as { data: unknown }).data) as T }, retry];
}

function Slot<T>({ of: [state, retry], title, height = 240, children }: {
  of: Query<T>;
  title: string;
  height?: number;
  children: (data: T) => ReactNode;
}) {
  if (state.status === "loading") return <Skeleton height={height} />;
  if (state.status === "error") return <Card title={title}><ErrorState error={state.error} onRetry={retry} /></Card>;
  return <>{children(state.data)}</>;
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

/** The one-sentence answer at the top of the page. */
function StatusBanner({ asOf, gaps }: { asOf: string; gaps: CashFlowGaps }) {
  const next = gaps.gaps[0];
  if (!next) {
    return (
      <section className="status-banner good">
        <Icon name="check_circle" size={24} />
        <div className="status-text"><b>ไม่พบช่วงที่เงินสดอาจไม่พอใน 14 วันข้างหน้า</b><span className="small"><SyntheticBadge /></span></div>
      </section>
    );
  }
  const cause = next.contributors[0];
  return (
    <section className="status-banner bad" role="status">
      <Icon name="warning" size={24} filled />
      <div className="status-text">
        <b>อีก {daysBetween(asOf, next.date)} วัน ({thaiDate(next.date)}) เงินสดอาจไม่พอ ขาดประมาณ <span className="num">{money(next.shortfall)}</span></b>
        <span className="small">{cause && <>สาเหตุหลัก: {cause.label}</>} <SyntheticBadge /></span>
      </div>
      <a className="btn" href="#alerts">ดูรายละเอียด</a>
    </section>
  );
}

function SalesCard({ asOf, forecast, history }: { asOf: string; forecast: Forecast; history: SalesHistory }) {
  const recent = forecast.points.filter((p) => p.date <= asOf);
  const recentSales = recent.reduce((sum, p) => sum + (p.actual ?? 0), 0);
  const before = addDays(recent[0].date, -recent.length);
  const previous = history.points.filter((h) => h.date >= before && h.date < recent[0].date).reduce((sum, h) => sum + (h.sales ?? 0), 0);
  return (
    <section className="stat-card">
      <div className="stat-label">ยอดขาย {recent.length} วันล่าสุด</div>
      <div className="stat-value num">{money(recentSales)}</div>
      <div className="stat-sub">
        {previous > 0
          ? <>{recentSales >= previous ? "▲" : "▼"} {change(recentSales / previous - 1)} จากช่วงก่อน</>
          : <>{thaiDate(recent[0].date)} – {thaiDate(asOf)}</>}
      </div>
    </section>
  );
}

function SignalCard({ credit }: { credit: CreditSignal }) {
  return (
    <section className="stat-card">
      <div className="stat-label">สัญญาณการเงิน <ExperimentalBadge /></div>
      <div className="stat-value num">{credit.score}<small>/100</small></div>
      <div className="stat-sub">จากพฤติกรรมยอดขายและเงินสดที่คาดการณ์</div>
    </section>
  );
}

function NextGapCard({ gaps, pastCount }: { gaps: CashFlowGaps; pastCount: number }) {
  const next = gaps.gaps[0];
  return (
    <section className="stat-card">
      <div className="stat-label">เงินอาจไม่พอครั้งถัดไป <SyntheticBadge /></div>
      {next ? (
        <>
          <div className="stat-value small-value bad-text"><Icon name="warning" size={24} filled />{thaiDate(next.date)}</div>
          <div className="stat-sub">ขาดประมาณ <strong className="num">{money(next.shortfall)}</strong></div>
        </>
      ) : (
        <>
          <div className="stat-value small-value good-text"><Icon name="check_circle" size={24} filled />ไม่พบ</div>
          <div className="stat-sub">ใน 14 วันข้างหน้า</div>
        </>
      )}
      {pastCount > 0 && <div className="stat-sub">ที่ผ่านมาเคยเงินไม่พอ {pastCount} ครั้ง</div>}
    </section>
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

function Skyline({ data }: { data: { balance: CashBalance; gaps: CashFlowGaps; asOf: string } }) {
  const days = useMemo(() => skylineDays(data.balance, data.gaps.gaps, data.asOf), [data]);
  const firstGap = days.findIndex((d) => d.gap);
  const [selected, setSelected] = useState<number | null>(firstGap >= 0 ? firstGap : null);
  const day = selected != null ? days[selected] : null;
  const gap = day ? data.gaps.gaps.find((g) => g.date === day.date) : undefined;

  return (
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
              {gap ? (
                <div className="alert bad compact">
                  <div className="alert-title"><Icon name="warning" filled />{thaiDate(gap.date)} เงินสดอาจไม่พอ ขาดประมาณ {money(gap.shortfall)}</div>
                  <ul className="contributors">
                    {gap.contributors.map((c, i) => (
                      <li key={`${c.due_date}-${c.type}-${i}`}><span>{c.label}</span><span className="num">{money(c.amount)}</span></li>
                    ))}
                  </ul>
                </div>
              ) : day.balance < 0 ? (
                <p className="bad-text small">ยอดเงินยังติดลบต่อเนื่องจากวันที่เงินเริ่มไม่พอ</p>
              ) : (
                <p className="good-text small">เงินสดพอในวันนี้</p>
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
  );
}

// --- Alerts ------------------------------------------------------------------------------

type AlertTab = "next" | "past" | "later";

/** The history tabs need cash-balance; without it (null) only the 14-day warnings are shown. */
function GapAlerts({ gaps, pastGaps, longGaps }: { gaps: CashFlowGaps; pastGaps: Gap[] | null; longGaps: LongGap[] | null }) {
  const [tab, setTab] = useState<AlertTab>("next");
  return (
    <Card title="การแจ้งเตือนเงินสด" badges={<SyntheticBadge />}
      action={
        pastGaps && longGaps && (
          <Segmented label="ช่วงของการแจ้งเตือน" value={tab} onChange={setTab} options={[
            { key: "next", label: <>14 วันข้างหน้า <span className="count">{gaps.gaps.length}</span></> },
            { key: "past", label: <>ที่ผ่านมา <span className="count">{pastGaps.length}</span></> },
            { key: "later", label: <>หลัง 14 วัน <span className="count">{longGaps.length}</span></> },
          ]} />
        )
      }>
      {tab === "next" && (gaps.gaps.length === 0 ? (
        <div className="alert good"><Icon name="check_circle" />ไม่พบช่วงที่เงินสดอาจไม่พอใน 14 วันข้างหน้า</div>
      ) : (
        <div className="alert-grid">
          {gaps.gaps.map((g) => (
            <div key={g.date} className="alert bad">
              <div className="alert-title">
                <Icon name="warning" filled /><span>วันที่ {thaiDate(g.date)} เงินสดอาจไม่พอ ขาดประมาณ {money(g.shortfall)}</span>
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
      {tab === "past" && pastGaps && (pastGaps.length === 0 ? (
        <div className="alert good"><Icon name="check_circle" />ตั้งแต่ 1 ม.ค. 2558 เงินสดไม่เคยไม่พอ</div>
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
      {tab === "later" && longGaps && (longGaps.length === 0 ? (
        <div className="alert good"><Icon name="check_circle" />ไม่พบวันที่เงินอาจไม่พอหลัง 14 วันข้างหน้า</div>
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
    <Card eyebrow="สัญญาณทดลอง (experimental)" title="สัญญาณการเงิน" badges={<ExperimentalBadge />}>
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
          <h3>ปัจจัยบวก</h3>
          {credit.positive_factors.length ? (
            <ul className="factor-list pos">{credit.positive_factors.map((f) => <li key={f}><Icon name="check_circle" />{f}</li>)}</ul>
          ) : <p className="muted">—</p>}
        </div>
        <div className="factor-box neg">
          <h3>ความเสี่ยง</h3>
          {credit.risk_indicators.length ? (
            <ul className="factor-list neg">{credit.risk_indicators.map((f) => <li key={f}><Icon name="warning" />{thaiDatesInText(f)}</li>)}</ul>
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

/** Marks the tab of the section under the sticky bars; at the end of the page, the last one (it may never get that high). */
function useActiveSection(ready: boolean) {
  const [active, setActive] = useState(SECTIONS[0].id);
  useEffect(() => {
    if (!ready) return;
    const update = () => {
      const last = SECTIONS[SECTIONS.length - 1].id;
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) return setActive(last);
      const passed = SECTIONS.filter((s) => (document.getElementById(s.id)?.getBoundingClientRect().top ?? Infinity) <= window.innerHeight * 0.3);
      setActive(passed.length ? passed[passed.length - 1].id : SECTIONS[0].id);
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, [ready]);
  return active;
}

function ReadGuide() {
  return (
    <InfoDialog label="วิธีอ่านกราฟยอดขาย" title="วิธีอ่านกราฟ">
      <ul className="read-guide">
        <li><Swatch kind="line" color="var(--series-actual)" />เส้นทึบ คือยอดขายจริงจนถึงวันนี้</li>
        <li><Swatch kind="line" color="var(--series-forecast)" dashed />เส้นประ คือยอดขายที่ระบบคาดการณ์</li>
        <li><Swatch kind="area" color="var(--series-band)" />แถบจาง คือช่วงคาดการณ์โดยประมาณ ยอดจริงมักอยู่ในช่วงนี้ แต่ไม่เสมอไป</li>
        <li><Swatch kind="line" color="var(--bad)" dashed />เส้นสีแดง คือวันที่เงินสดอาจไม่พอ</li>
      </ul>
      <p className="muted">เส้นที่ขาดเป็นช่วง ๆ คือวันที่ร้านปิด</p>
    </InfoDialog>
  );
}

/** Keyed by store: searching from the app bar starts a fresh page (filters, chat) for the new store. */
export function Passport() {
  const id = Number(useParams().id);
  return <PassportPage key={id} id={id} />;
}

function PassportPage({ id }: { id: number }) {
  const asOf = useAsync(api.asOf, []);
  const forecast = useAsync(() => api.forecast(id), [id]);
  const history = useAsync(() => api.salesHistory(id), [id]);
  const balance = useAsync(() => api.cashBalance(id), [id]);
  const gaps = useAsync(() => api.cashFlowGaps(id), [id]);
  const credit = useAsync(() => api.creditSignal(id), [id]);
  const longForecast = useAsync(() => api.longForecast(id), [id]);
  const seasonal = useAsync(() => api.seasonalOutlook(id), [id]);
  const [results] = useAsync(api.modelResults, []);
  const [merchants] = useAsync(api.merchants, []);
  const [range, setRange] = useState<RangeKey>("3m");
  const [view, setView] = useState<ViewMode>("chart");
  const [salesLayers, setSalesLayers] = useState<Set<SalesLayer>>(new Set());
  const [salesDetails, setSalesDetails] = useState(false);
  const [balanceLayers, setBalanceLayers] = useState<Set<BalanceLayer>>(new Set(["expenses", "pastGaps", "longGaps"]));
  const [show3D, setShow3D] = useState(false);
  const isDemo = merchants.status === "ok" && merchants.data.some((m) => m.merchant_id === id && m.is_demo);

  // An unknown store (or one with no mock data) is a page-level state, not one error per section.
  const missing = [forecast, history, balance, gaps, credit, longForecast, seasonal]
    .map(([state]) => (state.status === "error" ? state.error : null))
    .find((e) => e instanceof NotFoundError || e instanceof MockMissingError);
  const activeSection = useActiveSection(!missing);

  const asOfDate = asOf[0].status === "ok" ? asOf[0].data : null;
  const gapList = gaps[0].status === "ok" ? gaps[0].data.gaps : [];
  const balanceData = balance[0].status === "ok" ? balance[0].data : null;
  const chartControls = (
    <span className="card-actions">
      <Segmented label="ช่วงเวลา" options={RANGES} value={range} onChange={setRange} />
      <ViewToggle value={view} onChange={setView} />
    </span>
  );

  return (
    <>
      <div className="page-head">
        <Link to="/" className="back"><Icon name="arrow_back" />ร้านค้า</Link>
        <div className="title-row">
          <h1>ร้านตัวอย่าง #{id}</h1>
          {isDemo && <span className="badge accent">ร้านสาธิต</span>}
          {asOfDate && <span className="asof">ข้อมูลถึง {thaiDate(asOfDate)}</span>}
        </div>
      </div>

      {missing ? <Card><ErrorState error={missing} /></Card> : (
        <>
          <Slot of={join(asOf, gaps)} title="สถานะเงินสด" height={88}>
            {([today, g]) => <StatusBanner asOf={today} gaps={g} />}
          </Slot>
          <div className="summary-grid">
            <Slot of={join(asOf, forecast, history)} title="ยอดขายล่าสุด" height={150}>
              {([today, f, h]) => <SalesCard asOf={today} forecast={f} history={h} />}
            </Slot>
            <Slot of={credit} title="สัญญาณการเงิน" height={150}>{(c) => <SignalCard credit={c} />}</Slot>
            <Slot of={gaps} title="เงินอาจไม่พอครั้งถัดไป" height={150}>
              {(g) => <NextGapCard gaps={g} pastCount={balanceData?.past_gaps.length ?? 0} />}
            </Slot>
          </div>

          <nav className="section-nav" aria-label="ส่วนของหน้า">
            {SECTIONS.map((s) => (
              <a key={s.id} href={`#${s.id}`} className={activeSection === s.id ? "active" : ""}
                aria-current={activeSection === s.id ? "location" : undefined}>{s.label}</a>
            ))}
          </nav>

          <div id="sales">
            <Slot of={join(asOf, forecast, history, longForecast, seasonal)} title="ยอดขายจริงและยอดขายที่คาดการณ์" height={380}>
              {([today, f, h, l, o]) => (
                <Card title="ยอดขายจริงและยอดขายที่คาดการณ์" action={<>{chartControls}<ReadGuide /></>}>
                  <SalesChart range={range} layers={salesLayers} view={view}
                    forecast={f} history={h} longForecast={l} seasonal={o}
                    results={results.status === "ok" ? results.data : []}
                    asOf={today} gaps={gapList} pastGaps={balanceData?.past_gaps ?? []}
                    details={range !== "1y" && (
                      <div className="chart-details">
                        <Disclosure open={salesDetails} onToggle={() => {
                          setSalesLayers(new Set(salesDetails ? [] : ALL_SALES_LAYERS));
                          setSalesDetails(!salesDetails);
                        }}>
                          {salesDetails ? "ซ่อนรายละเอียด" : "แสดงรายละเอียด"}
                        </Disclosure>
                        {salesDetails && (
                          <ChipGroup label="ชั้นข้อมูลบนกราฟยอดขาย" options={SALES_LAYERS} value={salesLayers} onChange={setSalesLayers} />
                        )}
                      </div>
                    )} />
                </Card>
              )}
            </Slot>
          </div>

          <div id="alerts">
            <Slot of={gaps} title="การแจ้งเตือนเงินสด">
              {(g) => <GapAlerts gaps={g} pastGaps={balanceData?.past_gaps ?? null} longGaps={balanceData?.long_gaps ?? null} />}
            </Slot>
          </div>

          <div id="balance">
            <Slot of={join(asOf, balance, gaps)} title="ยอดเงินคงเหลือที่คาดการณ์" height={380}>
              {([today, b, g]) => (
                <Card title="ยอดเงินคงเหลือที่คาดการณ์" badges={<SyntheticBadge />} action={chartControls}>
                  {view === "chart" && (
                    <ChipGroup label="ชั้นข้อมูลบนกราฟยอดเงิน" options={BALANCE_LAYERS} value={balanceLayers} onChange={setBalanceLayers} />
                  )}
                  <BalanceChart balance={b} asOf={today} gaps={g.gaps} range={range} layers={balanceLayers} view={view} />
                  <Disclosure open={show3D} onToggle={() => setShow3D((o) => !o)}>ดูเงินเข้า–เงินออก 14 วันข้างหน้า รายวัน (มุมมอง 3 มิติ)</Disclosure>
                  {show3D && <Skyline data={{ balance: b, gaps: g, asOf: today }} />}
                </Card>
              )}
            </Slot>
          </div>

          <div id="signal">
            <Slot of={credit} title="สัญญาณการเงิน">{(c) => <Factors credit={c} />}</Slot>
          </div>
          <Copilot merchantId={id} />
          <Offers gaps={gapList} />
        </>
      )}
    </>
  );
}
