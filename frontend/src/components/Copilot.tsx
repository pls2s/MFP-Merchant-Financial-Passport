import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ChatMessage, CopilotResponse } from "../types";
import { Icon, SyntheticBadge } from "./ui";

const QUICK_QUESTIONS = [
  "สรุปสถานะร้านให้หน่อย",
  "สัปดาห์หน้าต้องจ่ายอะไรบ้าง",
  "ควรทำยังไงให้ผ่านวันที่เงินไม่พอ",
  "เดือนหน้ายอดขายจะเป็นยังไง",
  "ถ้ายอดขายต่ำกว่าที่คาดจะเป็นยังไง",
  "โปรโมชันช่วยยอดขายแค่ไหน",
  "ทำไมคะแนนได้เท่านี้",
  "ระบบทายยอดขายยังไง แม่นแค่ไหน",
];
const INITIAL_QUESTIONS = 3;
const SLOW_AFTER_MS = 8000;

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
  const [slow, setSlow] = useState(false);
  const [allQuestions, setAllQuestions] = useState(false);
  const [open, setOpen] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!loading) return;
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => { clearTimeout(timer); setSlow(false); };
  }, [loading]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, loading, open]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

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

  // Not modal: the page stays usable so the owner can check the answer against its figures.
  if (!open) {
    return (
      <button className="chat-fab" aria-label="เปิดผู้ช่วยการเงินร้านค้า" title="ถามผู้ช่วยการเงินร้านค้า" onClick={() => setOpen(true)}>
        <span aria-hidden>💬</span>
      </button>
    );
  }

  return (
    <section className="chat-panel" role="dialog" aria-label="ผู้ช่วยการเงินร้านค้า"
      onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
      <div className="chat-head">
        <div className="chat-title">
          <h2>ผู้ช่วยการเงินร้านค้า</h2>
          <span className="chat-badges"><span className="badge">Typhoon</span><SyntheticBadge /></span>
        </div>
        {turns.length > 0 && (
          <button className="btn ghost" disabled={loading} onClick={() => { setTurns([]); setFailed(false); }}>เริ่มคุยใหม่</button>
        )}
        <button className="icon-btn" aria-label="ปิดผู้ช่วย" onClick={() => setOpen(false)}><Icon name="close" /></button>
      </div>

      <div className="chat-scroll" ref={threadRef}>
        {turns.length === 0 && (
          <>
            <p className="muted small" style={{ margin: 0 }}>
              ถามได้ทั้งยอดขาย รายจ่าย ยอดเงิน สถานการณ์ "ถ้า..." และวิธีบริหารเงินสด ·
              ใช้เฉพาะตัวเลขที่ระบบคำนวณไว้ ไม่ให้คำแนะนำด้านสินเชื่อ
            </p>
            <div className="chips" style={{ marginTop: 12 }}>
              {(allQuestions ? QUICK_QUESTIONS : QUICK_QUESTIONS.slice(0, INITIAL_QUESTIONS)).map((q) => (
                <button key={q} className="btn chip" disabled={loading} onClick={() => ask(q)}>{q}</button>
              ))}
              {!allQuestions && <button className="btn ghost" onClick={() => setAllQuestions(true)}>ดูคำถามอื่น</button>}
            </div>
          </>
        )}
        {turns.length > 0 && (
          <div className="chat-thread">
            {turns.map((t, i) => (
              <div key={i} className={`chat-msg ${t.role}`}>
                <div className="chat-bubble">{t.role === "assistant" ? renderAnswer(t.content) : t.content}</div>
                {t.source && (
                  <span className="badge">{t.source === "llm" ? "AI (Typhoon)" : "สรุปอัตโนมัติ"}</span>
                )}
              </div>
            ))}
            {loading && (
              <div className="chat-msg assistant">
                <div className="chat-bubble muted" role="status">
                  <span className="typing" aria-hidden><i /><i /><i /></span>
                  {slow ? "ใช้เวลานานกว่าปกติเล็กน้อย" : "กำลังสรุปข้อมูล…"}
                </div>
              </div>
            )}
          </div>
        )}
        {failed && !loading && <p className="muted small">ขออภัย ไม่สามารถสร้างคำอธิบายได้ในขณะนี้</p>}
      </div>

      <div className="chat-foot">
        <form
          className="copilot-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (input.trim() && !loading) ask(input.trim());
          }}
        >
          <input
            ref={inputRef}
            className="input"
            value={input}
            maxLength={500}
            aria-label="คำถามถึงผู้ช่วย"
            placeholder={turns.length ? "ถามต่อได้เลย เช่น แล้วถ้าเลื่อนจ่ายล่ะ" : "พิมพ์คำถามเกี่ยวกับร้าน"}
            onChange={(e) => setInput(e.target.value)}
          />
          <button className="btn primary" disabled={loading || !input.trim()}><Icon name="send" />ถาม</button>
        </form>
        {disclaimer && <div className="disclaimer">{disclaimer} · คำตอบจาก AI ควรตรวจกับตัวเลขในหน้านี้อีกครั้ง</div>}
      </div>
    </section>
  );
}
