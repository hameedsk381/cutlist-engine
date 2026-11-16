import { useMemo, useState } from 'react';
import { ArrowRight, ChevronRight, CircleCheck, Info, Search, TriangleAlert } from 'lucide-react';
import { tidyName } from '../format';
import type { Board, ExtractResult, ProcessConfig, ReviewDecisions } from '../types';

interface Props {
  data: ExtractResult;
  config: ProcessConfig;
  decisions: ReviewDecisions;
  onChange: (next: ReviewDecisions) => void;
  onContinue: () => void;
  error: string | null;
  busy: boolean;
  designNotes?: string[];
}

/** Engine warnings rewritten in workshop language. `check` means look before cutting. */
function explain(board: Board): { text: string; check: boolean }[] {
  const notes: { text: string; check: boolean }[] = [];
  for (const w of board.warnings) {
    if (w.includes('Non-rectangular')) notes.push({ text: 'Not a plain rectangle. It will be cut to its real shape.', check: false });
    else if (w.includes('interior cutout')) notes.push({ text: 'Has a cut-out inside.', check: false });
    else if (w.includes('not a standard sheet thickness')) notes.push({ text: `${board.thickness} mm is not a usual sheet thickness. Check the drawing.`, check: true });
    else if (w.includes('differ in area')) notes.push({ text: 'The two faces are not the same (groove, rebate or pocket). Check the size.', check: true });
    else if (w.includes('laterally offset')) notes.push({ text: 'The two faces do not line up. Check the size.', check: true });
    else notes.push({ text: w, check: true });
  }
  if (Math.min(board.length, board.width) < 50) {
    return [{ text: 'Smaller than 50 mm, so probably hardware and not a board. Left out unless you switch it on.', check: true }];
  }
  if (board.confidence < 0.8 && !notes.some(n => n.check)) {
    notes.push({ text: 'We are not fully sure about this part. Check the size.', check: true });
  }
  return notes;
}

function Thumb({ board }: { board: Board }) {
  const xs = board.contour.map(p => p[0]);
  const ys = board.contour.map(p => p[1]);
  const w = Math.max(...xs) - Math.min(...xs) || 1;
  const h = Math.max(...ys) - Math.min(...ys) || 1;
  const pad = Math.max(w, h) * 0.08;
  const path = (pts: [number, number][]) => pts.map((p, i) => `${i ? 'L' : 'M'}${p[0]} ${p[1]}`).join(' ') + ' Z';
  const d = [path(board.contour), ...(board.holes || []).map(path)].join(' ');
  return (
    <svg viewBox={`${-pad} ${-pad} ${w + pad * 2} ${h + pad * 2}`} width="68" height="68" role="img" aria-label="Part shape">
      <path d={d} fill="var(--wood)" stroke="var(--part-line)" strokeWidth={Math.max(w, h) / 40} fillRule="evenodd" strokeLinejoin="round" />
    </svg>
  );
}

