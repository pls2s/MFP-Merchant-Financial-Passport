import { NavLink, Route, Routes } from "react-router-dom";
import { isMock } from "./api";
import { Card } from "./components/ui";
import { MerchantPicker } from "./pages/MerchantPicker";
import { ModelResults } from "./pages/ModelResults";
import { Passport } from "./pages/Passport";

export default function App() {
  return (
    <>
      <header className="topbar">
        <NavLink to="/" className="brand"><img src="/favicon.svg" alt="MFP" /><span>Merchant Financial Passport</span></NavLink>
        <nav className="nav">
          <NavLink to="/" end>ร้านค้า</NavLink>
          <NavLink to="/model-results">ผลโมเดล</NavLink>
        </nav>
        <span className="mode">{isMock ? "โหมด mock" : "เชื่อมต่อ API"} · ต้นแบบเพื่อการศึกษา</span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<MerchantPicker />} />
          <Route path="/merchants/:id" element={<Passport />} />
          <Route path="/model-results" element={<ModelResults />} />
          <Route path="*" element={<Card><p className="state">ไม่พบหน้านี้</p></Card>} />
        </Routes>
      </main>
    </>
  );
}
