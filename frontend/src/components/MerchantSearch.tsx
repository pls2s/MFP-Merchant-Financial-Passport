import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { Merchant } from "../types";
import { useAsync } from "../useAsync";
import { Icon } from "./ui";

const MAX_OPTIONS = 8;

/** App-bar search: suggestions drop down while typing, demo stores first. */
export function MerchantSearch() {
  const [state] = useAsync(api.merchants, []);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  const box = useRef<HTMLDivElement>(null);

  const options = useMemo(() => {
    const all: Merchant[] = state.status === "ok" ? state.data : [];
    const q = query.trim();
    return all
      .filter((m) => (q ? String(m.merchant_id).includes(q) || m.name.includes(q) : m.is_demo))
      .sort((a, b) => Number(b.is_demo) - Number(a.is_demo) || a.merchant_id - b.merchant_id)
      .slice(0, MAX_OPTIONS);
  }, [state, query]);

  const go = (m: Merchant) => {
    setQuery("");
    setOpen(false);
    navigate(`/merchants/${m.merchant_id}`);
  };

  return (
    <div className="search" ref={box} onBlur={(e) => { if (!box.current?.contains(e.relatedTarget)) setOpen(false); }}>
      <Icon name="search" />
      <input type="search" role="combobox" aria-label="ค้นหาร้าน" aria-expanded={open} aria-controls="merchant-options"
        aria-autocomplete="list" aria-activedescendant={open && options[active] ? `merchant-option-${active}` : undefined}
        placeholder="ค้นหาร้าน (เลขร้านหรือชื่อ)" value={query}
        onFocus={() => setOpen(true)}
        onChange={(e) => { setQuery(e.target.value); setActive(0); setOpen(true); }}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            const step = e.key === "ArrowDown" ? 1 : -1;
            setActive((a) => (options.length ? (a + step + options.length) % options.length : 0));
          }
          if (e.key === "Enter" && open && options[active]) go(options[active]);
        }} />
      {open && (
        <ul className="search-menu" id="merchant-options" role="listbox" aria-label="ร้านที่ตรงกับคำค้นหา">
          {options.map((m, i) => (
            <li key={m.merchant_id} id={`merchant-option-${i}`} role="option" aria-selected={i === active}
              className={i === active ? "on" : ""} onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => e.preventDefault()} onClick={() => go(m)}>
              <span>{m.name}</span>
              {m.is_demo && <span className="badge accent">ร้านสาธิต</span>}
              <span className={`small ${m.gap_count > 0 ? "bad-text" : "good-text"}`}>
                {m.gap_count > 0 ? `เงินอาจไม่พอ ${m.gap_count} ครั้ง` : "ไม่พบความเสี่ยง"}
              </span>
            </li>
          ))}
          {options.length === 0 && (
            <li className="search-empty">{state.status === "loading" ? "กำลังโหลด…" : state.status === "error" ? "โหลดรายชื่อร้านไม่สำเร็จ" : "ไม่พบร้านที่ตรงกับคำค้นหา"}</li>
          )}
        </ul>
      )}
    </div>
  );
}
