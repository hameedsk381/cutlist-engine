import { useState } from 'react';
import { t } from '../i18n';
import { ArrowRight, ChevronLeft, Plus, Printer, TriangleAlert, X } from 'lucide-react';
import { friendlyError, linearNest } from '../api';
import type { LinearPlan } from '../types';

interface Row { label: string; length: string; quantity: string; }

const STOCKS = [
  { label: '8 ft', mm: 2440 },
  { label: '10 ft', mm: 3050 },
  { label: '12 ft', mm: 3660 },
  { label: '6 m', mm: 6000 },
];
const COLORS = ['#cfe8e3', '#f6dfb8', '#d9d4f0', '#f3cfd6', '#cfe0f5', '#dcebc4'];

export default function LinearView({ onBack }: { onBack: () => void }) {
  const [rows, setRows] = useState<Row[]>([{ label: '', length: '', quantity: '1' }]);
  const [stock, setStock] = useState(3050);
  const [customStock, setCustomStock] = useState(false);
  const [kerf, setKerf] = useState(3);
  const [cost, setCost] = useState(0);
  const [leftovers, setLeftovers] = useState('');
  const [plan, setPlan] = useState<LinearPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const update = (i: number, patch: Partial<Row>) => setRows(r => r.map((row, k) => (k === i ? { ...row, ...patch } : row)));
  const valid = rows.filter(r => parseFloat(r.length) > 0 && parseInt(r.quantity, 10) > 0);
  const ready = valid.length > 0 && stock > 0;

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await linearNest({
        pieces: valid.map((r, i) => ({ label: r.label.trim() || `Piece ${i + 1}`, length: parseFloat(r.length), quantity: parseInt(r.quantity, 10) })),
        stock_length: stock,
        kerf,
        stock_cost: cost,
        leftovers: leftovers.split(/[,\s]+/).map(parseFloat).filter(v => v > 0),
      });
      setPlan(result);
    } catch (err) {
      setPlan(null);
      setError(friendlyError(err, 'We could not work out the cuts. Check the lengths and try again.'));
    } finally {
      setBusy(false);
    }
  };

  const labels = plan ? [...new Set(plan.bars.flatMap(b => b.cuts.map(c => c.label)))] : [];
  const colorOf = (label: string) => COLORS[labels.indexOf(label) % COLORS.length];
  const money = (v: number) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v);

  return (
    <main className="page">
      <button type="button" className="btn btn-ghost no-print" onClick={onBack}><ChevronLeft size={20} /> {t('Your projects')}</button>
      <div className="page-head">
        <h1>{t('Cut lengths')}</h1>
        <p className="lead">{t('For timber, beading, pipe and profiles. List the lengths you need and we fit them onto the fewest bars.')}</p>
      </div>

      <div className="result-grid">
        <section className="card stack no-print" aria-label={t('What to cut')}>
          <h2>{t('Pieces you need')}</h2>
          <div className="stack" style={{ gap: 8 }}>
            {rows.map((row, i) => (
              <div key={i} className="linear-row">
                <input className="input" placeholder="Name (optional)" aria-label={`Name of piece ${i + 1}`} value={row.label} onChange={e => update(i, { label: e.target.value })} />
                <input className="input num" type="number" inputMode="decimal" min={1} placeholder={t('Length mm')} aria-label={`Length of piece ${i + 1} in mm`} value={row.length} onChange={e => update(i, { length: e.target.value })} />
                <input className="input num" type="number" inputMode="numeric" min={1} placeholder={t('Qty')} aria-label={`Quantity of piece ${i + 1}`} value={row.quantity} onChange={e => update(i, { quantity: e.target.value })} />
                <button type="button" className="icon-btn" aria-label={`Remove piece ${i + 1}`} disabled={rows.length === 1} onClick={() => setRows(r => r.filter((_, k) => k !== i))}><X size={20} /></button>
              </div>
            ))}
          </div>
          <button type="button" className="btn" onClick={() => setRows(r => [...r, { label: '', length: '', quantity: '1' }])}><Plus size={18} /> {t('Add another piece')}</button>

          <div className="field">
            <span className="field-label" id="stock-label">{t('Length of one bar')}</span>
            <div className="chips" role="group" aria-labelledby="stock-label">
              {STOCKS.map(s => (
                <button key={s.mm} type="button" className="chip" aria-pressed={!customStock && stock === s.mm} onClick={() => { setCustomStock(false); setStock(s.mm); }}>
                  {s.label} <small>{s.mm}</small>
                </button>
              ))}
              <button type="button" className="chip" aria-pressed={customStock} onClick={() => setCustomStock(true)}>{t('Other')}</button>
            </div>
            {customStock && (
              <div className="input-row">
                <input className="input num" type="number" inputMode="numeric" min={1} aria-label={t('Bar length in mm')} value={stock || ''} onChange={e => setStock(parseFloat(e.target.value) || 0)} />
                <span className="input-affix">mm</span>
              </div>
            )}
          </div>
          <div className="quote-grid">
            <div className="field">
              <label htmlFor="l-kerf">{t('Blade thickness')}</label>
              <div className="input-row"><input id="l-kerf" className="input num" type="number" min={0} step={0.5} value={kerf} onChange={e => setKerf(parseFloat(e.target.value) || 0)} /><span className="input-affix">mm</span></div>
            </div>
            <div className="field">
              <label htmlFor="l-cost">{t('Price of one bar')}</label>
              <div className="input-row"><span className="input-affix">₹</span><input id="l-cost" className="input num" type="number" min={0} value={cost || ''} onChange={e => setCost(parseFloat(e.target.value) || 0)} /></div>
            </div>
          </div>
          <div className="field">
            <label htmlFor="l-left">{t('Leftover lengths you already have')}</label>
            <input id="l-left" className="input" placeholder="Example: 800, 1250" value={leftovers} onChange={e => setLeftovers(e.target.value)} />
            <span className="field-help">{t('In mm, separated by commas. These are used first and cost nothing.')}</span>
          </div>
          {error && <div className="notice notice-danger" role="alert"><TriangleAlert size={20} /><div>{error}</div></div>}
          <button type="button" className="btn btn-primary btn-lg" disabled={!ready || busy} onClick={run}>
            {t('Work out the cuts')} <ArrowRight size={22} />
          </button>
        </section>

        <section className="stack" aria-label={t('Cutting plan')} aria-live="polite">
          {!plan ? (
            <div className="card muted">{t('Your cutting plan will appear here.')}</div>
          ) : (
            <>
              <div className="stats">
                <div className="stat"><div className="stat-label">{t('Bars to buy')}</div><div className="stat-value num">{plan.new_bar_count}</div>
                  {plan.leftover_bar_count > 0 && <div className="stat-sub">plus {plan.leftover_bar_count} of your leftovers</div>}</div>
                <div className="stat"><div className="stat-label">{t('Waste')}</div><div className="stat-value num">{Math.round(plan.waste_percent)}%</div></div>
                {plan.total_cost > 0 && <div className="stat"><div className="stat-label">{t('Cost')}</div><div className="stat-value num">{money(plan.total_cost)}</div></div>}
              </div>
              <div className="card stack">
                <div className="card-title"><h2>{t('How to cut each bar')}</h2><span className="spacer" />
                  <button type="button" className="btn no-print" onClick={() => window.print()}><Printer size={18} /> {t('Print')}</button></div>
                {plan.bars.map(bar => (
                  <div key={bar.bar_id}>
                    <div className="small"><strong>Bar {bar.bar_id}</strong> · {bar.stock_length} mm{bar.is_leftover ? ' · your leftover' : ''} · {Math.round(bar.remaining)} mm left</div>
                    <div className="bar" role="img" aria-label={`Bar ${bar.bar_id}: ${bar.cuts.map(c => `${c.label} ${c.length}`).join(', ')}`}>
                      {bar.cuts.map((cut, i) => (
                        <div key={i} className="bar-cut" style={{ width: `${(cut.length / bar.stock_length) * 100}%`, background: colorOf(cut.label) }} title={`${cut.label} — ${cut.length} mm`}>
                          <span>{cut.length}</span>
                        </div>
                      ))}
                    </div>
                    <div className="small muted">{bar.cuts.map(c => `${c.label} ${c.length}`).join(' · ')}</div>
                  </div>
                ))}
                {plan.reusable_leftovers.length > 0 && (
                  <p className="small">{t('Leftovers worth keeping:')} <strong className="num">{plan.reusable_leftovers.join(', ')} mm</strong></p>
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
