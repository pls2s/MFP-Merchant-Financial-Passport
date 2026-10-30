import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { isMock } from "./api";
import { MerchantSearch } from "./components/MerchantSearch";
import { Card, Icon, InfoDialog } from "./components/ui";
import { MerchantPicker } from "./pages/MerchantPicker";
import { ModelResults } from "./pages/ModelResults";
import { Passport } from "./pages/Passport";
import { useTheme } from "./theme";

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const { pathname } = useLocation();
  const [scrolled, setScrolled] = useState(false);
  const inStores = pathname === "/" || pathname.startsWith("/merchants");
  const modeText = isMock ? "โหมด mock" : "เชื่อมต่อ API";

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 0);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
      <header className={`topbar${scrolled ? " scrolled" : ""}`}>
        <Link to="/" className="brand">
          <img src="/favicon.svg" alt="" />
          <span className="brand-text">
            <b>MFP</b>
            <small>Merchant Financial Passport</small>
          </span>
        </Link>
        {/* The home page has the big search box in its centre. */}
        {pathname !== "/" && <MerchantSearch />}
        <span className="topbar-actions">
          <span className="mode"><i className={isMock ? "dot warn" : "dot live"} />{modeText}</span>
          <button className="icon-btn" onClick={toggleTheme} aria-label={theme === "dark" ? "เปลี่ยนเป็นธีมสว่าง" : "เปลี่ยนเป็นธีมมืด"}
            title={theme === "dark" ? "ธีมสว่าง" : "ธีมมืด"}>
            <Icon name={theme === "dark" ? "light_mode" : "dark_mode"} />
          </button>
          <InfoDialog label="เกี่ยวกับต้นแบบนี้" title="เกี่ยวกับต้นแบบนี้">
            <p>{modeText} · ต้นแบบเพื่อการศึกษา</p>
            <p className="muted">ยอดขายมาจาก Rossmann Store Sales ส่วนรายจ่าย ยอดเงิน และข้อเสนอเป็นข้อมูลจำลอง</p>
          </InfoDialog>
        </span>
      </header>

      <nav className="rail" aria-label="เมนูหลัก">
        <Link to="/" className={inStores ? "active" : ""} aria-current={inStores ? "page" : undefined}>
          <span className="rail-icon"><Icon name="storefront" size={24} filled={inStores} /></span>ร้านค้า
        </Link>
        <NavLink to="/model-results">
          {({ isActive }) => <><span className="rail-icon"><Icon name="monitoring" size={24} filled={isActive} /></span>ผลโมเดล</>}
        </NavLink>
      </nav>

      <div className="content">
        <main>
          <Routes>
            <Route path="/" element={<MerchantPicker />} />
            <Route path="/merchants/:id" element={<Passport />} />
            <Route path="/model-results" element={<ModelResults />} />
            <Route path="*" element={<Card><p className="state">ไม่พบหน้านี้</p></Card>} />
          </Routes>
        </main>
        <footer className="footer">
          ต้นแบบเพื่อการศึกษา · ยอดขายจาก Rossmann Store Sales · รายจ่าย ยอดเงิน และข้อเสนอเป็นข้อมูลจำลอง ·
          สัญญาณการเงินเป็นการทดลอง ไม่ใช่คะแนนเครดิต
        </footer>
      </div>
    </>
  );
}
