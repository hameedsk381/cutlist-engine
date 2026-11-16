import { useState } from 'react';
import { t } from '../i18n';
import { LayoutGrid, LoaderCircle, LogIn, UserPlus } from 'lucide-react';
import { saasLogin, saasSignup, friendlyError } from '../api';
import type { SaaSUser } from '../types';

interface Props {
  onAuthed: (user: SaaSUser) => void;
  onTryWithoutAccount: () => void;
}

export default function AuthView({ onAuthed, onTryWithoutAccount }: Props) {
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = mode === 'login'
        ? await saasLogin(email.trim(), password)
        : await saasSignup(email.trim(), password);
      onAuthed(user);
    } catch (err) {
      setError(friendlyError(err, mode === 'login'
        ? 'Could not sign you in. Check your email and password.'
        : 'Could not create the account. Try a different email.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="page page-narrow">
      <div className="auth-hero">
        <span className="brand-mark auth-mark" aria-hidden="true"><LayoutGrid size={28} /></span>
        <h1>{t('Turning designs into cut lists')}</h1>
        <p className="lead">
          Upload a 3D model, get nested sheet layouts, DXF, G-code and a
          workshop-ready parts list — in one click.
        </p>
      </div>

      <section className="card">
        <div className="card-title">
          <h2>{mode === 'login' ? 'Welcome back' : 'Create your free account'}</h2>
        </div>

        <form onSubmit={submit} className="stack">
          <div className="field">
            <label htmlFor="auth-email">{t('Email')}</label>
            <input
              id="auth-email"
              className="input"
              type="email"
              required
              autoComplete="email"
              placeholder="you@workshop.in"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="auth-password">{t('Password')}</label>
            <input
              id="auth-password"
              className="input"
              type="password"
              required
              minLength={8}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              placeholder={mode === 'signup' ? 'At least 8 characters' : ''}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {error && <div className="notice notice-danger"><TriangleAlertIcon /> {error}</div>}

          <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy}>
            {busy
              ? <><LoaderCircle size={20} className="spinner" /> {t('Working…')}</>
              : mode === 'login'
                ? <><LogIn size={20} /> {t('Sign in')}</>
                : <><UserPlus size={20} /> {t('Create account')}</>}
          </button>
        </form>

        <p className="muted small" style={{ textAlign: 'center', marginTop: 14 }}>
          {mode === 'login' ? (
            <>{t('New here?')} <button type="button" className="linklike" onClick={() => { setMode('signup'); setError(null); }}>{t('Create a free account')}</button></>
          ) : (
            <>{t('Already have an account?')} <button type="button" className="linklike" onClick={() => { setMode('login'); setError(null); }}>{t('Sign in')}</button></>
          )}
        </p>
      </section>

      <p className="muted small" style={{ textAlign: 'center' }}>
        <button type="button" className="linklike" onClick={onTryWithoutAccount}>
          Try it without an account →
        </button>
      </p>
    </main>
  );
}

function TriangleAlertIcon() {
  return <span aria-hidden="true">⚠️</span>;
}
