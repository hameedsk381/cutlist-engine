import { useId, useMemo, useRef, useState } from 'react';
import type { MouseEvent } from 'react';
import { Minus, Plus, Maximize2 } from 'lucide-react';
import { t } from '../i18n';
import { describeTape, partGroup, tidyName } from '../format';
import type { Board, CutStep, Sheet, SheetPart } from '../types';

interface Props {
  sheet: Sheet;
  activeIds: Set<string>;
  onSelect: (boardId: string) => void;
  /** Display name of every board in the plan, so part colours stay the same on every sheet. */
  names: Record<string, string>;
  /** Boards by id, for the hover card (thickness, material, tape). */
  boards?: Record<string, Board>;
  /** Row number of each board in the parts list, shown on the part. */
  numbers?: Record<string, number>;
  /** Select every board of one kind, from the legend. */
  onSelectGroup?: (ids: string[]) => void;
  /** False for the printed copy: no zoom, hover card or dimming. */
  interactive?: boolean;
  /** Saw cuts to draw over the sheet, and the one to stress. */
  cuts?: CutStep[];
  activeCut?: number | null;
}

/** Soft, well-separated hues. Each kind of part gets one, in order of first appearance. */
const HUES = [28, 205, 150, 340, 262, 48, 178, 8, 228, 100];
const ZOOMS = [1, 1.5, 2, 3];

/** Outline of a part in sheet coordinates, following its real shape when it has one. */
function partPath(part: SheetPart): string {
  const rect = `M${part.x} ${part.y} h${part.length} v${part.width} h${-part.length} Z`;
  const contour = part.contour;
  if (!contour || contour.length < 3) return rect;

  const xs = contour.map(p => p[0]);
  const ys = contour.map(p => p[1]);
  const minX = Math.min(...xs), minY = Math.min(...ys);
  const cw = Math.max(...xs) - minX, ch = Math.max(...ys) - minY;
  const direct = Math.abs(cw - part.length) < 2 && Math.abs(ch - part.width) < 2;
  const turned = Math.abs(ch - part.length) < 2 && Math.abs(cw - part.width) < 2;
  if (!direct && !turned) return rect;

  const place = ([px, py]: [number, number]): [number, number] =>
    direct
      ? [part.x + (px - minX), part.y + (py - minY)]
      : [part.x + (ch - (py - minY)), part.y + (px - minX)];
  const loop = (pts: [number, number][]) =>
    pts.map(place).map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ') + ' Z';
  return [loop(contour), ...(part.holes || []).map(loop)].join(' ');
}

interface Label { vertical: boolean; size: number; text: string; dims: boolean }

/** Pick the way to write a name inside a part: across, or turned for a tall narrow part. */
function fitLabel(part: SheetPart, name: string, minSize: number, maxSize: number): Label | null {
  const CHAR = 0.58; // average glyph width as a share of the font size
  let best: Label | null = null;
  for (const vertical of [false, true]) {
    const room = vertical ? part.width : part.length;     // along the text
    const depth = vertical ? part.length : part.width;    // across the text
    const margin = 0.9;
    const size = Math.min(maxSize, (depth * margin) / 2.7, (room * margin) / Math.max(3, Math.min(name.length, 14)) / CHAR);
    if (size < minSize) continue;
    const chars = Math.max(3, Math.floor((room * margin) / (size * CHAR)));
    const text = name.length > chars ? `${name.slice(0, chars - 1)}…` : name;
    const dims = depth * margin > size * 2.7 && room * margin > size * 7;
    if (!best || size > best.size) best = { vertical, size, text, dims };
  }
  return best;
}

