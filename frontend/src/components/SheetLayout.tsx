import { useState } from 'react';
import type { Sheet, Board } from '../types';

interface Props {
  sheet: Sheet;
  boards: Board[];
}

export default function SheetLayout({ sheet, boards }: Props) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const boardMap = Object.fromEntries(boards.map(b => [b.id, b]));

  const utilizationColor = sheet.utilization_percent >= 85 ? 'var(--accent)'
    : sheet.utilization_percent >= 70 ? 'var(--warning)' : 'var(--danger)';

  return (
    <div className="card animate-in" style={{ overflow: 'hidden' }}>
      {/* Header */}
      <div className="flex items-center justify-between" style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
        <div className="flex items-center gap-3">
          <span style={{ fontWeight: 700, fontSize: 15 }}>Sheet {sheet.sheet_id}</span>
          <span className="mono" style={{ fontSize: 12, color: 'var(--text-dim)' }}>
            {sheet.width} × {sheet.height} mm
          </span>
          {sheet.sheet_cost > 0 && (
            <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>
              • {sheet.currency} {sheet.sheet_cost.toFixed(0)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="badge badge-neutral">{sheet.parts.length} cuts</span>
          <span className="badge" style={{
            background: `color-mix(in srgb, ${utilizationColor} 15%, transparent)`,
            color: utilizationColor,
          }}>
            {sheet.utilization_percent.toFixed(1)}% used
          </span>
        </div>
      </div>

      {/* Utilization bar */}
      <div style={{ padding: '0 20px' }}>
        <div className="progress-bar" style={{ marginTop: 12 }}>
          <div
            className="progress-bar-fill"
            style={{
              width: `${sheet.utilization_percent}%`,
              background: `linear-gradient(90deg, ${utilizationColor}, ${utilizationColor}aa)`,
            }}
          />
        </div>
      </div>

      {/* SVG Layout */}
      <div style={{ padding: '16px 20px 20px' }}>
        <div className="sheet-container">
          <svg
            viewBox={`0 0 ${sheet.width} ${sheet.height}`}
            preserveAspectRatio="xMidYMid meet"
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
          >
            {/* Parts */}
            {sheet.parts.map((p, idx) => {
              const board = boardMap[p.board_id];
              if (!board) return null;

              let pathData = '';
              const contour = (p as any).contour || board.contour;
              const holes = (p as any).holes || board.holes;

              if (contour?.length > 0) {
                pathData = `M ${contour[0][0]} ${contour[0][1]} ` +
                  contour.slice(1).map((pt: number[]) => `L ${pt[0]} ${pt[1]}`).join(' ') + ' Z';
                if (holes?.length > 0) {
                  holes.forEach((hole: number[][]) => {
                    pathData += ` M ${hole[0][0]} ${hole[0][1]} ` +
                      hole.slice(1).map((pt: number[]) => `L ${pt[0]} ${pt[1]}`).join(' ') + ' Z';
                  });
                }
              } else {
                pathData = `M 0 0 L ${p.length} 0 L ${p.length} ${p.width} L 0 ${p.width} Z`;
              }

              const isHovered = hoveredIdx === idx;
              const isVisible = (p as any).priority === 'visible' || board.priority === 'visible';

              const fill = isHovered
                ? 'rgba(16,185,129,0.25)'
                : isVisible
                  ? 'rgba(16,185,129,0.08)'
                  : 'rgba(255,255,255,0.04)';
              const stroke = isHovered
                ? 'var(--accent)'
                : isVisible
                  ? 'rgba(16,185,129,0.4)'
                  : 'rgba(255,255,255,0.12)';

              let transform = `translate(${p.x}, ${p.y})`;
              if (p.rotation === 90) {
                transform += ` rotate(90, 0, 0) translate(0, -${p.length})`;
              }

              return (
                <path
                  key={idx}
                  d={pathData}
                  transform={transform}
                  fill={fill}
                  stroke={stroke}
                  strokeWidth="1.5"
                  vectorEffect="non-scaling-stroke"
                  style={{ cursor: 'pointer', transition: 'fill 0.15s, stroke 0.15s' }}
                  onMouseEnter={() => setHoveredIdx(idx)}
                  onMouseLeave={() => setHoveredIdx(null)}
                />
              );
            })}

            {/* Offcut rectangles */}
            {sheet.offcuts?.filter(o => o.reusable).map((o, idx) => (
              <rect
                key={`off-${idx}`}
                x={o.x} y={o.y} width={o.width} height={o.height}
                fill="none"
                stroke="var(--accent)"
                strokeWidth="1"
                strokeDasharray="6 3"
                vectorEffect="non-scaling-stroke"
                opacity={0.3}
              />
            ))}
          </svg>

          {/* Label overlays */}
          {sheet.parts.map((p, idx) => {
            const board = boardMap[p.board_id];
            const w = p.rotation === 90 ? p.width : p.length;
            const h = p.rotation === 90 ? p.length : p.width;
            const isHovered = hoveredIdx === idx;
            const label = (p as any).label || board?.label || p.board_id;

            // Smart sizing: hide labels when part is too small relative to sheet
            const partWidthPct = (w / sheet.width) * 100;
            const partHeightPct = (h / sheet.height) * 100;
            const isTiny = partWidthPct < 8 || partHeightPct < 8;
            const isSmall = partWidthPct < 15 || partHeightPct < 12;

            return (
              <div
                key={`lbl-${idx}`}
                style={{
                  position: 'absolute',
                  left: `${(p.x / sheet.width) * 100}%`,
                  top: `${(p.y / sheet.height) * 100}%`,
                  width: `${partWidthPct}%`,
                  height: `${partHeightPct}%`,
                  display: 'flex', flexDirection: 'column',
                  alignItems: 'center', justifyContent: 'center',
                  pointerEvents: 'none', padding: 4,
                  opacity: isHovered ? 1 : 0.7,
                  transition: 'opacity 0.15s',
                }}
                onMouseEnter={() => setHoveredIdx(idx)}
              >
                <span style={{
                  width: isTiny ? 14 : 20, height: isTiny ? 14 : 20, borderRadius: '50%',
                  background: 'var(--accent)', color: '#000',
                  fontSize: isTiny ? 8 : 10, fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  marginBottom: 2, flexShrink: 0,
                }}>{idx + 1}</span>
                {!isTiny && (
                  <span style={{
                    fontSize: isSmall ? 8 : 9, fontWeight: 600, color: 'var(--text)',
                    textShadow: '0 0 6px var(--bg), 0 0 12px var(--bg)',
                    maxWidth: '100%', textAlign: 'center',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }} title={label}>{label}</span>
                )}
                {!isTiny && (
                  <span className="mono" style={{
                    fontSize: 8, color: 'var(--text-dim)',
                    textShadow: '0 0 4px var(--bg)',
                  }}>{Math.round(p.length)}×{Math.round(p.width)}</span>
                )}
              </div>
            );
          })}

          {/* Offcut labels */}
          {sheet.offcuts?.filter(o => o.reusable).map((o, idx) => (
            <div
              key={`offlbl-${idx}`}
              style={{
                position: 'absolute',
                left: `${(o.x / sheet.width) * 100}%`,
                top: `${(o.y / sheet.height) * 100}%`,
                width: `${(o.width / sheet.width) * 100}%`,
                height: `${(o.height / sheet.height) * 100}%`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                pointerEvents: 'none',
              }}
            >
              <span className="mono" style={{ fontSize: 10, color: 'var(--accent)', opacity: 0.7 }}>
                {Math.round(o.width)}×{Math.round(o.height)}
              </span>
            </div>
          ))}
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4" style={{ marginTop: 10, fontSize: 11, color: 'var(--text-dim)' }}>
          <span className="flex items-center gap-1">
            <span style={{ width: 10, height: 10, borderRadius: 2, background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.4)' }} />
            Visible
          </span>
          <span className="flex items-center gap-1">
            <span style={{ width: 10, height: 10, borderRadius: 2, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)' }} />
            Internal
          </span>
          <span className="flex items-center gap-1">
            <span style={{ width: 10, height: 10, borderRadius: 2, border: '1px dashed var(--accent)', opacity: 0.4 }} />
            Reusable Offcut
          </span>
        </div>
      </div>

      {/* Hovered Part Detail */}
      {hoveredIdx !== null && sheet.parts[hoveredIdx] && (() => {
        const p = sheet.parts[hoveredIdx];
        const board = boardMap[p.board_id];
        const label = (p as any).label || board?.label || p.board_id;
        return (
          <div style={{
            padding: '10px 20px', borderTop: '1px solid var(--border)',
            background: 'var(--surface-hover)', fontSize: 12,
          }}>
            <span style={{ fontWeight: 600, marginRight: 12 }}>{label}</span>
            <span className="mono" style={{ color: 'var(--text-secondary)' }}>
              {Math.round(p.length)} × {Math.round(p.width)} mm
            </span>
            <span style={{ color: 'var(--text-dim)', marginLeft: 12 }}>
              at ({Math.round(p.x)}, {Math.round(p.y)})
              {p.rotation ? ` ↻${p.rotation}°` : ''}
            </span>
          </div>
        );
      })()}
    </div>
  );
}
