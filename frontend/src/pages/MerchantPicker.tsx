import { lazy, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, isMock } from "../api";
import { Scene3D } from "../components/three/Scene3D";
import type { ScoreBin } from "../components/three/ScoreHistogram3D";
import { Card, ErrorState, Segmented, Skeleton } from "../components/ui";
import { percent } from "../format";
import type { Merchant } from "../types";
import { useAsync } from "../useAsync";

const ScoreHistogram3D = lazy(() => import("../components/three/ScoreHistogram3D"));

const PAGE_SIZE = 50;

const SEGMENTS = [
  { key: "all", label: "ทั้งหมด" },
  { key: "demo", label: "ร้านสาธิต" },
  { key: "risk", label: "เงินอาจไม่พอ" },
  { key: "clear", label: "ไม่พบความเสี่ยง" },
] as const;
type Segment = (typeof SEGMENTS)[number]["key"];

const SORTS = {
  default: { label: "ร้านสาธิตก่อน แล้วตามเลขร้าน", cmp: (a: Merchant, b: Merchant) => Number(b.is_demo) - Number(a.is_demo) || a.merchant_id - b.merchant_id },
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

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : 0;
};

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
      <div className="kpi">
        <span className="kpi-label">ความคลาดเคลื่อนพยากรณ์ (มัธยฐาน)</span>
        <span className="kpi-value">{percent(median(all.map((m) => m.forecast_wape)), 1)}</span>
        <span className="kpi-sub">WAPE ต่อร้าน · LSTM+GRU</span>
      </div>
    </div>
  );
}

function ScoreBar({ score }: { score: number }) {
  return (
    <span className="score-cell">
      <span className="score-track"><span className="score-fill" style={{ width: `${score}%` }} /></span>
      <b className="num">{score}</b>
    </span>
  );
}

function Row({ m }: { m: Merchant }) {
  return (
    <li>
      <Link className="merchant-row" to={`/merchants/${m.merchant_id}`}>
        <span className="m-name">
          <span className="avatar">{m.merchant_id}</span>
          <span>
            <b>{m.name}</b>
            <span className="m-badges">
              {m.is_demo && <span className="badge experimental">ร้านสาธิต</span>}
              {m.gap_count > 0
                ? <span className="badge danger">⚠ เงินอาจไม่พอ {m.gap_count} ครั้ง</span>
                : <span className="badge good">✓ ไม่พบความเสี่ยงใน 14 วัน</span>}
            </span>
          </span>
        </span>
        <span className="m-score"><span className="m-label">สัญญาณการเงิน <span className="badge">ทดลอง</span></span><ScoreBar score={m.score} /></span>
        <span className="m-wape"><span className="m-label">คลาดเคลื่อน</span><b className="num">{percent(m.forecast_wape, 1)}</b></span>
        <span className="m-go" aria-hidden>→</span>
      </Link>
    </li>
  );
}

