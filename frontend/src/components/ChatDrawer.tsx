import { useEffect, useRef, useState } from 'react';
import { t } from '../i18n';
import ReactMarkdown from 'react-markdown';
import { Check, LoaderCircle, Send, Sparkles, X } from 'lucide-react';
import { friendlyError } from '../api';
import type { AssistantAnswer, AssistantProposal } from '../types';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  proposals?: AssistantProposal[];
}

interface Props {
  /** Sends one question with the conversation so far. */
  ask: (question: string, history: { role: string; content: string }[]) => Promise<AssistantAnswer>;
  /** Saves a proposed change. Without it, proposals are not offered. */
  onApply?: (proposal: AssistantProposal) => void;
  suggestions?: string[];
  onClose: () => void;
}

const DEFAULT_SUGGESTIONS = [
  'How many sheets for 3 of these?',
  'Which edges should get edge banding?',
  'What hardware do I need?',
];

export default function ChatDrawer({ ask, onApply, suggestions = DEFAULT_SUGGESTIONS, onClose }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [applied, setApplied] = useState<Set<string>>(new Set());
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
      const answer = await ask(question, history);
      setMessages(m => [...m, { role: 'assistant', content: answer.reply, proposals: answer.proposals }]);
    } catch (err) {
      setMessages(m => [...m, { role: 'assistant', content: friendlyError(err, 'Sorry, I could not answer that just now. Please try again.') }]);
    } finally {
      setSending(false);
    }
  };

  const apply = (key: string, proposal: AssistantProposal) => {
    if (!onApply || applied.has(key)) return;
    setApplied(prev => new Set(prev).add(key));
    onApply(proposal);
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
            <p className="muted">
              {onApply
                ? t('Ask about this plan, or ask for a change. You approve every change before it is made.')
                : t('Ask anything about this cutting plan, the material or how to build it.')}
            </p>
            <div className="chips">
              {suggestions.map(s => <button key={s} type="button" className="chip" style={{ fontSize: 14 }} onClick={() => send(t(s))}>{t(s)}</button>)}
            </div>
          </>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role === 'user' ? 'msg-user' : 'msg-bot'}`}>
            {m.role === 'user' ? m.content : <ReactMarkdown>{m.content}</ReactMarkdown>}
            {onApply && m.proposals?.map((p, j) => {
              const key = `${i}-${j}`;
              const done = applied.has(key);
              return (
                <div key={key} className="proposal">
                  <div className="proposal-title"><Sparkles size={16} /> {p.title}</div>
                  <div className="small muted">
                    {p.type === 'overrides'
                      ? t('The cutting plan will be made again with this change.')
                      : t('Saves the quote. Your customer sees only the total.')}
                  </div>
                  <button type="button" className="btn btn-primary btn-block" disabled={done} onClick={() => apply(key, p)}>
                    {done ? <><Check size={18} /> {t('Applied')}</> : t('Apply this change')}
                  </button>
                </div>
              );
            })}
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
