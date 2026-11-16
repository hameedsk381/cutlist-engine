import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  ArrowLeft, ChevronRight, CircleCheck, Cpu, Download, FileText, Lightbulb, Printer, Tag, TriangleAlert,
} from 'lucide-react';
import SheetLayout from './SheetLayout';
import { tidyName } from '../format';
import { saveArtifact } from '../api';
import type { FinalizeResult, ProcessResult, Sheet } from '../types';

interface Props {
  result: ProcessResult;
  finalized: FinalizeResult | null;
  fromDescription: boolean;
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

export default function Dashboard({ result, finalized, fromDescription, onBackToParts, onForce, error }: Props) {
  const [sheetIndex, setSheetIndex] = useState(0);
  const [activeIds, setActiveIds] = useState<Set<string>>(new Set());

  const boards = useMemo(() => Object.fromEntries(result.boards.map(b => [b.id, b])), [result.boards]);
  const names = useMemo(
    () => Object.fromEntries(result.boards.map(b => [b.id, tidyName(b.label || b.id)])),
    [result.boards],
  );
  const summary = result.material_summary;
  const sheets = result.sheets;
  const money = (v: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: summary.currency || 'INR', maximumFractionDigits: 0 }).format(v);

  const thicknessOf = (sheet: Sheet) => boards[sheet.parts[0]?.board_id]?.thickness;
  const sheetName = (sheet: Sheet) => {
    const t = thicknessOf(sheet);
    return `Sheet ${sheet.sheet_id}${t ? ` · ${t} mm` : ''}`;
  };
  const byThickness = useMemo(() => {
    const counts = new Map<number, number>();
    sheets.forEach(s => { const t = thicknessOf(s) ?? 0; counts.set(t, (counts.get(t) || 0) + 1); });
    return [...counts.entries()].sort((a, b) => b[0] - a[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheets, boards]);

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
          <h1>This design is not ready to cut</h1>
          <p className="lead">We stopped before making a plan, because the sizes we read may be wrong. Cutting from it could waste sheets.</p>
        </div>
        <div className="stack">
          <div className="notice notice-warn">
            <TriangleAlert size={22} />
            <div>
              <strong>What we found</strong>
              <ul>{findings.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </div>
          </div>
          {fix && fix.recommendations.length > 0 && (
            <div className="notice notice-info">
              <Lightbulb size={22} />
              <div>
                <strong>How to fix it</strong>
                <ul>{fix.recommendations.map((s, i) => <li key={i}>{s}</li>)}</ul>
              </div>
            </div>
          )}
          {error && <div className="notice notice-danger" role="alert"><TriangleAlert size={20} /><div>{error}</div></div>}
          <div className="row">
            {onBackToParts && (
              <button type="button" className="btn btn-primary btn-lg" onClick={onBackToParts}><ArrowLeft size={20} /> Back to the parts</button>
            )}
            <button
              type="button" className="btn btn-danger"
              onClick={() => window.confirm('Make the plan anyway? Only do this if you have checked every part size yourself.') && onForce()}
            >
              I have checked the sizes, make the plan anyway
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
          <h1>Your cutting plan</h1>
          <p className="lead">
            {totalParts} parts on {summary.sheet_count} {summary.sheet_count === 1 ? 'sheet' : 'sheets'}. Tap a part in the list to find it on the sheet.
          </p>
        </div>
        <div className="row no-print">
          {onBackToParts && <button type="button" className="btn" onClick={onBackToParts}><ArrowLeft size={20} /> Change parts</button>}
          <button type="button" className="btn btn-primary" onClick={() => window.print()}><Printer size={20} /> Print plan</button>
        </div>
      </div>

      <div className="stack">
        {fromDescription && (
          <div className="notice notice-warn">
            <TriangleAlert size={22} />
            <div><strong>These sizes are an AI estimate from your description.</strong> Check every part against your own measurements before cutting.</div>
          </div>
        )}
        {error && <div className="notice notice-danger" role="alert"><TriangleAlert size={20} /><div>{error}</div></div>}

        <section className="stats" aria-label="Summary">
          <div className="stat">
            <div className="stat-label">Sheets to buy</div>
            <div className="stat-value num">{summary.sheet_count}</div>
            <div className="stat-sub">{byThickness.map(([t, n]) => `${n} × ${t} mm`).join(' · ')}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Material cost</div>
            <div className="stat-value num">{money(summary.total_material_cost)}</div>
            <div className="stat-sub">at the sheet price you entered</div>
          </div>
          <div className="stat">
            <div className="stat-label">Wood used</div>
            <div className="stat-value num">{Math.round(summary.utilization_percent)}%</div>
            <div className="stat-sub">{Math.round(summary.waste_percent)}% is left over</div>
          </div>
          <div className="stat">
            <div className="stat-label">Spare pieces worth keeping</div>
            <div className="stat-value num">{summary.reusable_offcut_area.toFixed(1)} m²</div>
            <div className="stat-sub">shown hatched in green</div>
          </div>
        </section>

        <div className="result-grid">
          <div className="stack">
            {sheet && (
              <section className="card screen-only" aria-label="Sheet layout">
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
                <SheetLayout sheet={sheet} activeIds={activeIds} onSelect={id => selectBoards([id])} names={names} />
                <div className="sheet-meta">
                  <span><span className="legend-swatch" style={{ background: 'var(--part)' }} />Part to cut</span>
                  <span><span className="legend-swatch" style={{ background: 'var(--ok-soft)', borderColor: 'var(--ok)' }} />Spare piece worth keeping</span>
                  <span><span className="legend-swatch" style={{ background: 'var(--wood)' }} />Waste</span>
                  <span className="num">{sheet.parts.length} parts · {Math.round(sheet.utilization_percent)}% used</span>
                </div>
              </section>
            )}

            {/* On paper every sheet is printed, one after another. */}
            <div className="only-print print-all-sheets">
              {sheets.map(s => (
                <div key={s.sheet_id} className="sheet-print">
                  <h2 style={{ marginBottom: 8 }}>{sheetName(s)} — {Math.round(s.width)} × {Math.round(s.height)} mm</h2>
                  <SheetLayout sheet={s} activeIds={new Set()} onSelect={() => {}} names={names} />
                </div>
              ))}
            </div>

            <section className="card" aria-label="Parts list">
              <div className="card-title"><h2>Parts list</h2><span className="tag tag-muted num">{totalParts} parts</span></div>
              <div className="table-wrap">
                <table className="cut">
                  <thead>
                    <tr><th>Qty</th><th>Part</th><th>Length</th><th>Width</th><th>Thick</th></tr>
                  </thead>
                  <tbody>
                    {result.cutlist.map(item => {
                      const ids = item.board_ids || [];
                      const active = ids.some(id => activeIds.has(id));
                      const label = [...new Set((item.labels || []).map(tidyName))].join(', ') || item.id;
                      return (
                        <tr
                          key={item.id} className={active ? 'is-active' : ''} tabIndex={0}
                          onClick={() => selectBoards(ids)}
                          onKeyDown={e => { if (e.key === 'Enter') selectBoards(ids); }}
                        >
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
            <section className="card" aria-label="Downloads">
              <div className="card-title"><h2>Take it to the workshop</h2></div>
              <div className="dl-list">
                <button type="button" className="dl" onClick={() => window.print()}>
                  <span className="dl-icon"><Printer size={20} /></span>
                  <span><strong>Print the cutting plan</strong><span>Every sheet and the parts list</span></span>
                  <ChevronRight size={20} />
                </button>
                {find('labels.html') && (
                  <button
                    type="button"
                    className="dl"
                    onClick={() => saveArtifact(find('labels.html')!.url, 'labels.html', true)}
                  >
                    <span className="dl-icon"><Tag size={20} /></span>
                    <span><strong>Part labels</strong><span>Stick one on each cut part</span></span>
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
                    <span><strong>Parts list for Excel</strong><span>CSV file</span></span>
                    <Download size={20} />
                  </button>
                )}
              </div>

              {(dxf.length > 0 || gcode.length > 0) && (
                <details className="more" style={{ marginTop: 12 }}>
                  <summary><ChevronRight size={18} /> Files for a CNC machine</summary>
                  <div className="dl-list" style={{ marginTop: 8 }}>
                    {dxf.map((a, i) => (
                      <button key={a.url} type="button" className="dl" onClick={() => saveArtifact(a.url, a.name)}>
                        <span className="dl-icon"><Cpu size={20} /></span>
                        <span><strong>Sheet {i + 1} drawing</strong><span>DXF, opens in any CAM software</span></span>
                        <Download size={20} />
                      </button>
                    ))}
                    {gcode.map((a, i) => (
                      <button key={a.url} type="button" className="dl" onClick={() => saveArtifact(a.url, a.name)}>
                        <span className="dl-icon"><Cpu size={20} /></span>
                        <span><strong>Sheet {i + 1} G-code</strong><span>Test with an air cut before using</span></span>
                        <Download size={20} />
                      </button>
                    ))}
                  </div>
                </details>
              )}
              {artifacts.length === 0 && (
                <p className="small muted" style={{ marginTop: 12 }}>
                  Labels and machine files are made when you start from a 3D file.
                </p>
              )}
            </section>

            {fix && !fix.passes_gate && (
              <div className="notice notice-warn">
                <TriangleAlert size={22} />
                <div><strong>Made without passing our checks.</strong> You chose to continue, so measure before you cut.</div>
              </div>
            )}
            {fix?.passes_gate && findings.length > 0 && (
              <div className="notice notice-info">
                <CircleCheck size={22} />
                <div>
                  <strong>Good to know</strong>
                  <ul className="small">{findings.map((s, i) => <li key={i}>{s}</li>)}</ul>
                </div>
              </div>
            )}

            {advice && (
              <details className="more card card-flat">
                <summary><Lightbulb size={18} /> Tips for this job</summary>
                <div className="small" style={{ marginTop: 8 }}><ReactMarkdown>{advice}</ReactMarkdown></div>
              </details>
            )}
          </aside>
        </div>
      </div>
    </main>
  );
}
