import type { Sheet, SheetPart } from '../types';

interface Props {
  sheet: Sheet;
  activeIds: Set<string>;
  onSelect: (boardId: string) => void;
  names: Record<string, string>;
}

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

export default function SheetLayout({ sheet, activeIds, onSelect, names }: Props) {
  const stroke = sheet.width / 400;
  const reusable = sheet.offcuts.filter(o => o.reusable);

  return (
    <svg
      className="sheet-svg"
      viewBox={`${-stroke} ${-stroke} ${sheet.width + stroke * 2} ${sheet.height + stroke * 2}`}
      role="img"
      aria-label={`Sheet ${sheet.sheet_id}: ${sheet.parts.length} parts on a ${Math.round(sheet.width)} by ${Math.round(sheet.height)} mm sheet`}
    >
      <defs>
        <pattern id={`hatch-${sheet.sheet_id}`} width={stroke * 8} height={stroke * 8} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2={stroke * 8} stroke="var(--ok)" strokeWidth={stroke} opacity="0.45" />
        </pattern>
      </defs>

      <rect x="0" y="0" width={sheet.width} height={sheet.height} fill="var(--wood)" stroke="var(--wood-line)" strokeWidth={stroke * 1.5} />

      {reusable.map((o, i) => {
        const size = Math.min(o.width / 7, o.height / 3, sheet.width / 45);
        return (
          <g key={`off-${i}`}>
            <rect x={o.x} y={o.y} width={o.width} height={o.height} fill={`url(#hatch-${sheet.sheet_id})`} stroke="var(--ok)" strokeWidth={stroke} strokeDasharray={`${stroke * 6} ${stroke * 4}`} />
            {size > sheet.width / 110 && (
              <text x={o.x + o.width / 2} y={o.y + o.height / 2} fontSize={size} textAnchor="middle" dominantBaseline="middle" fill="var(--ok)" fontWeight="700">
                Spare {Math.round(o.width)} × {Math.round(o.height)}
              </text>
            )}
          </g>
        );
      })}

      {sheet.parts.map((part, i) => {
        const active = activeIds.has(part.board_id);
        const name = names[part.board_id] || part.label || part.board_id;
        const size = Math.max(sheet.width / 90, Math.min(part.length / 9, part.width / 3.2, sheet.width / 38));
        const fits = part.length > size * 4 && part.width > size * 2.6;
        const maxChars = Math.max(3, Math.floor(part.length / (size * 0.6)));
        const shown = name.length > maxChars ? `${name.slice(0, maxChars - 1)}…` : name;
        const cx = part.x + part.length / 2;
        const cy = part.y + part.width / 2;
        return (
          <g
            key={`${part.board_id}-${i}`} className="sheet-part" tabIndex={0} role="button"
            aria-label={`${name}, ${Math.round(part.length)} by ${Math.round(part.width)} mm`}
            onClick={() => onSelect(part.board_id)}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(part.board_id); } }}
          >
            <path
              d={partPath(part)} fillRule="evenodd"
              fill={active ? 'var(--primary-soft)' : 'var(--part)'}
              stroke={active ? 'var(--part-active)' : 'var(--part-line)'}
              strokeWidth={active ? stroke * 3 : stroke * 1.2} strokeLinejoin="round"
            />
            {fits ? (
              <>
                <text x={cx} y={cy - size * 0.15} fontSize={size} textAnchor="middle" fontWeight="700" fill="var(--text)">{shown}</text>
                <text x={cx} y={cy + size * 0.95} fontSize={size * 0.8} textAnchor="middle" fill="var(--text-2)">
                  {Math.round(part.length)} × {Math.round(part.width)}
                </text>
              </>
            ) : (
              <text x={cx} y={cy} fontSize={Math.min(size, part.width * 0.6, part.length * 0.25)} textAnchor="middle" dominantBaseline="middle" fontWeight="700" fill="var(--text)">
                {i + 1}
              </text>
            )}
            <title>{name} — {Math.round(part.length)} × {Math.round(part.width)} mm</title>
          </g>
        );
      })}
    </svg>
  );
}
