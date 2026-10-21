import { useState } from "react";
import { api } from "../api";
import type { CopilotResponse } from "../types";
import { Card } from "./ui";

const QUICK_QUESTIONS = [
  { label: "สรุปสถานะร้าน", question: null },
  { label: "สัปดาห์หน้าต้องระวังอะไร", question: "สัปดาห์หน้าต้องระวังอะไร" },
  { label: "ทำไมเงินอาจไม่พอ", question: "ทำไมเงินสดอาจไม่พอ และเกิดจากรายจ่ายอะไร" },
];

export function Copilot({ merchantId }: { merchantId: number }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<CopilotResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  async function ask(q: string | null) {
    setLoading(true);
    setFailed(false);
    try {
      setAnswer(await api.copilot(merchantId, q));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card
      title="ผู้ช่วยอธิบายตัวเลข"
      badges={answer && (
        <span className="badge">{answer.source === "llm" ? "AI (Typhoon)" : "สรุปอัตโนมัติ"}</span>
      )}
    >
      <p className="muted small" style={{ margin: 0 }}>
        อธิบายจากตัวเลขที่ระบบคำนวณไว้แล้วเท่านั้น ไม่ได้ให้คำแนะนำด้านสินเชื่อ
      </p>
      <div className="chips" style={{ marginTop: 10 }}>
        {QUICK_QUESTIONS.map((q) => (
          <button key={q.label} className="btn chip" disabled={loading} onClick={() => ask(q.question)}>
            {q.label}
          </button>
        ))}
      </div>
      <form
        className="copilot-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim()) ask(question.trim());
        }}
      >
        <input
          className="input"
          value={question}
          maxLength={500}
          placeholder="พิมพ์คำถาม เช่น เดือนนี้ร้านเป็นอย่างไรบ้าง"
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button className="btn primary" disabled={loading || !question.trim()}>ถาม</button>
      </form>

      {loading && (
        <p className="muted small"><span className="spinner" /> กำลังสร้างคำอธิบาย…</p>
      )}
      {failed && !loading && <p className="muted">ขออภัย ไม่สามารถสร้างคำอธิบายได้ในขณะนี้</p>}
      {answer && !loading && (
        <>
          {/* The backend may already append the disclaimer; show it once, below the answer. */}
          <div className="copilot-answer">{answer.answer.replace(answer.disclaimer, "").trim()}</div>
          <div className="disclaimer">{answer.disclaimer}</div>
        </>
      )}
    </Card>
  );
}
