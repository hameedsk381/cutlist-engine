import { Box, Calculator, FileCode2, LayoutGrid, LogIn, Ruler, Share2, Wrench } from 'lucide-react';
import { t } from '../i18n';

interface Props {
  onOpenApp: () => void;
}

const FEATURES = [
  {
    icon: Box,
    title: 'Upload any 3D model',
    body: 'OBJ, DAE, GLB, STL or DXF from SketchUp, Fusion 360, Blender or AutoCAD. Or just type the sizes.',
  },
  {
    icon: Ruler,
    title: 'Every part found for you',
    body: 'The engine reads the geometry and lists every panel: size, thickness, grain direction, edge banding.',
  },
  {
    icon: Calculator,
    title: 'Nested sheet layouts',
    body: 'Parts are nested on your sheet stock with kerf, offcuts kept and utilization shown sheet by sheet.',
  },
  {
    icon: FileCode2,
    title: 'DXF & G-code out',
    body: 'Download the parts list as CSV, nested DXF per sheet, and G-code ready for your CNC.',
  },
  {
    icon: Share2,
    title: 'Share a quote link',
    body: 'Send a clean read-only cutting plan to your client or the workshop — no account needed to view.',
  },
  {
    icon: Wrench,
    title: 'Built for the shop floor',
    body: 'Job queue keeps plans ready while you work; API keys let your CNC software pull files directly.',
  },
];

export default function LandingView({ onOpenApp }: Props) {
  return (
    <main className="landing">
      <section className="landing-hero">
        <span className="brand-mark landing-mark" aria-hidden="true"><LayoutGrid size={34} /></span>
        <h1>{t('From 3D model to cutting plan, in one click')}</h1>
        <p className="lead">
          CutList turns any furniture model into a parts list, nested plywood sheets,
          DXF and CNC-ready G-code — so you buy the right amount of board and cut without guesswork.
        </p>
        <div className="row" style={{ justifyContent: 'center', marginTop: 24 }}>
          <button type="button" className="btn btn-primary btn-lg" onClick={onOpenApp}>
            {t('Start free — no card needed')}
          </button>
        </div>
        <p className="muted small" style={{ marginTop: 10 }}>
          {t('Free plan: 50 projects a month')}
        </p>
      </section>

      <section className="landing-features">
        {FEATURES.map(({ icon: Icon, title, body }) => (
          <article key={title} className="card card-flat landing-feature">
            <span className="landing-feature-icon" aria-hidden="true"><Icon size={22} /></span>
            <h2>{title}</h2>
            <p className="muted">{body}</p>
          </article>
        ))}
      </section>

      <section className="landing-pricing">
        <div className="card" style={{ textAlign: 'center', padding: '36px 24px' }}>
          <h2>{t('Simple pricing')}</h2>
          <p className="muted" style={{ maxWidth: 520, margin: '8px auto 24px' }}>
            Start free. Upgrade when your workshop does — bigger jobs, more projects,
            priority processing.
          </p>
          <div className="landing-plans">
            <div className="landing-plan">
              <h3>{t('Free')}</h3>
              <p className="num">₹0</p>
              <p className="muted small">50 projects / month<br />{t('All export formats')}</p>
            </div>
            <div className="landing-plan landing-plan-pro">
              <h3>{t('Pro')}</h3>
              <p className="num">{t('Coming soon')}</p>
              <p className="muted small">{t('Unlimited projects')}<br />{t('API access · priority queue')}</p>
            </div>
          </div>
          <button type="button" className="btn btn-primary btn-lg" style={{ marginTop: 20 }} onClick={onOpenApp}>
            <LogIn size={20} /> {t('Create your free account')}
          </button>
        </div>
      </section>
    </main>
  );
}
