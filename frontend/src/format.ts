/** Turn a modelling name like "left_side" into "Left side" for display. */
export function tidyName(raw: string): string {
  const s = raw.replace(/[_-]+/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
