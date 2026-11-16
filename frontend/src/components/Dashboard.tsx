import { useMemo, useState } from 'react';
import { t, tf } from '../i18n';
import type { ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  ArrowLeft, ChevronRight, CircleCheck, Cpu, Download, FileText, Lightbulb, Printer, Tag, TriangleAlert,
} from 'lucide-react';
import SheetLayout from './SheetLayout';
import CutSteps from './CutSteps';
import { tidyName } from '../format';
import { saveArtifact } from '../api';
import type { FinalizeResult, ProcessResult, Sheet } from '../types';

interface Props {
  result: ProcessResult;
  finalized: FinalizeResult | null;
  designNotes?: string[];
  /** Extra cards (edge banding, quote) shown above the downloads. */
  tools?: ReactNode;
  onBackToParts?: () => void;
  onForce: () => void;
  error: string | null;
}

/** Engine findings rewritten in workshop language; null hides one the user has already dealt with. */
function plain(issue: string): string | null {
  if (issue.startsWith('No structural')) return null;
  if (issue.includes('micro-parts')) return null;
  const sheets = issue.match(/own sheets \(([^)]+)\)/);
  if (sheets) return `Parts in another thickness (${sheets[1].replace(/mm/g, ' mm')}) are on their own sheets, priced the same as the main sheet. The real cost may be lower.`;
  if (issue.includes('not flat panels')) return 'Some items in the design are not flat boards (handles, legs, decoration) and are not in this plan.';
  if (issue.includes('inferred by pairing')) return 'Some parts were worked out from loose faces, not solid boards. Measure them before cutting.';
  if (issue.includes('confidence')) return 'We could not measure every part cleanly, so some sizes may be wrong.';
  if (issue.includes('could not be paired')) return 'Some faces in the design do not belong to any solid board.';
  if (issue.includes('No manufacturable boards')) return 'No boards are left to cut.';
  return issue;
}

