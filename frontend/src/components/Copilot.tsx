import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ChatMessage, CopilotResponse } from "../types";
import { Card } from "./ui";

const QUICK_QUESTIONS = [
  "สรุปสถานะร้านให้หน่อย",
  "สัปดาห์หน้าต้องจ่ายอะไรบ้าง",
  "ถ้ายอดขายต่ำกว่าที่คาดจะเป็นยังไง",
  "ควรทำยังไงให้ผ่านวันที่เงินไม่พอ",
  "โปรโมชันช่วยยอดขายแค่ไหน",
  "ทำไมคะแนนได้เท่านี้",
  "ระบบทายยอดขายยังไง แม่นแค่ไหน",
];

/** Minimal rendering of the LLM's markdown: **bold** and "> " quote markers. */
function renderAnswer(text: string) {
  return text
    .replace(/^>\s?/gm, "")
    .split(/(\*\*[^*]+\*\*)/g)
    .map((part, i) => (part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part));
}

interface Turn extends ChatMessage {
  source?: CopilotResponse["source"];
}

export function Copilot({ merchantId }: { merchantId: number }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, loading]);

  async function ask(question: string) {
    const history: ChatMessage[] = turns.map(({ role, content }) => ({ role, content }));
    setTurns((t) => [...t, { role: "user", content: question }]);
    setInput("");
    setLoading(true);
    setFailed(false);
    try {
      const res = await api.copilot(merchantId, question, history);
      // The disclaimer is shown once under the thread, not inside every answer.
      const content = res.answer.replace(res.disclaimer, "").trim();
      setTurns((t) => [...t, { role: "assistant", content, source: res.source }]);
      setDisclaimer(res.disclaimer);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card
      title="ผู้ช่วยการเงินร้านค้า"
      badges={<span className="badge">Typhoon</span>}
      action={turns.length > 0 && (
        <button className="btn chip" disabled={loading} onClick={() => { setTurns([]); setFailed(false); }}>
          เริ่มคุยใหม่
        </button>
      )}
    >
      <p className="muted small" style={{ margin: 0 }}>
        ถามได้ทั้งยอดขาย รายจ่าย ยอดเงิน สถานการณ์ "ถ้า..." และวิธีบริหารเงินสด ·
        ใช้เฉพาะตัวเลขที่ระบบคำนวณไว้ ไม่ให้คำแนะนำด้านสินเชื่อ
      </p>

      {turns.length > 0 && (
        <div className="chat-thread" ref={threadRef}>
          {turns.map((t, i) => (
            <div key={i} className={`chat-msg ${t.role}`}>
              <div className="chat-bubble">{t.role === "assistant" ? renderAnswer(t.content) : t.content}</div>
              {t.source && (
                <div className="chat-meta">{t.source === "llm" ? "AI (Typhoon)" : "สรุปอัตโนมัติ"}</div>
              )}
            </div>
          ))}
          {loading && (
            <div className="chat-msg assistant">
              <div className="chat-bubble muted"><span className="spinner" /> กำลังคิด…</div>
            </div>
          )}
        </div>
      )}
      {failed && !loading && <p className="muted small">ขออภัย ไม่สามารถตอบได้ในขณะนี้ ลองใหม่อีกครั้ง</p>}

      <div className="chips" style={{ marginTop: 12 }}>
        {QUICK_QUESTIONS.map((q) => (
          <button key={q} className="btn chip" disabled={loading} onClick={() => ask(q)}>{q}</button>
        ))}
      </div>
      <form
        className="copilot-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (input.trim() && !loading) ask(input.trim());
        }}
      >
        <input
          className="input"
          value={input}
          maxLength={500}
          placeholder={turns.length ? "ถามต่อได้เลย เช่น แล้วถ้าเลื่อนจ่ายล่ะ" : "พิมพ์คำถามเกี่ยวกับร้าน"}
          onChange={(e) => setInput(e.target.value)}
        />
        <button className="btn primary" disabled={loading || !input.trim()}>ส่ง</button>
      </form>
      {disclaimer && <div className="disclaimer">{disclaimer} · คำตอบจาก AI ควรตรวจกับตัวเลขในหน้านี้อีกครั้ง</div>}
    </Card>
  );
}
