import { useMemo, useState } from 'react';
import { t, tf } from '../i18n';
import { ChevronRight, Receipt, Ruler } from 'lucide-react';
import { tidyName } from '../format';
import type { PartOverrides, ProcessResult, QuoteInput, QuoteTotals } from '../types';

type Choice = 'none' | 'front' | 'long' | 'all';

const CHOICES: { value: Choice; label: string }[] = [
  { value: 'none', label: 'No tape' },
  { value: 'front', label: 'Front edge' },
  { value: 'long', label: 'Both long edges' },
  { value: 'all', label: 'All 4 edges' },
];
const TAPES = [0.5, 1, 2];

/** [top, right, bottom, left]: top/bottom are the short edges, left/right the long ones. */
function toBand(choice: Choice, t: number): number[] {
  if (choice === 'front') return [0, 0, 0, t];
  if (choice === 'long') return [0, t, 0, t];
  if (choice === 'all') return [t, t, t, t];
  return [0, 0, 0, 0];
}

function fromBand(band: number[] | undefined): Choice {
  if (!band || !band.some(v => v > 0)) return 'none';
  const [top, right, bottom, left] = band;
  if (top > 0 && bottom > 0 && left > 0 && right > 0) return 'all';
  if (left > 0 && right > 0) return 'long';
  return 'front';
}

interface BandingProps {
  result: ProcessResult;
  onApply: (overrides: PartOverrides) => void;
  busy: boolean;
}

export function EdgeBandingCard({ result, onApply, busy }: BandingProps) {
  const boards = useMemo(() => Object.fromEntries(result.boards.map(b => [b.id, b])), [result.boards]);
  const rows = useMemo(
    () => result.cutlist.map(item => {
      const ids = item.board_ids || [];
      const band = boards[ids[0]]?.edge_band;
      return {
        key: item.id,
        ids,
        label: [...new Set((item.labels || []).map(tidyName))].join(', ') || item.id,
        size: `${Math.round(item.finished_length || item.length)} × ${Math.round(item.finished_width || item.width)}`,
        quantity: item.quantity,
        saved: fromBand(band),
      };
    }),
    [result.cutlist, boards],
  );
  const savedTape = useMemo(() => {
    const all = result.boards.flatMap(b => b.edge_band || []).filter(v => v > 0);
    return all.length ? Math.max(...all) : 2;
  }, [result.boards]);

  const [tape, setTape] = useState(savedTape);
  const [choices, setChoices] = useState<Record<string, Choice>>(() => Object.fromEntries(rows.map(r => [r.key, r.saved])));

  const dirty = tape !== savedTape ? rows.some(r => choices[r.key] !== 'none') : rows.some(r => choices[r.key] !== r.saved);
  const setAll = (choice: Choice) => setChoices(Object.fromEntries(rows.map(r => [r.key, choice])));
  const apply = () => {
    const overrides: PartOverrides = {};
    rows.forEach(r => {
      const choice = choices[r.key];
      if (choice !== 'none') r.ids.forEach(id => { overrides[id] = { edge_band: toBand(choice, tape) }; });
    });
    onApply(overrides);
  };
  const banding = result.edge_banding;
  const [open, setOpen] = useState(!!banding && banding.total_m > 0);

  return (
    <details className="more card" open={open} onToggle={e => setOpen(e.currentTarget.open)}>
      <summary><Ruler size={18} /> {t('Edge banding')}{banding && banding.total_m > 0 ? ` · ${tf('{metres} m of tape', { metres: banding.total_m })}` : ''}</summary>
      <div className="stack" style={{ marginTop: 8 }}>
        <p className="small muted">
          {t('Choose which edges get tape. Taped parts are cut smaller by the tape thickness, so they finish at the right size.')}
        </p>
        <div className="field">
          <span className="field-label" id="tape-label">{t('Tape thickness')}</span>
          <div className="chips" role="group" aria-labelledby="tape-label">
            {TAPES.map(t => (
              <button key={t} type="button" className="chip" aria-pressed={tape === t} onClick={() => setTape(t)}>{t} mm</button>
            ))}
          </div>
        </div>
        <div className="row">
          <button type="button" className="btn btn-ghost" onClick={() => setAll('front')}>{t('Front edge on all')}</button>
          <button type="button" className="btn btn-ghost" onClick={() => setAll('none')}>{t('Clear all')}</button>
        </div>
        <div className="band-list">
          {rows.map(r => (
            <label key={r.key} className="band-row">
              <span>
                <strong>{r.quantity} × {r.label}</strong>
                <span className="small muted num"> {r.size}</span>
              </span>
              <select
                className="input" value={choices[r.key]}
                onChange={e => setChoices(c => ({ ...c, [r.key]: e.target.value as Choice }))}
              >
                {CHOICES.map(c => <option key={c.value} value={c.value}>{t(c.label)}</option>)}
              </select>
            </label>
          ))}
        </div>
        {banding && banding.total_m > 0 && (
          <p className="small">
            <strong className="num">{tf('{metres} m of tape needed', { metres: banding.total_m })}</strong>
            {banding.by_thickness.length > 1 && ` (${banding.by_thickness.map(b => `${b.metres} m of ${b.thickness} mm`).join(', ')})`}.
            {' '}{t('Buy about 10% extra for trimming.')}
          </p>
        )}
        <button type="button" className="btn btn-primary btn-block" disabled={!dirty || busy} onClick={apply}>
          {t('Update the cutting plan')}
        </button>
      </div>
    </details>
  );
}

