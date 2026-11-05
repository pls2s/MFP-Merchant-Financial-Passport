import { useState } from "react";
import { money, thaiDate } from "../format";
import type { Gap } from "../types";
import { Card, SampleBadge } from "./ui";

// Mock product matching (CLAUDE.md: simple rules + mock offers, cut first if short on time).
// These are not real offers from any provider.
const OFFERS = [
  { name: "เงินทุนหมุนเวียนระยะสั้น", detail: "วงเงินสำหรับช่วงที่รายจ่ายมาก่อนรายรับ" },
  { name: "รับเงินจากยอดขายล่วงหน้า", detail: "รับเงินบางส่วนจากยอดขายที่คาดว่าจะเข้า" },
];

export function Offers({ gaps }: { gaps: Gap[] }) {
  const [opened, setOpened] = useState<string | null>(null);
  if (!gaps.length) return null;
  const first = gaps[0];
  return (
    <Card title="ตัวเลือกที่อาจช่วยได้" badges={<SampleBadge />}>
      <p className="muted small" style={{ marginTop: 0 }}>
        เพราะคาดว่าวันที่ {thaiDate(first.date)} เงินสดอาจขาดประมาณ {money(first.shortfall)}
      </p>
      <div className="grid-2">
        {OFFERS.map((o) => (
          <div key={o.name} className="offer">
            <strong>{o.name}</strong>
            {opened === o.name && <div className="muted small">{o.detail}</div>}
            <button className="btn ghost" aria-expanded={opened === o.name}
              onClick={() => setOpened(opened === o.name ? null : o.name)}>
              {opened === o.name ? "ซ่อนข้อมูล" : "ดูข้อมูลเพิ่มเติม"}
            </button>
          </div>
        ))}
      </div>
      <p className="disclaimer">ข้อเสนอจำลอง ไม่ใช่ข้อเสนอจริงจากผู้ให้บริการ และไม่ใช่การพิจารณาสินเชื่อ</p>
    </Card>
  );
}
