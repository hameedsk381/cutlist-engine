import { useState } from 'react';
import { Check, X, Edit3, AlertTriangle, Shield, ChevronRight } from 'lucide-react';
import type { Board, ExtractResult, ReviewDecisions } from '../types';

interface Props {
  data: ExtractResult;
  onFinalize: (decisions: ReviewDecisions) => void;
  onBack: () => void;
  loading: boolean;
}

export default function ReviewView({ data, onFinalize, onBack, loading }: Props) {
  const [decisions, setDecisions] = useState<ReviewDecisions>(() => {
    const d: ReviewDecisions = {};
    data.boards.forEach(b => {
      d[b.id] = { accepted: true, rename: '', reason: '' };
    });
    return d;
  });
  const [editingId, setEditingId] = useState<string | null>(null);

  const toggle = (id: string) => {
    setDecisions(d => ({
      ...d,
      [id]: { ...d[id], accepted: !d[id].accepted, reason: d[id].accepted ? 'rejected' : '' },
    }));
  };

  const rename = (id: string, name: string) => {
    setDecisions(d => ({ ...d, [id]: { ...d[id], rename: name } }));
  };

  const accepted = Object.values(decisions).filter(d => d.accepted).length;
  const rejected = Object.values(decisions).filter(d => !d.accepted).length;
  const rpt = data.extraction_report;

  return (
    <div style={{ minHeight: '100%', padding: 32 }}>
      <div className="animate-slide-up" style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* Header */}
        <div className="flex items-center justify-between" style={{ marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: '1.5rem' }}>Review Extracted Boards</h1>
            <p style={{ color: 'var(--text-secondary)', marginTop: 4 }}>
              Accept, reject, or rename parts before finalizing the cutlist
            </p>
          </div>
          <div className="flex gap-2">
            <button className="btn btn-secondary" onClick={onBack}>← Back</button>
            <button
              className="btn btn-primary"
              disabled={loading || accepted === 0}
              onClick={() => onFinalize(decisions)}
            >
              {loading ? (
                <><div className="spinner" style={{ borderTopColor: '#000' }} /> Finalizing…</>
              ) : (
                <><ChevronRight size={16} /> Finalize {accepted} Parts</>
              )}
            </button>
          </div>
        </div>

        {/* Extraction Stats */}
        <div className="grid grid-4 gap-3 stagger" style={{ marginBottom: 24 }}>
          <div className="card stat-card">
            <div className="stat-icon" style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>
              <Shield size={18} />
            </div>
            <div>
              <div className="stat-value">{rpt.board_count}</div>
              <div className="stat-label">Boards Found</div>
            </div>
          </div>
          <div className="card stat-card">
            <div className="stat-icon" style={{ background: 'var(--info-bg)', color: 'var(--info)' }}>📐</div>
            <div>
              <div className="stat-value">{rpt.plane_count}</div>
              <div className="stat-label">Planes Detected</div>
            </div>
          </div>
          <div className="card stat-card">
            <div className="stat-icon" style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>
              <Check size={18} />
            </div>
            <div>
              <div className="stat-value" style={{ color: 'var(--accent)' }}>{accepted}</div>
              <div className="stat-label">Accepted</div>
            </div>
          </div>
          <div className="card stat-card">
            <div className="stat-icon" style={{ background: 'var(--danger-bg)', color: 'var(--danger)' }}>
              <X size={18} />
            </div>
            <div>
              <div className="stat-value" style={{ color: rejected > 0 ? 'var(--danger)' : 'var(--text-dim)' }}>{rejected}</div>
              <div className="stat-label">Rejected</div>
            </div>
          </div>
        </div>

        {/* Processing info */}
        {rpt.triangle_count > 0 && (
          <p style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 16 }}>
            ⏱ Processed {rpt.triangle_count.toLocaleString()} triangles ({rpt.usable_triangle_count.toLocaleString()} usable) • {rpt.surface_count} surfaces • Overall confidence: {Math.round(rpt.confidence * 100)}%
          </p>
        )}

        {/* Board Review Table */}
        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="review-table">
              <thead>
                <tr>
                  <th style={{ width: 50 }}>Status</th>
                  <th>Part Name</th>
                  <th>Length</th>
                  <th>Width</th>
                  <th>T</th>
                  <th>Confidence</th>
                  <th>Source</th>
                  <th style={{ width: 50 }}>Shape</th>
                  <th style={{ width: 80 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.boards.map((board) => {
                  const dec = decisions[board.id];
                  return (
                    <tr key={board.id} className={dec.accepted ? '' : 'rejected'}>
                      <td>
                        <button
                          className={`btn btn-icon btn-sm ${dec.accepted ? '' : 'btn-danger'}`}
                          style={dec.accepted ? { background: 'var(--accent-dim)', color: 'var(--accent)' } : {}}
                          onClick={() => toggle(board.id)}
                          title={dec.accepted ? 'Click to reject' : 'Click to accept'}
                        >
                          {dec.accepted ? <Check size={14} /> : <X size={14} />}
                        </button>
                      </td>
                      <td>
                        {editingId === board.id ? (
                          <input
                            className="input input-sm"
                            autoFocus
                            defaultValue={dec.rename || board.label}
                            onBlur={e => { rename(board.id, e.target.value); setEditingId(null); }}
                            onKeyDown={e => { if (e.key === 'Enter') { rename(board.id, (e.target as HTMLInputElement).value); setEditingId(null); } }}
                            style={{ width: 200 }}
                          />
                        ) : (
                          <span style={{ fontWeight: 600, maxWidth: 260, display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={dec.rename || board.label}>{dec.rename || board.label}</span>
                        )}
                      </td>
                      <td className="mono" style={{ fontSize: 13 }}>{Math.round(board.length)}</td>
                      <td className="mono" style={{ fontSize: 13 }}>{Math.round(board.width)}</td>
                      <td className="mono" style={{ fontSize: 13 }}>{board.thickness}</td>
                      <td>
                        <ConfidenceBadge value={board.confidence} />
                      </td>
                      <td>
                        <span className="truncate" style={{ maxWidth: 150, display: 'inline-block', color: 'var(--text-dim)', fontSize: 12 }}>
                          {board.source_objects.join(', ') || '—'}
                        </span>
                      </td>
                      <td>
                        <BoardMiniSvg board={board} size={32} />
                      </td>
                      <td>
                        <button
                          className="btn btn-icon btn-sm btn-ghost"
                          onClick={() => setEditingId(editingId === board.id ? null : board.id)}
                          title="Rename"
                        >
                          <Edit3 size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Warnings */}
        {data.boards.some(b => b.warnings.length > 0) && (
          <div className="card animate-in" style={{ marginTop: 16, padding: 16 }}>
            <div className="flex items-center gap-2" style={{ marginBottom: 12, color: 'var(--warning)' }}>
              <AlertTriangle size={16} />
              <span style={{ fontWeight: 600, fontSize: 13 }}>Board Warnings</span>
            </div>
            {data.boards.filter(b => b.warnings.length > 0).map(b => (
              <div key={b.id} style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>
                  {b.label || b.id}
                </div>
                <ul style={{ margin: 0, paddingLeft: 16, listStyle: 'none' }}>
                  {b.warnings.map((w, i) => (
                    <li key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 2, position: 'relative', paddingLeft: 12 }}>
                      <span style={{ position: 'absolute', left: 0, color: 'var(--warning)' }}>•</span>
                      {w}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const cls = pct >= 90 ? 'badge-success' : pct >= 70 ? 'badge-warning' : 'badge-danger';
  return <span className={`badge ${cls}`}>{pct}%</span>;
}

function BoardMiniSvg({ board, size }: { board: Board; size: number }) {
  if (!board.contour || board.contour.length < 3) {
    return <div style={{ width: size, height: size, background: 'var(--surface-hover)', borderRadius: 4 }} />;
  }
  const xs = board.contour.map(p => p[0]);
  const ys = board.contour.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const w = maxX - minX || 1, h = maxY - minY || 1;
  const pad = 2;
  const vb = `${minX - pad} ${minY - pad} ${w + pad * 2} ${h + pad * 2}`;
  const d = `M ${board.contour[0][0]} ${board.contour[0][1]} ` +
    board.contour.slice(1).map(p => `L ${p[0]} ${p[1]}`).join(' ') + ' Z';
  return (
    <svg width={size} height={size} viewBox={vb} style={{ borderRadius: 4 }}>
      <path d={d} fill="var(--accent-dim)" stroke="var(--accent)" strokeWidth={w / 20} />
    </svg>
  );
}