interface QuoteProps {
  result: ProcessResult;
  saved: QuoteInput | null;
  totals: QuoteTotals | null;
  onSave: (quote: QuoteInput | null) => void;
  busy: boolean;
}

const EMPTY: QuoteInput = { labour: 0, hardware: 0, other: 0, edge_band_rate: 0, margin_percent: 0, customer: '', note: '' };

export function QuoteCard({ result, saved, totals, onSave, busy }: QuoteProps) {
  const [quote, setQuote] = useState<QuoteInput>(saved || EMPTY);
  const [open, setOpen] = useState(!!totals);
  const currency = result.material_summary.currency || 'INR';
  const money = (v: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(v);

  const material = result.material_summary.total_material_cost;
  const tapeM = result.edge_banding?.total_m || 0;
  const tape = tapeM * quote.edge_band_rate;
  const subtotal = material + tape + quote.labour + quote.hardware + quote.other;
  const total = subtotal * (1 + quote.margin_percent / 100);
  const num = (v: string) => { const n = parseFloat(v); return Number.isFinite(n) && n >= 0 ? n : 0; };
  const set = (patch: Partial<QuoteInput>) => setQuote(q => ({ ...q, ...patch }));

  const amount = (id: string, label: string, key: 'labour' | 'hardware' | 'other' | 'edge_band_rate', affix = '₹') => (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="input-row">
        <span className="input-affix">{affix}</span>
        <input id={id} className="input num" type="number" inputMode="decimal" min={0} value={quote[key] || ''} onChange={e => set({ [key]: num(e.target.value) })} />
      </div>
    </div>
  );

  return (
    <details className="more card" open={open} onToggle={e => setOpen(e.currentTarget.open)}>
      <summary><Receipt size={18} /> {t('Quote for your customer')}{totals ? ` · ${money(totals.total)}` : ''}</summary>
      <div className="stack" style={{ marginTop: 8 }}>
        <p className="small muted">{t('Your customer sees only the total on the shared link, never your costs or margin.')}</p>
        <div className="quote-grid">
          {amount('q-labour', 'Labour', 'labour')}
          {amount('q-hardware', 'Hardware', 'hardware')}
          {amount('q-other', 'Other costs', 'other')}
          {amount('q-tape', 'Tape price per metre', 'edge_band_rate')}
          <div className="field">
            <label htmlFor="q-margin">{t('Your margin')}</label>
            <div className="input-row">
              <input id="q-margin" className="input num" type="number" inputMode="decimal" min={0} max={500} value={quote.margin_percent || ''} onChange={e => set({ margin_percent: num(e.target.value) })} />
              <span className="input-affix">%</span>
            </div>
          </div>
        </div>
        <div className="field">
          <label htmlFor="q-customer">{t('Customer name')}</label>
          <input id="q-customer" className="input" maxLength={120} value={quote.customer} onChange={e => set({ customer: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="q-note">{t('Note on the quote')}</label>
          <input id="q-note" className="input" maxLength={500} placeholder={t('Example: Price valid for 15 days')} value={quote.note} onChange={e => set({ note: e.target.value })} />
        </div>

        <table className="cut quote-lines">
          <tbody>
            <tr><td>Material ({result.material_summary.sheet_count} sheets)</td><td className="num">{money(material)}</td></tr>
            {tape > 0 && <tr><td>Edge banding ({tapeM} m)</td><td className="num">{money(tape)}</td></tr>}
            {quote.labour > 0 && <tr><td>{t('Labour')}</td><td className="num">{money(quote.labour)}</td></tr>}
            {quote.hardware > 0 && <tr><td>{t('Hardware')}</td><td className="num">{money(quote.hardware)}</td></tr>}
            {quote.other > 0 && <tr><td>{t('Other')}</td><td className="num">{money(quote.other)}</td></tr>}
            {quote.margin_percent > 0 && <tr><td>Margin ({quote.margin_percent}%)</td><td className="num">{money(total - subtotal)}</td></tr>}
            <tr className="quote-total"><td><strong>{t('Quote total')}</strong></td><td className="num"><strong>{money(total)}</strong></td></tr>
          </tbody>
        </table>

        <div className="row">
          <button type="button" className="btn btn-primary" style={{ flex: 1 }} disabled={busy} onClick={() => onSave(quote)}>
            {t('Save quote')} <ChevronRight size={18} />
          </button>
          {saved && <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => { setQuote(EMPTY); onSave(null); }}>{t('Remove')}</button>}
        </div>
        {totals && <p className="small muted">{t('Saved. Share the project link to send it.')}</p>}
      </div>
    </details>
  );
}
