/** Turn a modelling name like "left_side" into "Left side" for display. */
export function tidyName(raw: string): string {
  const s = raw.replace(/[_-]+/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** "Shelf 2", "shelf_2" and "Shelf #3" are all the same kind of part: "shelf". */
export function partGroup(raw: string): string {
  return raw.toLowerCase().replace(/[_-]+/g, ' ').replace(/[\s#]*\d+\s*$/, '').replace(/\s+/g, ' ').trim() || raw.toLowerCase();
}

/** Edge tape [top, right, bottom, left] in plain words, or '' when there is none. */
export function describeTape(band: number[] | undefined): string {
  if (!band || !band.some(v => v > 0)) return '';
  const [top, right, bottom, left] = band;
  const tape = Math.max(...band);
  const where = top > 0 && bottom > 0 && left > 0 && right > 0 ? 'all 4 edges'
    : left > 0 && right > 0 ? 'both long edges' : 'one long edge';
  return `${tape} mm, ${where}`;
}
