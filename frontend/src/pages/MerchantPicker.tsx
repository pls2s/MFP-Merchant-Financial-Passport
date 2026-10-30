import { lazy, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, isMock } from "../api";
import { Scene3D } from "../components/three/Scene3D";
import type { ScoreBin } from "../components/three/ScoreHistogram3D";
import { Card, Disclosure, ErrorState, Icon, Skeleton } from "../components/ui";
import { percent } from "../format";
import type { Merchant } from "../types";
import { useAsync } from "../useAsync";

const ScoreHistogram3D = lazy(() => import("../components/three/ScoreHistogram3D"));

const PAGE_SIZE = 50;

const SEGMENTS = [
  { key: "all", label: "ทั้งหมด" },
  { key: "risk", label: "มีความเสี่ยง" },
  { key: "clear", label: "ไม่มีความเสี่ยง" },
] as const;
type Segment = (typeof SEGMENTS)[number]["key"];

const SORTS = {
  default: { label: "ตามเลขร้าน", cmp: (a: Merchant, b: Merchant) => Number(b.is_demo) - Number(a.is_demo) || a.merchant_id - b.merchant_id },
  scoreDesc: { label: "สัญญาณการเงิน สูง → ต่ำ", cmp: (a: Merchant, b: Merchant) => b.score - a.score },
  scoreAsc: { label: "สัญญาณการเงิน ต่ำ → สูง", cmp: (a: Merchant, b: Merchant) => a.score - b.score },
  gaps: { label: "ครั้งที่เงินอาจไม่พอ มาก → น้อย", cmp: (a: Merchant, b: Merchant) => b.gap_count - a.gap_count || a.score - b.score },
  wape: { label: "พยากรณ์แม่นที่สุดก่อน", cmp: (a: Merchant, b: Merchant) => a.forecast_wape - b.forecast_wape },
} as const;
type SortKey = keyof typeof SORTS;

const binOf = (score: number) => Math.min(9, Math.floor(score / 10));

function scoreBins(all: Merchant[]): ScoreBin[] {
  const bins: ScoreBin[] = Array.from({ length: 10 }, (_, i) => ({ from: i * 10, to: i === 9 ? 100 : i * 10 + 9, total: 0, atRisk: 0 }));
  all.forEach((m) => {
    const b = bins[binOf(m.score)];
    b.total += 1;
    if (m.gap_count > 0) b.atRisk += 1;
  });
  return bins;
}

function Kpis({ all }: { all: Merchant[] }) {
  const risk = all.filter((m) => m.gap_count > 0).length;
  const avg = all.reduce((s, m) => s + m.score, 0) / Math.max(all.length, 1);
  return (
    <div className="kpis">
      <div className="kpi">
        <span className="kpi-label">ร้านค้าทั้งหมด</span>
        <span className="kpi-value">{all.length.toLocaleString("en-US")}</span>
        <span className="kpi-sub">ยอดขายรายวันจริงจาก Rossmann</span>
      </div>
      <div className="kpi">
        <span className="kpi-label">เงินอาจไม่พอใน 14 วัน <span className="badge synthetic">ข้อมูลจำลอง</span></span>
        <span className="kpi-value bad-text">{risk.toLocaleString("en-US")}</span>
        <span className="kpi-sub">{percent(risk / Math.max(all.length, 1), 1)} ของร้านทั้งหมด</span>
      </div>
      <div className="kpi">
        <span className="kpi-label">สัญญาณการเงินเฉลี่ย <span className="badge experimental">ทดลอง</span></span>
        <span className="kpi-value">{avg.toFixed(0)}<small>/100</small></span>
        <span className="kpi-sub">ไม่ใช่คะแนนเครดิต</span>
      </div>
    </div>
  );
}

function Status({ m }: { m: Merchant }) {
  return m.gap_count > 0
    ? <span className="m-status bad-text"><Icon name="warning" size={16} />เงินอาจไม่พอ {m.gap_count} ครั้ง</span>
    : <span className="m-status good-text"><Icon name="check_circle" size={16} />ไม่พบความเสี่ยงใน 14 วัน</span>;
}

