import { Sparkles, TriangleAlert } from 'lucide-react';
import { t } from '../i18n';
import type { ModelAdvice, ModelProblems } from '../types';

interface Props {
  problems?: ModelProblems;
  advice?: ModelAdvice | null;
  /** The blocked screen already lists what was found, so it shows only the explanation. */
  showItems?: boolean;
}

/**
 * Tells the user their 3D model has problems, before they trust the plan.
 *
 * The software measures every problem (numbers and fixes are always shown).
 * When AI is on it also explains them in plain words; if it is off, or its
 * answer is rejected, the software's own wording stands alone.
 */
export default function ModelProblemsCard({ problems, advice, showItems = true }: Props) {
  if (!problems || (problems.severity !== 'medium' && problems.severity !== 'high')) return null;
  const items = problems.items.filter(i => i.severity !== 'low');

  return (
    <section className="notice notice-warn model-problems" aria-label={t('Problems with the 3D model')}>
      <TriangleAlert size={22} />
      <div className="stack" style={{ gap: 10 }}>
        <strong>{t('This 3D model has problems that affect the plan')}</strong>

        {advice && (
          <div className="stack" style={{ gap: 6 }}>
            <p style={{ margin: 0 }}><strong>{advice.headline}</strong></p>
            <p style={{ margin: 0 }}>{advice.explanation}</p>
            {advice.steps.length > 0 && (
              <>
                <span className="field-label">{t('What to do')}</span>
                <ul className="small" style={{ margin: 0 }}>{advice.steps.map((s, i) => <li key={i}>{s}</li>)}</ul>
              </>
            )}
            <p className="small muted" style={{ margin: 0 }}>
              <Sparkles size={14} style={{ verticalAlign: -2 }} /> {t('Explained by AI. Every number comes from the checks of your model.')}
            </p>
          </div>
        )}

        {showItems && (
          <details className="more" open={!advice}>
            <summary>{t('What the software found')}</summary>
            <ul className="problem-list">
              {items.map(item => (
                <li key={item.code}>
                  <strong>{item.title}.</strong> {item.detail}
                  <div className="small muted">{t('How to fix it')}: {item.fix}</div>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </section>
  );
}
