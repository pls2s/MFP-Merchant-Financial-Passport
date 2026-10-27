import { NavLink, Route, Routes } from "react-router-dom";
import { isMock } from "./api";
import { Card } from "./components/ui";
import { MerchantPicker } from "./pages/MerchantPicker";
import { ModelResults } from "./pages/ModelResults";
import { Passport } from "./pages/Passport";
import { useTheme } from "./theme";

export default function App() {
  const [theme, toggleTheme] = useTheme();
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand">
            <img src="/favicon.svg" alt="" />
            <span className="brand-text">
              <b>MFP</b>
              <small>Merchant Financial Passport</small>
            </span>
          </NavLink>
          <nav className="nav">
            <NavLink to="/" end>ร้านค้า</NavLink>
            <NavLink to="/model-results">ผลโมเดล</NavLink>
          </nav>
          <span className="mode">
            <i className={isMock ? "dot warn" : "dot live"} />
            {isMock ? "โหมด mock" : "เชื่อมต่อ API"} · ต้นแบบเพื่อการศึกษา
          </span>
          <button className="icon-btn" onClick={toggleTheme} aria-label={theme === "dark" ? "เปลี่ยนเป็นธีมสว่าง" : "เปลี่ยนเป็นธีมมืด"}
            title={theme === "dark" ? "ธีมสว่าง" : "ธีมมืด"}>
            {theme === "dark" ? "☀" : "☾"}
          </button>
        </div>
      </header>
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
    </>
  );
}