const Score = ({ m }: { m: Merchant }) => (
  <span className="m-score"><span className="num">{m.score}/100</span> <span className="badge experimental">ทดลอง</span></span>
);

function Row({ m }: { m: Merchant }) {
  return (
    <li>
      <Link className="merchant-row" to={`/merchants/${m.merchant_id}`}>
        <span className="m-name">
          <b>{m.name} {m.is_demo && <span className="badge accent">ร้านสาธิต</span>}</b>
          <Status m={m} />
        </span>
        <Score m={m} />
        <span className="m-go"><Icon name="chevron_right" /></span>
      </Link>
    </li>
  );
}

function DemoCard({ m }: { m: Merchant }) {
  return (
    <Link className="demo-card" to={`/merchants/${m.merchant_id}`}>
      <span>{m.name} <span className="badge accent">ร้านสาธิต</span></span>
      <Status m={m} />
      <Score m={m} />
    </Link>
  );
}

export function MerchantPicker() {
  const [state, retry] = useAsync(api.merchants, []);
  const [query, setQuery] = useState("");
  const [segment, setSegment] = useState<Segment>("all");
  const [sort, setSort] = useState<SortKey>("default");
  const [bin, setBin] = useState<number | null>(null);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [moreOpen, setMoreOpen] = useState(false);
  const [overviewOpen, setOverviewOpen] = useState(false);
  const navigate = useNavigate();

  const all = useMemo(() => (state.status === "ok" ? state.data : []), [state]);
  const bins = useMemo(() => scoreBins(all), [all]);
  const demos = useMemo(() => all.filter((m) => m.is_demo), [all]);
  const filtered = query.trim() !== "" || segment !== "all" || bin != null;

  const rows = useMemo(() => {
    const q = query.trim();
    return all
      // Unfiltered, the demo stores sit in their own cards above the list.
      .filter((m) => filtered || !m.is_demo)
      .filter((m) => !q || String(m.merchant_id).includes(q) || m.name.includes(q))
      .filter((m) => segment === "all" || (segment === "risk" ? m.gap_count > 0 : m.gap_count === 0))
      .filter((m) => bin == null || binOf(m.score) === bin)
      .sort(SORTS[sort].cmp);
  }, [all, filtered, query, segment, bin, sort]);

  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setLimit(PAGE_SIZE); };
  const clearFilters = () => { setQuery(""); setSegment("all"); setBin(null); setLimit(PAGE_SIZE); };

  return (
    <>
      <section className="home-hero">
        <h1 className="home-logo"><img src="/favicon.svg" alt="" />MFP</h1>
        <p>เปลี่ยนทุกยอดขายให้เป็นโอกาสทางการเงิน</p>
        <form className="search" role="search" onSubmit={(e) => {
          e.preventDefault();
          const exact = all.find((m) => String(m.merchant_id) === query.trim());
          if (exact) navigate(`/merchants/${exact.merchant_id}`);
        }}>
          <Icon name="search" />
          <input type="search" placeholder="พิมพ์เลขร้านหรือชื่อร้าน" value={query}
            onChange={(e) => reset(setQuery)(e.target.value)} aria-label="ค้นหาร้าน" />
        </form>
      </section>

      {state.status === "loading" && <div className="demo-grid"><Skeleton height={112} /><Skeleton height={112} /><Skeleton height={112} /></div>}

      {!filtered && demos.length > 0 && (
        <section className="home-section">
          <h2>ร้านสาธิต</h2>
          <div className="demo-grid">{demos.map((m) => <DemoCard key={m.merchant_id} m={m} />)}</div>
        </section>
      )}

      <Card title={`ร้านทั้งหมด (${all.length.toLocaleString("en-US")})`}
        action={filtered ? <span className="muted small">{rows.length.toLocaleString("en-US")} ร้านตรงเงื่อนไข</span> : undefined}>
        <div className="chip-group" role="group" aria-label="กลุ่มร้าน">
          {SEGMENTS.map((s) => (
            <button key={s.key} className={`chip${segment === s.key ? " on" : ""}`} aria-pressed={segment === s.key}
              onClick={() => reset(setSegment)(s.key)}>
              {segment === s.key && <Icon name="check" size={16} />}{s.label}
            </button>
          ))}
        </div>
        <Disclosure open={moreOpen} onToggle={() => setMoreOpen((o) => !o)}>เรียงลำดับและช่วงสัญญาณการเงิน</Disclosure>
        {moreOpen && (
          <>
            <div className="filter-bar">
              <label className="select-wrap">
                <span className="muted small">เรียง</span>
                <select className="select" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                  {Object.entries(SORTS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
                </select>
              </label>
            </div>
            <div className="bin-chips" role="group" aria-label="ช่วงคะแนนสัญญาณการเงิน">
              <span className="muted small">ช่วงสัญญาณการเงิน <span className="badge experimental">ทดลอง</span></span>
              {bins.map((b, i) => (
                <button key={b.from} className={`chip${bin === i ? " on" : ""}`} aria-pressed={bin === i}
                  onClick={() => reset(setBin)(bin === i ? null : i)} disabled={b.total === 0}>
                  {b.from}–{b.to} ({b.total})
                </button>
              ))}
            </div>
          </>
        )}
        {isMock && <p className="muted small">โหมด mock: เปิดดูรายละเอียดได้เฉพาะร้าน 1, 2, 25, 817</p>}

        {state.status === "loading" && <Skeleton height={240} />}
        {state.status === "error" && <ErrorState error={state.error} onRetry={retry} />}
        {state.status === "ok" && (
          <>
            <ul className="merchant-list">{rows.slice(0, limit).map((m) => <Row key={m.merchant_id} m={m} />)}</ul>
            {rows.length === 0 && (
              <div className="state">
                <p>{query.trim() ? `ไม่พบร้านที่ตรงกับ “${query.trim()}”` : "ไม่พบร้านที่ตรงเงื่อนไข"}</p>
                <button className="btn tonal" onClick={clearFilters}>{query.trim() ? "ล้างคำค้นหา" : "ล้างตัวกรอง"}</button>
              </div>
            )}
            {rows.length > limit && (
              <div style={{ textAlign: "center", marginTop: 16 }}>
                <button className="btn" onClick={() => setLimit((l) => l + PAGE_SIZE)}>
                  แสดงเพิ่ม ({(rows.length - limit).toLocaleString("en-US")} ร้านที่เหลือ)
                </button>
              </div>
            )}
          </>
        )}
      </Card>

      {state.status === "ok" && (
        <Card>
          <Disclosure open={overviewOpen} onToggle={() => setOverviewOpen((o) => !o)}>ภาพรวมทุกร้าน</Disclosure>
          {overviewOpen && (
            <>
              <Kpis all={all} />
              <Scene3D height={360} fallback={<div className="scene3d-fallback">เปิดภาพ 3 มิติไม่ได้ในเบราว์เซอร์นี้ ใช้ตัวกรองช่วงสัญญาณการเงินด้านบนแทนได้</div>}>
                <ScoreHistogram3D bins={bins} selected={bin} onSelect={reset(setBin)} />
              </Scene3D>
              <div className="scene-caption">
                <span><i className="swatch bar" style={{ "--c": "var(--series-forecast)" } as React.CSSProperties} />จำนวนร้านในแต่ละช่วงสัญญาณการเงิน</span>
                <span><i className="swatch bar" style={{ "--c": "var(--bad)" } as React.CSSProperties} />ในนั้น ร้านที่เงินอาจไม่พอ</span>
                <span className="muted">ลาก = หมุน · คลิกแท่ง = กรองรายชื่อร้าน</span>
              </div>
            </>
          )}
        </Card>
      )}
    </>
  );
}