export default function ReviewView({ data, config, decisions, onChange, onContinue, error, busy, designNotes = [] }: Props) {
  const [query, setQuery] = useState('');

  const annotated = useMemo(
    () => data.boards.map(board => {
      const notes = explain(board);
      return { board, notes, needsLook: notes.some(n => n.check) };
    }),
    [data.boards],
  );

  const included = data.boards.filter(b => decisions[b.id]?.accepted !== false).length;
  const toCheck = annotated.filter(a => a.needsLook);
  const skipped = data.extraction_report.skipped_parts || [];
  const guessed = data.extraction_report.inferred_board_count || 0;

  const nameOf = (b: Board) => decisions[b.id]?.rename || tidyName(b.label || b.id);
  const update = (id: string, patch: Partial<ReviewDecisions[string]>) => {
    const current = decisions[id] || { accepted: true, rename: '', reason: '' };
    onChange({ ...decisions, [id]: { ...current, ...patch } });
  };
  const includeAll = () => {
    const next: ReviewDecisions = {};
    data.boards.forEach(b => { next[b.id] = { ...(decisions[b.id] || { rename: '', reason: '' }), accepted: true }; });
    onChange(next);
  };

  const q = query.trim().toLowerCase();
  const visible = annotated
    .filter(a => !q || nameOf(a.board).toLowerCase().includes(q) || `${Math.round(a.board.length)} ${Math.round(a.board.width)}`.includes(q))
    .sort((a, b) => Number(b.needsLook) - Number(a.needsLook));

  if (data.boards.length === 0) {
    return (
      <main className="page page-narrow fade-in">
        <div className="page-head">
          <h1>We could not find any boards</h1>
          <p className="lead">The file opened, but nothing in it looks like a flat board with thickness.</p>
        </div>
        <div className="notice notice-warn">
          <TriangleAlert size={20} />
          <div>
            <strong>How to fix the design</strong>
            <ul>
              <li>Draw every board as a solid with its real thickness, not a flat face.</li>
              <li>Make each board its own group or component.</li>
              <li>Export in millimetres.</li>
            </ul>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="page fade-in">
      <div className="page-head">
        <h1>We found {data.boards.length} {data.boards.length === 1 ? 'part' : 'parts'}</h1>
        <p className="lead">Check the sizes match your design. Rename a part by tapping its name. Switch off anything you do not want cut.</p>
      </div>

      <div className="stack">
        {designNotes.length > 0 && (
          <div className="notice notice-info">
            <Info size={22} />
            <div>
              <strong>How these sizes were worked out</strong>
              <ul>{designNotes.map((n, i) => <li key={i}>{n}</li>)}</ul>
            </div>
          </div>
        )}

        {toCheck.length === 0 ? (
          <div className="notice notice-ok"><CircleCheck size={22} /><div><strong>Every part was measured cleanly.</strong> A quick look at the sizes is still a good idea.</div></div>
        ) : (
          <div className="notice notice-warn"><TriangleAlert size={22} /><div><strong>{toCheck.length} {toCheck.length === 1 ? 'part needs' : 'parts need'} a look.</strong> They are shown first, with the reason.</div></div>
        )}

        {guessed > 0 && (
          <div className="notice notice-warn">
            <TriangleAlert size={22} />
            <div><strong>{guessed} {guessed === 1 ? 'part was' : 'parts were'} worked out from loose faces.</strong> The design did not have them as closed solid boards, so please check their sizes carefully.</div>
          </div>
        )}

        {skipped.length > 0 && (
          <details className="more">
            <summary><ChevronRight size={18} /> {skipped.length} {skipped.length === 1 ? 'item was' : 'items were'} left out because they are not flat boards</summary>
            <div className="notice notice-info" style={{ marginTop: 8 }}>
              <Info size={20} />
              <div>
                Usually handles, legs or decoration. If one of these is a real board, fix it in the design and upload again.
                <ul>{skipped.map((s, i) => <li key={i}>{s}</li>)}</ul>
              </div>
            </div>
          </details>
        )}

        {data.boards.length > 12 && (
          <div className="input-row" style={{ maxWidth: 420 }}>
            <Search size={20} color="var(--text-2)" />
            <input className="input" style={{ maxWidth: 'none' }} type="search" placeholder="Find a part by name or size" aria-label="Find a part" value={query} onChange={e => setQuery(e.target.value)} />
          </div>
        )}

        <div className="parts-grid">
          {visible.map(({ board, notes, needsLook }) => {
            const on = decisions[board.id]?.accepted !== false;
            const otherThickness = Math.abs(board.thickness - config.thickness) > 0.5;
            return (
              <article key={board.id} className={`part-card ${needsLook && on ? 'needs-look' : ''} ${on ? '' : 'is-off'}`}>
                <div className="part-thumb"><Thumb board={board} /></div>
                <div style={{ minWidth: 0 }}>
                  <input
                    className="part-name" aria-label={`Name of ${nameOf(board)}`}
                    value={nameOf(board)} onChange={e => update(board.id, { rename: e.target.value })}
                  />
                  <div className="part-size num">
                    {Math.round(board.length)} × {Math.round(board.width)} <small>mm</small>
                  </div>
                  <div className="small muted">{board.thickness} mm thick</div>
                </div>

                {notes.length > 0 && (
                  <ul className="part-notes" style={needsLook ? undefined : { color: 'var(--text-2)' }}>
                    {notes.map((n, i) => <li key={i}>{n.text}</li>)}
                  </ul>
                )}

                <div className="part-foot">
                  {needsLook
                    ? <span className="tag tag-warn"><TriangleAlert size={14} /> Please check</span>
                    : <span className="tag tag-ok"><CircleCheck size={14} /> Looks right</span>}
                  {otherThickness && <span className="tag tag-muted">Separate {board.thickness} mm sheet</span>}
                  <span className="spacer" />
                  <label className="switch">
                    <input type="checkbox" checked={on} onChange={e => update(board.id, { accepted: e.target.checked })} />
                    <span className="switch-track" aria-hidden="true" />
                    {on ? 'Cut this' : 'Left out'}
                  </label>
                </div>
              </article>
            );
          })}
        </div>
        {visible.length === 0 && <p className="muted">No part matches "{query}".</p>}

        {error && <div className="notice notice-danger" role="alert"><TriangleAlert size={20} /><div>{error}</div></div>}
      </div>

      <div className="actionbar">
        <div className="actionbar-inner">
          <span>
            <strong className="num">{included} of {data.boards.length}</strong> parts will be cut
          </span>
          {included < data.boards.length && (
            <button type="button" className="btn btn-ghost" onClick={includeAll}>Include all</button>
          )}
          <button type="button" className="btn btn-primary btn-lg" disabled={included === 0 || busy} onClick={onContinue}>
            Make cutting plan <ArrowRight size={22} />
          </button>
        </div>
      </div>
    </main>
  );
}
