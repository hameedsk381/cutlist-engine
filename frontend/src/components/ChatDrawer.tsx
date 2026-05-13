import { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Send } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { aiChat } from '../api';

interface Props {
  context: any;
  sessionId?: string;
  onClose: () => void;
}

export default function ChatDrawer({ context, sessionId, onClose }: Props) {
  const [msg, setMsg] = useState('');
  const [history, setHistory] = useState<{ role: string; content: string }[]>([]);
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [history, sending]);

  const send = async () => {
    const text = msg.trim();
    if (!text || sending) return;
    setSending(true);
    const userMsg = { role: 'user', content: text };
    setHistory(h => [...h, userMsg]);
    setMsg('');

    try {
      const response = await aiChat(text, context, history, sessionId);
      setHistory(h => [...h, { role: 'assistant', content: response }]);
    } catch {
      setHistory(h => [...h, { role: 'assistant', content: 'Sorry, I could not connect to the AI service.' }]);
    } finally {
      setSending(false);
    }
  };

  const boardCount = context?.boards?.length || 0;
  const sheetCount = context?.sheets?.length || 0;

  return (
    <div className="chat-drawer">
      {/* Header */}
      <div className="flex items-center justify-between" style={{
        padding: '16px 20px', borderBottom: '1px solid var(--border)',
      }}>
        <div className="flex items-center gap-2">
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'var(--accent-dim)', color: 'var(--accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <MessageSquare size={16} />
          </div>
          <div>
            <h3 style={{ fontSize: 14 }}>Workshop Brain</h3>
            <p style={{ fontSize: 11, color: 'var(--text-dim)' }}>AI-powered assistant</p>
          </div>
        </div>
        <button className="btn btn-icon btn-ghost" onClick={onClose}>
          <X size={18} />
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} style={{ flex: 1, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Welcome */}
        <div style={{
          padding: 14, borderRadius: 'var(--radius-sm)',
          background: 'var(--surface-hover)', fontSize: 13,
          color: 'var(--text-secondary)', lineHeight: 1.6,
        }}>
          नमस्ते! I'm your AI workshop assistant. I have context for <strong style={{ color: 'var(--text)' }}>{boardCount} boards</strong> and <strong style={{ color: 'var(--text)' }}>{sheetCount} sheets</strong>. Ask me about dimensions, material, assembly tips, or cost estimates!
        </div>

        {/* Quick prompts */}
        {history.length === 0 && (
          <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
            {['What hardware do I need?', 'How to reduce waste?', 'Edge banding advice'].map(q => (
              <button
                key={q}
                className="btn btn-sm btn-secondary"
                onClick={() => { setMsg(q); }}
                style={{ fontSize: 11 }}
              >{q}</button>
            ))}
          </div>
        )}

        {/* Chat history */}
        {history.map((h, i) => (
          <div
            key={i}
            style={{
              padding: 12, borderRadius: 'var(--radius-sm)', fontSize: 13,
              ...(h.role === 'user'
                ? { background: 'var(--accent)', color: '#000', alignSelf: 'flex-end', maxWidth: '85%', fontWeight: 500 }
                : { background: 'var(--surface-hover)', color: 'var(--text)', alignSelf: 'flex-start', maxWidth: '90%' }),
            }}
          >
            <div className="chat-md">
              <ReactMarkdown>{h.content}</ReactMarkdown>
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex items-center gap-2" style={{ padding: 12, fontSize: 12, color: 'var(--text-dim)' }}>
            <div className="spinner" />
            Thinking…
          </div>
        )}
      </div>

      {/* Input */}
      <div style={{ padding: 16, borderTop: '1px solid var(--border)' }}>
        <div className="flex gap-2">
          <input
            className="input"
            value={msg}
            onChange={e => setMsg(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send()}
            placeholder="Ask about your project…"
            style={{ fontSize: 13 }}
          />
          <button
            className="btn btn-primary btn-icon"
            onClick={send}
            disabled={!msg.trim() || sending}
            style={{ flexShrink: 0 }}
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
