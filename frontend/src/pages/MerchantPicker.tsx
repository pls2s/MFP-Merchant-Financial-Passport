import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, isMock } from "../api";
import { Card, ErrorState, Skeleton } from "../components/ui";
import type { Merchant } from "../types";
import { useAsync } from "../useAsync";

const PAGE_SIZE = 50;

function Row({ m }: { m: Merchant }) {
  return (
    <li>
      <Link className="merchant-row" to={`/merchants/${m.merchant_id}`}>
        <span className="name">{m.name}</span>
        {m.is_demo && <span className="badge experimental">ร้านสาธิต</span>}
        {m.gap_count > 0 && <span className="badge danger">เงินอาจไม่พอ {m.gap_count} ครั้ง</span>}
        <span className="score num">สัญญาณการเงิน {m.score}/100 <span className="badge">ทดลอง</span></span>
      </Link>
    </li>
  );
}

export function MerchantPicker() {
  const [state, retry] = useAsync(api.merchants, []);
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(PAGE_SIZE);

  const { demo, others } = useMemo(() => {
    const all = state.status === "ok" ? state.data : [];
    const q = query.trim();
    const match = q ? all.filter((m) => String(m.merchant_id).includes(q) || m.name.includes(q)) : all;
    return { demo: match.filter((m) => m.is_demo), others: match.filter((m) => !m.is_demo) };
  }, [state, query]);

  return (
    <>
      <div className="page-head">
        <h1>เลือกร้านค้า</h1>
        <p>ดูยอดขายที่คาดการณ์ วันที่เงินสดอาจไม่พอ และสัญญาณการเงินของแต่ละร้าน</p>
      </div>
      <Card>
        <input
          className="input"
          type="search"
          placeholder="ค้นหาเลขร้าน เช่น 1, 25, 817"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setLimit(PAGE_SIZE);
          }}
        />
        {isMock && (
          <p className="muted small">โหมด mock: เปิดดูรายละเอียดได้เฉพาะร้าน 1, 2, 25, 817</p>
        )}
        {state.status === "loading" && <div style={{ marginTop: 16 }}><Skeleton height={240} /></div>}
        {state.status === "error" && <ErrorState error={state.error} onRetry={retry} />}
        {state.status === "ok" && (
          <>
            {demo.length > 0 && (
              <>
                <div className="section-label">ร้านสาธิต</div>
                <ul className="merchant-list">{demo.map((m) => <Row key={m.merchant_id} m={m} />)}</ul>
              </>
            )}
            <div className="section-label">ร้านทั้งหมด ({others.length.toLocaleString("en-US")})</div>
            <ul className="merchant-list">
              {others.slice(0, limit).map((m) => <Row key={m.merchant_id} m={m} />)}
            </ul>
            {others.length === 0 && demo.length === 0 && <p className="state">ไม่พบร้านที่ค้นหา</p>}
            {others.length > limit && (
              <div style={{ textAlign: "center", marginTop: 12 }}>
                <button className="btn" onClick={() => setLimit((l) => l + PAGE_SIZE)}>แสดงเพิ่ม</button>
              </div>
            )}
          </>
        )}
      </Card>
    </>
  );
}