export function MerchantPicker() {
  const [state, retry] = useAsync(api.merchants, []);
  const [query, setQuery] = useState("");
  const [segment, setSegment] = useState<Segment>("all");
  const [sort, setSort] = useState<SortKey>("default");
  const [bin, setBin] = useState<number | null>(null);
  const [limit, setLimit] = useState(PAGE_SIZE);

  const all = useMemo(() => (state.status === "ok" ? state.data : []), [state]);
  const bins = useMemo(() => scoreBins(all), [all]);

  const rows = useMemo(() => {
    const q = query.trim();
    return all
      .filter((m) => !q || String(m.merchant_id).includes(q) || m.name.includes(q))
      .filter((m) => segment === "all" || (segment === "demo" ? m.is_demo : segment === "risk" ? m.gap_count > 0 : m.gap_count === 0))
      .filter((m) => bin == null || binOf(m.score) === bin)
      .sort(SORTS[sort].cmp);
  }, [all, query, segment, bin, sort]);

  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setLimit(PAGE_SIZE); };
  const filtered = query.trim() !== "" || segment !== "all" || bin != null;

  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow">Merchant Financial Passport</div>
          <h1>เห็นเงินสดของร้าน<br /><span className="grad-text">ก่อนที่มันจะขาด</span></h1>
          <p>
            พยากรณ์ยอดขายรายวันด้วย LSTM + GRU แล้วแปลงเป็นคำเตือนวันที่เงินสดอาจไม่พอ
            และสัญญาณการเงินแบบอธิบายได้ ของร้านค้า {all.length ? all.length.toLocaleString("en-US") : "1,115"} ร้าน
          </p>
          {state.status === "ok" && <Kpis all={all} />}
          {state.status === "loading" && <Skeleton height={110} />}
        </div>
        <div className="hero-scene">
          {state.status === "ok" && (
            <Scene3D height={420} fallback={<div className="scene3d-fallback">เปิดภาพ 3 มิติไม่ได้ในเบราว์เซอร์นี้ ใช้ตัวกรองช่วงคะแนนด้านล่างแทนได้</div>}>
              <ScoreHistogram3D bins={bins} selected={bin} onSelect={reset(setBin)} />
            </Scene3D>
          )}
          <div className="scene-caption">
            <span><i className="swatch bar" style={{ "--c": "var(--series-forecast)" } as React.CSSProperties} />จำนวนร้านในแต่ละช่วงสัญญาณการเงิน</span>
            <span><i className="swatch bar" style={{ "--c": "var(--bad)" } as React.CSSProperties} />ในนั้น ร้านที่เงินอาจไม่พอ</span>
            <span className="muted">ลาก = หมุน · คลิกแท่ง = กรองรายชื่อร้าน</span>
          </div>
        </div>
      </section>

      <Card title="เลือกร้านค้า" eyebrow="ร้านค้า"
        action={<span className="muted small">{rows.length.toLocaleString("en-US")} ร้านตรงเงื่อนไข</span>}>
        <div className="filter-bar">
          <input className="input search" type="search" placeholder="ค้นหาเลขร้าน เช่น 1, 25, 817" value={query}
            onChange={(e) => reset(setQuery)(e.target.value)} aria-label="ค้นหาร้าน" />
          <Segmented label="กลุ่มร้าน" options={SEGMENTS} value={segment} onChange={reset(setSegment)} />
          <label className="select-wrap">
            <span className="muted small">เรียง</span>
            <select className="select" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
              {Object.entries(SORTS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
            </select>
          </label>
        </div>
        <div className="bin-chips" role="group" aria-label="ช่วงคะแนนสัญญาณการเงิน">
          <span className="muted small">ช่วงสัญญาณการเงิน</span>
          {bins.map((b, i) => (
            <button key={b.from} className={`chip mini${bin === i ? " on" : ""}`} aria-pressed={bin === i}
              onClick={() => reset(setBin)(bin === i ? null : i)} disabled={b.total === 0}>
              {b.from}–{b.to} <span className="muted">({b.total})</span>
            </button>
          ))}
          {filtered && (
            <button className="btn ghost small" onClick={() => { setQuery(""); setSegment("all"); setBin(null); setLimit(PAGE_SIZE); }}>
              ล้างตัวกรอง
            </button>
          )}
        </div>
        {isMock && <p className="muted small">โหมด mock: เปิดดูรายละเอียดได้เฉพาะร้าน 1, 2, 25, 817</p>}

        {state.status === "loading" && <Skeleton height={240} />}
        {state.status === "error" && <ErrorState error={state.error} onRetry={retry} />}
        {state.status === "ok" && (
          <>
            <ul className="merchant-list">{rows.slice(0, limit).map((m) => <Row key={m.merchant_id} m={m} />)}</ul>
            {rows.length === 0 && <p className="state">ไม่พบร้านที่ค้นหา</p>}
            {rows.length > limit && (
              <div style={{ textAlign: "center", marginTop: 14 }}>
                <button className="btn" onClick={() => setLimit((l) => l + PAGE_SIZE)}>
                  แสดงเพิ่ม ({(rows.length - limit).toLocaleString("en-US")} ร้านที่เหลือ)
                </button>
              </div>
            )}
          </>
        )}
      </Card>
    </>
  );
}
