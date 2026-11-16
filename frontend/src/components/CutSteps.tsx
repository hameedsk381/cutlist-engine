import { Fragment } from 'react';
import { t, tf } from '../i18n';
import type { CutStep, Sheet } from '../types';

interface Props {
  sheet: Sheet;
  /** Row number of each board in the parts list, so "frees part 4" matches the list. */
  numbers: Record<string, number>;
  active?: number | null;
  onActive?: (step: number | null) => void;
  /** Show the cut lines on the sheet drawing. */
  showLines?: boolean;
  onShowLines?: (show: boolean) => void;
  interactive?: boolean;
}

const mm = (n: number) => `${Math.round(n * 10) / 10}`;

/** One cut in words, from the saw operator's side: which piece, how far from which edge. */
function describe(step: CutStep): string {
  const edge = step.direction === 'horizontal' ? t('top edge') : t('left edge');
  const piece = `${mm(step.piece[0])} × ${mm(step.piece[1])}`;
  const values = { piece, d: mm(step.from_edge), edge };
  return step.kind === 'trim'
    ? tf('Trim the waste off the {piece} piece: {d} mm from the {edge}', values)
    : tf('Cut the {piece} piece: {d} mm from the {edge}', values);
}

/** The numbered order of saw cuts for one sheet. */
export default function CutSteps({
  sheet, numbers, active = null, onActive, showLines, onShowLines, interactive = true,
}: Props) {
  const cuts = sheet.cuts;
  if (!cuts) return null;
  if (!cuts.ok) {
    return (
      <p className="small muted">
        {t('This sheet cannot be cut with straight edge-to-edge cuts, so no cutting order is given.')}
      </p>
    );
  }
  if (cuts.steps.length === 0) {
    return <p className="small muted">{t('This sheet needs no cuts: one part fills it.')}</p>;
  }

  return (
    <div className="cut-steps">
      {interactive && onShowLines && (
        <label className="check small">
          <input type="checkbox" checked={!!showLines} onChange={e => onShowLines(e.target.checked)} />
          {t('Show the cut lines on the sheet')}
        </label>
      )}
      <ol className="cut-list">
        {cuts.steps.map((step, i) => {
          const newStage = i === 0 || cuts.steps[i - 1].stage !== step.stage;
          const freed = step.frees.map(id => numbers[id]).filter(n => n !== undefined);
          return (
            <Fragment key={step.step}>
              {newStage && <li className="cut-stage muted small" aria-hidden="true">{tf('Stage {n}', { n: step.stage + 1 })}</li>}
              <li value={step.step} className={`cut-step ${active === step.step ? 'is-active' : ''}`}>
                <button
                  type="button" disabled={!interactive || !onActive}
                  aria-pressed={active === step.step}
                  onClick={() => onActive?.(active === step.step ? null : step.step)}
                >
                  <span className="cut-no num">{step.step}</span>
                  <span className="cut-text">
                    {describe(step)}
                    {freed.length > 0 && (
                      <span className="muted"> → {tf('part {list} done', { list: freed.map(n => `#${n}`).join(', ') })}</span>
                    )}
                  </span>
                </button>
              </li>
            </Fragment>
          );
        })}
      </ol>
      <p className="small muted">
        {tf('Distances are to the near side of the blade. The {kerf} mm blade cuts into the gap beyond it.', { kerf: mm(cuts.steps[0].kerf) })}
      </p>
    </div>
  );
}