export default function Dashboard({ result, finalized, designNotes = [], tools, onBackToParts, onForce, error }: Props) {
  const [sheetIndex, setSheetIndexRaw] = useState(0);
  const [showCuts, setShowCuts] = useState(false);
  const [activeCut, setActiveCut] = useState<number | null>(null);
  const setSheetIndex = (i: number) => { setSheetIndexRaw(i); setActiveCut(null); };
  const [activeIds, setActiveIds] = useState<Set<string>>(new Set());

  const boards = useMemo(() => Object.fromEntries(result.boards.map(b => [b.id, b])), [result.boards]);
  const names = useMemo(
    () => Object.fromEntries(result.boards.map(b => [b.id, tidyName(b.label || b.id)])),
    [result.boards],
  );
  const numbers = useMemo(
    () => Object.fromEntries(result.cutlist.flatMap((item, i) => (item.board_ids || []).map(id => [id, i + 1]))),
    [result.cutlist],
  );
  const summary = result.material_summary;
  const sheets = result.sheets;
  const money = (v: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: summary.currency || 'INR', maximumFractionDigits: 0 }).format(v);

  const thicknessOf = (sheet: Sheet) => boards[sheet.parts[0]?.board_id]?.thickness;
  const sheetName = (sheet: Sheet) => {
    const t = thicknessOf(sheet);
    const base = `Sheet ${sheet.sheet_id}${t ? ` · ${t} mm` : ''}`;
    return sheet.is_offcut_stock ? `${base} · offcut` : base;
  };
  const byThickness = useMemo(() => {
    const counts = new Map<number, number>();
    sheets.forEach(s => { const t = thicknessOf(s) ?? 0; counts.set(t, (counts.get(t) || 0) + 1); });
    return [...counts.entries()].sort((a, b) => b[0] - a[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheets, boards]);
  const offcutSheets = sheets.filter(s => s.is_offcut_stock);

  const selectBoards = (ids: string[]) => {
    setActiveIds(new Set(ids));
    const at = sheets.findIndex(s => s.parts.some(p => ids.includes(p.board_id)));
    if (at >= 0) setSheetIndex(at);
  };

  const fix = result.model_fix_report;
  const findings = (fix?.issues || []).map(plain).filter((x): x is string => !!x);
  const advice = result.ai_advice && !result.ai_advice.includes('temporarily unavailable') ? result.ai_advice : null;

  /* ---------- Blocked: the design needs fixing first ---------- */
  if (finalized?.gated) {
    return (
      <main className="page page-narrow fade-in">
        <div className="page-head">
          <h1>{t('This design is not ready to cut')}</h1>
          <p className="lead">{t('We stopped before making a plan, because the sizes we read may be wrong. Cutting from it could waste sheets.')}</p>
        </div>
        <div className="stack">
          <div className="notice notice-warn">
            <TriangleAlert size={22} />
            <div>
              <strong>{t('What we found')}</strong>
              <ul>{findings.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </div>
          </div>
          {fix && fix.recommendations.length > 0 && (
            <div className="notice notice-info">
              <Lightbulb size={22} />
              <div>
                <strong>{t('How to fix it')}</strong>
                <ul>{fix.recommendations.map((s, i) => <li key={i}>{s}</li>)}</ul>
              </div>
            </div>
          )}
          {error && <div className="notice notice-danger" role="alert"><TriangleAlert size={20} /><div>{error}</div></div>}
          <div className="row">
            {onBackToParts && (
              <button type="button" className="btn btn-primary btn-lg" onClick={onBackToParts}><ArrowLeft size={20} /> {t('Back to the parts')}</button>
            )}
            <button
              type="button" className="btn btn-danger"
              onClick={() => window.confirm('Make the plan anyway? Only do this if you have checked every part size yourself.') && onForce()}
            >
              {t('I have checked the sizes, make the plan anyway')}
            </button>
          </div>
        </div>
      </main>
    );
  }

  const sheet = sheets[Math.min(sheetIndex, sheets.length - 1)];
  const artifacts = finalized?.artifacts || [];
  const find = (name: string) => artifacts.find(a => a.name === name);
  const dxf = artifacts.filter(a => a.name.startsWith('dxf/'));
  const gcode = artifacts.filter(a => a.name.startsWith('gcode/'));
  const totalParts = result.cutlist.reduce((n, c) => n + c.quantity, 0);

  return (
    <main className="page fade-in">
      <div className="page-head row">
        <div style={{ flex: 1, minWidth: 260 }}>
          <h1>{t('Your cutting plan')}</h1>
          <p className="lead">
            {tf('{parts} parts on {sheets} sheets. Tap a part in the list to find it on the sheet.', { parts: totalParts, sheets: summary.sheet_count })}
          </p>
        </div>
        <div className="row no-print">
          {onBackToParts && <button type="button" className="btn" onClick={onBackToParts}><ArrowLeft size={20} /> {t('Change parts')}</button>}
          <button type="button" className="btn btn-primary" onClick={() => window.print()}><Printer size={20} /> {t('Print plan')}</button>
        </div>
      </div>

      <div className="stack">
        {designNotes.length > 0 && (
          <details className="more">
            <summary><ChevronRight size={18} /> {t('How these sizes were worked out')}</summary>
            <div className="notice notice-info" style={{ marginTop: 8 }}>
              <div><ul style={{ marginTop: 0 }}>{designNotes.map((n, i) => <li key={i}>{n}</li>)}</ul></div>
            </div>
          </details>
        )}
        {error && <div className="notice notice-danger" role="alert"><TriangleAlert size={20} /><div>{error}</div></div>}
        {offcutSheets.length > 0 && (
          <div className="notice notice-info" role="status">
            <CircleCheck size={20} />
            <div>
              <strong>{offcutSheets.length} {offcutSheets.length === 1 ? 'sheet is' : 'sheets are'} cut from your offcut shelf</strong> — those pieces were already in your shop, so they cost nothing. Only {Math.max(0, summary.sheet_count - offcutSheets.length)} fresh {summary.sheet_count - offcutSheets.length === 1 ? 'sheet was' : 'sheets were'} bought.
            </div>
          </div>
        )}

        <section className="stats" aria-label={t('Summary')}>
          <div className="stat">
            <div className="stat-label">{t('Sheets to buy')}</div>
            <div className="stat-value num">{summary.sheet_count}</div>
            <div className="stat-sub">
              {offcutSheets.length > 0
                ? `${byThickness.map(([t, n]) => `${n} × ${t} mm`).join(' · ')} · ${offcutSheets.length} from your shelf (free)`
                : byThickness.map(([t, n]) => `${n} × ${t} mm`).join(' · ')}
            </div>
          </div>
          <div className="stat">
            <div className="stat-label">{t('Material cost')}</div>
            <div className="stat-value num">{money(summary.total_material_cost)}</div>
            <div className="stat-sub">{t('at the sheet price you entered')}</div>
          </div>
          <div className="stat">
            <div className="stat-label">{t('Wood used')}</div>
            <div className="stat-value num">{Math.round(summary.utilization_percent)}%</div>
            <div className="stat-sub">{tf('{percent}% is left over', { percent: Math.round(summary.waste_percent) })}</div>
          </div>
          <div className="stat">
            <div className="stat-label">{t('Spare pieces worth keeping')}</div>
            <div className="stat-value num">{summary.reusable_offcut_area.toFixed(1)} m²</div>
            <div className="stat-sub">{t('shown hatched in green')}</div>
          </div>
        </section>

        <div className="result-grid">
          <div className="stack">
            {sheet && (
              <section className="card screen-only" aria-label={t('Sheet layout')}>
                {sheets.length > 1 && (
                  <div className="sheet-tabs chips" role="tablist" style={{ flexWrap: 'nowrap', marginBottom: 14 }}>
                    {sheets.map((s, i) => (
                      <button key={s.sheet_id} type="button" role="tab" aria-selected={i === sheetIndex} aria-pressed={i === sheetIndex} className="chip" style={{ flexShrink: 0 }} onClick={() => setSheetIndex(i)}>
                        {sheetName(s)}
                      </button>
                    ))}
                  </div>
                )}
                <div className="card-title">
                  <h2>{sheetName(sheet)}</h2>
                  <span className="tag tag-muted num">{Math.round(sheet.width)} × {Math.round(sheet.height)} mm</span>
                </div>
                <SheetLayout
                  sheet={sheet} activeIds={activeIds} onSelect={id => selectBoards([id])} names={names}
                  boards={boards} numbers={numbers} onSelectGroup={selectBoards}
                  cuts={showCuts || activeCut !== null ? sheet.cuts?.steps : undefined} activeCut={activeCut}
                />
                <div className="sheet-meta">
                  <span><span className="legend-swatch" style={{ background: 'hsl(205 58% 90%)', borderColor: 'hsl(205 40% 30%)' }} />{t('Part to cut')}</span>
                  <span><span className="legend-swatch" style={{ background: 'var(--ok-soft)', borderColor: 'var(--ok)' }} />{t('Spare piece worth keeping')}</span>
                  <span><span className="legend-swatch" style={{ background: 'var(--wood)' }} />{t('Waste')}</span>
                  <span className="num">{tf('{parts} parts · {percent}% used', { parts: sheet.parts.length, percent: Math.round(sheet.utilization_percent) })}</span>
                </div>
              </section>
            )}

            {sheet?.cuts && (
              <section className="card screen-only" aria-label={t('Cutting order')}>
                <div className="card-title">
                  <h2>{t('Cutting order')}</h2>
                  <span className="tag tag-muted num">{tf('{n} cuts', { n: sheet.cuts.steps.length })}</span>
                </div>
                <CutSteps
                  sheet={sheet} numbers={numbers} active={activeCut} onActive={setActiveCut}
                  showLines={showCuts} onShowLines={setShowCuts}
                />
              </section>
            )}

            {/* On paper every sheet is printed, one after another. */}
            <div className="only-print print-all-sheets">
              {sheets.map(s => (
                <div key={s.sheet_id} className="sheet-print">
                  <h2 style={{ marginBottom: 8 }}>{sheetName(s)} — {Math.round(s.width)} × {Math.round(s.height)} mm</h2>
                  <SheetLayout sheet={s} activeIds={new Set()} onSelect={() => {}} names={names} boards={boards} numbers={numbers} interactive={false} cuts={s.cuts?.steps} />
                  <CutSteps sheet={s} numbers={numbers} interactive={false} />
                </div>
              ))}
            </div>

            <section className="card" aria-label={t('Parts list')}>
              <div className="card-title"><h2>{t('Parts list')}</h2><span className="tag tag-muted num">{totalParts} parts</span></div>
              <div className="table-wrap">
                <table className="cut">
                  <thead>
                    <tr><th>#</th><th>{t('Qty')}</th><th>{t('Part')}</th><th>{t('Length')}</th><th>{t('Width')}</th><th>{t('Thick')}</th></tr>
                  </thead>
                  <tbody>
                    {result.cutlist.map((item, index) => {
                      const ids = item.board_ids || [];
                      const active = ids.some(id => activeIds.has(id));
                      const label = [...new Set((item.labels || []).map(tidyName))].join(', ') || item.id;
                      return (
                        <tr
                          key={item.id} className={active ? 'is-active' : ''} tabIndex={0}
                          onClick={() => selectBoards(ids)}
                          onKeyDown={e => { if (e.key === 'Enter') selectBoards(ids); }}
                        >
                          <td><span className="legend-num">{index + 1}</span></td>
                          <td className="qty num">{item.quantity} ×</td>
                          <td><strong>{label}</strong></td>
                          <td className="num">{Math.round(item.length)}</td>
                          <td className="num">{Math.round(item.width)}</td>
                          <td className="num">{item.thickness} mm</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <aside className="stack no-print">
            {tools}
            <section className="card" aria-label={t('Downloads')}>
              <div className="card-title"><h2>{t('Take it to the workshop')}</h2></div>
              <div className="dl-list">
                <button type="button" className="dl" onClick={() => window.print()}>
                  <span className="dl-icon"><Printer size={20} /></span>
                  <span><strong>{t('Print the cutting plan')}</strong><span>{t('Every sheet and the parts list')}</span></span>
                  <ChevronRight size={20} />
                </button>
                {find('labels.html') && (
                  <button
                    type="button"
                    className="dl"
                    onClick={() => saveArtifact(find('labels.html')!.url, 'labels.html', true)}
                  >
                    <span className="dl-icon"><Tag size={20} /></span>
                    <span><strong>{t('Part labels')}</strong><span>{t('Stick one on each cut part')}</span></span>
                    <ChevronRight size={20} />
                  </button>
                )}
                {find('cutlist.csv') && (
                  <button
                    type="button"
                    className="dl"
                    onClick={() => saveArtifact(find('cutlist.csv')!.url, 'cutlist.csv')}
                  >
                    <span className="dl-icon"><FileText size={20} /></span>
                    <span><strong>{t('Parts list for Excel')}</strong><span>{t('CSV file')}</span></span>
                    <Download size={20} />
                  </button>
                )}
              </div>

              {(dxf.length > 0 || gcode.length > 0) && (
                <details className="more" style={{ marginTop: 12 }}>
                  <summary><ChevronRight size={18} /> {t('Files for a CNC machine')}</summary>
                  <div className="dl-list" style={{ marginTop: 8 }}>
                    {dxf.map((a, i) => (
                      <button key={a.url} type="button" className="dl" onClick={() => saveArtifact(a.url, a.name)}>
                        <span className="dl-icon"><Cpu size={20} /></span>
                        <span><strong>Sheet {i + 1} drawing</strong><span>{t('DXF, opens in any CAM software')}</span></span>
                        <Download size={20} />
                      </button>
                    ))}
                    {gcode.map((a, i) => (
                      <button key={a.url} type="button" className="dl" onClick={() => saveArtifact(a.url, a.name)}>
                        <span className="dl-icon"><Cpu size={20} /></span>
                        <span><strong>Sheet {i + 1} G-code</strong><span>{t('Test with an air cut before using')}</span></span>
                        <Download size={20} />
                      </button>
                    ))}
                  </div>
                </details>
              )}
              {artifacts.length === 0 && (
                <p className="small muted" style={{ marginTop: 12 }}>
                  {t('Labels and machine files are made when you start from a 3D file.')}
                </p>
              )}
            </section>

            {fix && !fix.passes_gate && (
              <div className="notice notice-warn">
                <TriangleAlert size={22} />
                <div><strong>{t('Made without passing our checks.')}</strong> {t('You chose to continue, so measure before you cut.')}</div>
              </div>
            )}
            {fix?.passes_gate && findings.length > 0 && (
              <div className="notice notice-info">
                <CircleCheck size={22} />
                <div>
                  <strong>{t('Good to know')}</strong>
                  <ul className="small">{findings.map((s, i) => <li key={i}>{s}</li>)}</ul>
                </div>
              </div>
            )}

            {advice && (
              <details className="more card card-flat">
                <summary><Lightbulb size={18} /> {t('Tips for this job')}</summary>
                <div className="small" style={{ marginTop: 8 }}><ReactMarkdown>{advice}</ReactMarkdown></div>
              </details>
            )}
          </aside>
        </div>
      </div>
    </main>
  );
}
