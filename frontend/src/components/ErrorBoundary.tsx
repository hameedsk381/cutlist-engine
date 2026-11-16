import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { t } from '../i18n';

interface State { failed: boolean }

/** A screen that crashes while drawing should say so and offer a way out, never go blank. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('CutList screen crashed', error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="page page-narrow" role="alert">
        <section className="card" style={{ textAlign: 'center' }}>
          <h1 style={{ fontSize: 24 }}>{t('Something went wrong on this screen')}</h1>
          <p className="muted">{t('Your projects are safe. Reload the page to carry on.')}</p>
          <button type="button" className="btn btn-primary btn-lg" onClick={() => window.location.reload()}>
            {t('Reload the page')}
          </button>
        </section>
      </main>
    );
  }
}