export default function SheetLayout({
  sheet, activeIds, onSelect, names, boards, numbers, onSelectGroup, interactive = true, cuts, activeCut = null,
}: Props) {
  const uid = useId().replace(/:/g, '');
  const wrapRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [hover, setHover] = useState<{ id: string; x: number; y: number; flip: boolean } | null>(null);

  const stroke = sheet.width / 420;
  const pad = sheet.width / 26;               // room for the size lines
  const reusable = sheet.offcuts.filter(o => o.reusable);
  const anySelected = interactive && activeIds.size > 0;

  /** What kind of part a board is. Named parts group by name ("Shelf 1", "Shelf 2" are "shelf");
   *  parts with a default name ("Component 13 8") group by size, which is what they have in common. */
  const kindOf = useMemo(() => (id: string, name: string): { key: string; label: string } => {
    const base = partGroup(name);
    const board = boards?.[id];
    if (board && /^(component|part|mesh|group|object|panel|solid|unnamed)\b/.test(base)) {
      const size = `${Math.round(board.length)} × ${Math.round(board.width)}`;
      return { key: `${base}|${size}|${board.thickness}`, label: `${size} · ${board.thickness} mm` };
    }
    return { key: base, label: name.replace(/\s*#?\d+$/, '') || name };
  }, [boards]);

  // One hue per kind, in order of first appearance, so it is the same on every sheet.
  const hueOf = useMemo(() => {
    const order: string[] = [];
    Object.entries(names).forEach(([id, n]) => { const k = kindOf(id, n).key; if (!order.includes(k)) order.push(k); });
    return (id: string, name: string) => HUES[Math.max(0, order.indexOf(kindOf(id, name).key)) % HUES.length];
  }, [names, kindOf]);

  const legend = useMemo(() => {
    const groups = new Map<string, { label: string; hue: number; ids: string[]; count: number }>();
    sheet.parts.forEach(p => {
      const name = names[p.board_id] || p.label || p.board_id;
      const kind = kindOf(p.board_id, name);
      const g = groups.get(kind.key) || { label: kind.label, hue: hueOf(p.board_id, name), ids: [], count: 0 };
      g.ids.push(p.board_id);
      g.count += 1;
      groups.set(kind.key, g);
    });
    return [...groups.values()];
  }, [sheet.parts, names, hueOf, kindOf]);

  const minText = sheet.width / 85;
  const maxText = sheet.width / 36;

  const showCard = (id: string, e: MouseEvent | { currentTarget: Element }) => {
    if (!interactive || !wrapRef.current) return;
    const box = wrapRef.current.getBoundingClientRect();
    let x: number, y: number;
    if ('clientX' in e) { x = e.clientX - box.left; y = e.clientY - box.top; }
    else {
      const r = e.currentTarget.getBoundingClientRect();
      x = r.left - box.left + r.width / 2; y = r.top - box.top + r.height / 2;
    }
    setHover({ id, x, y, flip: x > box.width * 0.55 });
  };

  const hovered = hover ? sheet.parts.find(p => p.board_id === hover.id) : null;
  const hoveredBoard = hover ? boards?.[hover.id] : undefined;

  const hue = (h: number, s: number, l: number) => `hsl(${h} ${s}% ${l}%)`;

  return (
    <div className="sheet-view">
      {interactive && (
        <div className="sheet-tools" role="group" aria-label={t('Zoom')}>
          <button type="button" className="icon-btn" aria-label={t('Zoom out')} disabled={zoom === ZOOMS[0]}
            onClick={() => setZoom(z => ZOOMS[Math.max(0, ZOOMS.indexOf(z) - 1)])}><Minus size={18} /></button>
          <span className="small muted num" aria-live="polite">{Math.round(zoom * 100)}%</span>
          <button type="button" className="icon-btn" aria-label={t('Zoom in')} disabled={zoom === ZOOMS[ZOOMS.length - 1]}
            onClick={() => setZoom(z => ZOOMS[Math.min(ZOOMS.length - 1, ZOOMS.indexOf(z) + 1)])}><Plus size={18} /></button>
          <button type="button" className="icon-btn" aria-label={t('Fit to screen')} disabled={zoom === 1}
            onClick={() => setZoom(1)}><Maximize2 size={16} /></button>
        </div>
      )}

      <div className="sheet-scroll" ref={wrapRef} onMouseLeave={() => setHover(null)}>
        <svg
          className="sheet-svg"
          style={{ width: `${zoom * 100}%` }}
          viewBox={`${-pad * 1.5} ${-pad * 1.4} ${sheet.width + pad * 2.5} ${sheet.height + pad * 2.4}`}
          role="img"
          aria-label={`Sheet ${sheet.sheet_id}: ${sheet.parts.length} parts on a ${Math.round(sheet.width)} by ${Math.round(sheet.height)} mm sheet`}
        >
          <defs>
            <linearGradient id={`wood-${uid}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#efddb9" />
              <stop offset="1" stopColor="#e4cd9f" />
            </linearGradient>
            {/* Plywood face grain: long streaks along the sheet's length. */}
            <filter id={`grain-${uid}`} x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
              <feTurbulence type="fractalNoise" baseFrequency="0.0009 0.085" numOctaves="2" seed={sheet.sheet_id * 7 + 3} />
              <feColorMatrix type="matrix" values="0 0 0 0 0.40  0 0 0 0 0.26  0 0 0 0 0.10  1.3 0 0 0 -0.52" />
            </filter>
            <pattern id={`hatch-${uid}`} width={stroke * 9} height={stroke * 9} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2={stroke * 9} stroke="#15803d" strokeWidth={stroke * 1.2} opacity="0.5" />
            </pattern>
            <clipPath id={`clip-${uid}`}><rect x="0" y="0" width={sheet.width} height={sheet.height} /></clipPath>
          </defs>

          {/* Size lines */}
          <g className="sheet-dim" stroke="var(--text-3)" strokeWidth={stroke} fill="var(--text-2)">
            <path d={`M0 ${-pad * 0.55} H${sheet.width} M0 ${-pad * 0.8} v${pad * 0.5} M${sheet.width} ${-pad * 0.8} v${pad * 0.5}`} fill="none" />
            <text x={sheet.width / 2} y={-pad * 0.8} fontSize={pad * 0.62} textAnchor="middle" stroke="none" fontWeight="700">
              {Math.round(sheet.width)} mm
            </text>
            <path d={`M${-pad * 0.55} 0 V${sheet.height} M${-pad * 0.8} 0 h${pad * 0.5} M${-pad * 0.8} ${sheet.height} h${pad * 0.5}`} fill="none" />
            <text transform={`translate(${-pad * 0.85} ${sheet.height / 2}) rotate(-90)`} fontSize={pad * 0.62} textAnchor="middle" stroke="none" fontWeight="700">
              {Math.round(sheet.height)} mm
            </text>
          </g>

          {/* The sheet */}
          <rect x={stroke * 3} y={stroke * 3} width={sheet.width} height={sheet.height} fill="rgba(60,40,10,0.22)" rx={stroke * 3} />
          <rect x="0" y="0" width={sheet.width} height={sheet.height} fill={`url(#wood-${uid})`} stroke="var(--wood-line)" strokeWidth={stroke * 1.6} rx={stroke * 3} />

          {reusable.map((o, i) => {
            const text = `${t('Spare')} ${Math.round(o.width)} × ${Math.round(o.height)}`;
            const across = Math.min(o.height / 3, (o.width * 0.9) / (text.length * 0.58), sheet.width / 45);
            const turned = Math.min(o.width / 3, (o.height * 0.9) / (text.length * 0.58), sheet.width / 45);
            const vertical = turned > across;
            const size = Math.max(across, turned);
            const cx = o.x + o.width / 2, cy = o.y + o.height / 2;
            return (
              <g key={`off-${i}`}>
                <rect x={o.x} y={o.y} width={o.width} height={o.height} fill={`url(#hatch-${uid})`} stroke="#15803d" strokeWidth={stroke * 1.2} strokeDasharray={`${stroke * 6} ${stroke * 4}`} />
                {size > sheet.width / 110 && (
                  <text x={cx} y={cy} fontSize={size} textAnchor="middle" dominantBaseline="central" fill="#14532d" fontWeight="700"
                    transform={vertical ? `rotate(-90 ${cx} ${cy})` : undefined}>{text}</text>
                )}
              </g>
            );
          })}

          {/* Parts: cut pieces, tinted by kind */}
          {sheet.parts.map((part, i) => {
            const active = activeIds.has(part.board_id);
            const name = names[part.board_id] || part.label || part.board_id;
            const h = hueOf(part.board_id, name);
            const dim = anySelected && !active;
            return (
              <g
                key={`${part.board_id}-${i}`} className="sheet-part" tabIndex={interactive ? 0 : -1} role="button"
                aria-label={`${name}, ${Math.round(part.length)} by ${Math.round(part.width)} mm`}
                opacity={dim ? 0.4 : 1}
                onClick={() => onSelect(part.board_id)}
                onMouseEnter={e => showCard(part.board_id, e)}
                onMouseMove={e => showCard(part.board_id, e)}
                onFocus={e => showCard(part.board_id, e)}
                onBlur={() => setHover(null)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(part.board_id); } }}
              >
                <path
                  d={partPath(part)} fillRule="evenodd"
                  fill={active ? hue(h, 75, 78) : hue(h, 55, 93)}
                  stroke={active ? 'var(--part-active)' : hue(h, 40, 30)}
                  strokeWidth={active ? stroke * 4 : stroke * 1.4} strokeLinejoin="round"
                />
              </g>
            );
          })}

          {/* Grain across the whole sheet, so cut parts look like the same board */}
          <g clipPath={`url(#clip-${uid})`} pointerEvents="none">
            <rect x="0" y="0" width={sheet.width} height={sheet.height} filter={`url(#grain-${uid})`} opacity="0.38" />
          </g>

          {/* Labels sit on top and never take clicks */}
          <g pointerEvents="none">
            {sheet.parts.map((part, i) => {
              const name = names[part.board_id] || part.label || part.board_id;
              const h = hueOf(part.board_id, name);
              const dim = anySelected && !activeIds.has(part.board_id);
              const label = fitLabel(part, name, minText, maxText);
              const cx = part.x + part.length / 2;
              const cy = part.y + part.width / 2;
              const number = numbers?.[part.board_id];
              const r = Math.min(sheet.width / 78, part.length / 5, part.width / 3.2);
              const badge = number !== undefined && r >= sheet.width / 220;
              const ink = hue(h, 45, 14);
              return (
                <g key={`label-${part.board_id}-${i}`} opacity={dim ? 0.4 : 1}>
                  {label ? (
                    <g transform={label.vertical ? `rotate(-90 ${cx} ${cy})` : undefined}>
                      <text x={cx} y={cy - (label.dims ? label.size * 0.1 : -label.size * 0.35)} fontSize={label.size} textAnchor="middle" fontWeight="700" fill={ink}>{label.text}</text>
                      {label.dims && (
                        <text x={cx} y={cy + label.size * 1.05} fontSize={label.size * 0.78} textAnchor="middle" fill={hue(h, 30, 28)}>
                          {Math.round(part.length)} × {Math.round(part.width)}
                        </text>
                      )}
                    </g>
                  ) : number !== undefined ? (
                    <text x={cx} y={cy} fontSize={Math.min(maxText, part.width * 0.55, part.length * 0.6)} textAnchor="middle" dominantBaseline="central" fontWeight="800" fill={ink}>{number}</text>
                  ) : null}
                  {badge && label && (
                    <g>
                      <circle cx={part.x + r * 1.35} cy={part.y + r * 1.35} r={r} fill={hue(h, 40, 30)} />
                      <text x={part.x + r * 1.35} y={part.y + r * 1.35} fontSize={r * (String(number).length > 2 ? 0.95 : 1.2)} textAnchor="middle" dominantBaseline="central" fontWeight="800" fill="#fff">{number}</text>
                    </g>
                  )}
                </g>
              );
            })}
          </g>

          {/* Saw cuts: a dashed line down the middle of the blade's path, numbered at its far end
              (the near end is where the part numbers sit) */}
          {cuts && cuts.length > 0 && (
            <g pointerEvents="none">
              {cuts.map(c => {
                const on = activeCut === c.step;
                const dim = activeCut !== null && !on;
                const half = c.kerf / 2;
                const [x0, y0, x1, y1] = c.line;
                const horizontal = c.direction === 'horizontal';
                const ax = horizontal ? x0 : x0 + half;
                const ay = horizontal ? y0 + half : y0;
                const bx = horizontal ? x1 : x1 + half;
                const by = horizontal ? y1 + half : y1;
                const r = sheet.width / 95;
                return (
                  <g key={c.step} opacity={dim ? 0.25 : 1}>
                    <line x1={ax} y1={ay} x2={bx} y2={by} stroke="#b3261e" strokeWidth={on ? stroke * 2.4 : stroke * 1.1}
                      strokeDasharray={`${stroke * 7} ${stroke * 4}`} strokeLinecap="round" />
                    <circle cx={bx - (horizontal ? r * 1.3 : 0)} cy={by - (horizontal ? 0 : r * 1.3)} r={on ? r * 1.25 : r} fill="#b3261e" />
                    <text x={bx - (horizontal ? r * 1.3 : 0)} y={by - (horizontal ? 0 : r * 1.3)} fontSize={r * (c.step > 9 ? 1.05 : 1.3)}
                      textAnchor="middle" dominantBaseline="central" fontWeight="800" fill="#fff">{c.step}</text>
                  </g>
                );
              })}
            </g>
          )}
        </svg>

        {interactive && hover && hovered && (
          <div className={`sheet-card ${hover.flip ? 'is-left' : ''}`} style={{ left: hover.x, top: hover.y }} role="tooltip">
            <strong>{numbers?.[hover.id] !== undefined ? `${numbers[hover.id]}. ` : ''}{tidyName(names[hover.id] || hovered.label || hover.id)}</strong>
            <span className="num">{Math.round(hovered.length)} × {Math.round(hovered.width)} mm{hoveredBoard ? ` · ${hoveredBoard.thickness} mm` : ''}</span>
            {hoveredBoard && hoveredBoard.material && hoveredBoard.material !== 'default' && !/^[\d.]+mm$/.test(hoveredBoard.material) && <span>{hoveredBoard.material}</span>}
            {hoveredBoard && describeTape(hoveredBoard.edge_band) && <span>{t('Tape')}: {describeTape(hoveredBoard.edge_band)}</span>}
            {hovered.rotation === 90 && <span className="muted">{t('Turned 90° on the sheet')}</span>}
          </div>
        )}
      </div>

      {legend.length > 1 && (
        <ul className="sheet-legend" aria-label={t('Kinds of part on this sheet')}>
          {legend.slice(0, 12).map(g => (
            <li key={g.label}>
              <button
                type="button" disabled={!interactive || !onSelectGroup}
                onClick={() => onSelectGroup?.(g.ids)}
                title={t('Show these on the sheet')}
              >
                <span className="legend-swatch" style={{ background: hue(g.hue, 58, 88), borderColor: hue(g.hue, 40, 30) }} />
                {g.label.includes('×') ? g.label : tidyName(g.label)} <span className="muted num">× {g.count}</span>
              </button>
            </li>
          ))}
          {legend.length > 12 && <li className="muted small">+{legend.length - 12}</li>}
        </ul>
      )}
    </div>
  );
}
