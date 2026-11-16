import { useEffect, useRef, useState } from 'react';
import { t } from '../i18n';
import ReactMarkdown from 'react-markdown';
import { LoaderCircle, Send, X } from 'lucide-react';
import { aiChat, friendlyError } from '../api';

interface Props {
  context: unknown;
  sessionId?: string;
  onClose: () => void;
}

interface Message { role: 'user' | 'assistant'; content: string; }

const SUGGESTIONS = [
  'How many sheets for 3 of these?',
  'Which edges should get edge banding?',
  'What hardware do I need?',
];

export default function ChatDrawer({ context, sessionId, onClose }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }); }, [messages, sending]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || sending) return;
    const history = messages.map(m => ({ role: m.role, content: m.content }));
    setMessages(m => [...m, { role: 'user', content: question }]);
    setInput('');
    setSending(true);
    try {
      const answer = await aiChat(question, context, history, sessionId);
      setMessages(m => [...m, { role: 'assistant', content: answer }]);
    } catch (err) {
      setMessages(m => [...m, { role: 'assistant', content: friendlyError(err, 'Sorry, I could not answer that just now. Please try again.') }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <aside className="drawer" role="dialog" aria-label={t('Ask about this job')}>
      <div className="drawer-head">
        <div style={{ flex: 1 }}>
          <h2>{t('Ask about this job')}</h2>
          <div className="small muted">{t('Answers are written by AI. Check before relying on them.')}</div>
        </div>
        <button type="button" className="icon-btn" aria-label={t('Close')} onClick={onClose}><X size={22} /></button>
      </div>

      <div className="drawer-body" aria-live="polite">
        {messages.length === 0 && (
          <>
            <p className="muted">{t('Ask anything about this cutting plan, the material or how to build it.')}</p>
            <div className="chips">
              {SUGGESTIONS.map(s => <button key={s} type="button" className="chip" style={{ fontSize: 14 }} onClick={() => send(s)}>{s}</button>)}
            </div>
          </>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role === 'user' ? 'msg-user' : 'msg-bot'}`}>
            {m.role === 'user' ? m.content : <ReactMarkdown>{m.content}</ReactMarkdown>}
          </div>
        ))}
        {sending && <div className="msg msg-bot"><LoaderCircle size={18} className="spinner" /></div>}
        <div ref={endRef} />
      </div>

      <form className="drawer-foot" onSubmit={e => { e.preventDefault(); send(input); }}>
        <input ref={inputRef} className="input" placeholder={t('Type your question')} aria-label={t('Your question')} value={input} onChange={e => setInput(e.target.value)} />
        <button type="submit" className="btn btn-primary" disabled={!input.trim() || sending} aria-label={t('Send')}><Send size={20} /></button>
      </form>
    </aside>
  );
}
