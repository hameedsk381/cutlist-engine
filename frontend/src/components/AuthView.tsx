import { useState } from 'react';
import { t } from '../i18n';
import { CircleCheck, LayoutGrid, LoaderCircle, LogIn, Mail, UserPlus } from 'lucide-react';
import { friendlyError, requestPasswordReset, resetPassword, saasLogin, saasSignup } from '../api';
import type { SaaSUser } from '../types';

interface Props {
  onAuthed: (user: SaaSUser) => void;
  onTryWithoutAccount: () => void;
}

type Mode = 'login' | 'signup' | 'forgot' | 'reset';

/** A reset link opens the app as /?reset=TOKEN. Read it once and take it out of the address bar. */
function takeResetToken(): string {
  try {
    const url = new URL(window.location.href);
    const token = url.searchParams.get('reset') || '';
    if (token) {
      url.searchParams.delete('reset');
      window.history.replaceState({}, '', url.pathname + url.search + url.hash);
    }
    return token;
  } catch {
    return '';
  }
}

export default function AuthView({ onAuthed, onTryWithoutAccount }: Props) {
  const [resetToken] = useState(takeResetToken);
  const [mode, setMode] = useState<Mode>(resetToken ? 'reset' : 'login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const go = (next: Mode) => { setMode(next); setError(null); setSent(false); };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === 'forgot') {
        await requestPasswordReset(email.trim());
        setSent(true);
      } else if (mode === 'reset') {
        onAuthed(await resetPassword(resetToken, password));
      } else {
        const user = mode === 'login'
          ? await saasLogin(email.trim(), password)
          : await saasSignup(email.trim(), password);
        onAuthed(user);
      }
    } catch (err) {
      setError(friendlyError(err, mode === 'login'
        ? 'Could not sign you in. Check your email and password.'
        : mode === 'signup'
          ? 'Could not create the account. Try a different email.'
          : mode === 'reset'
            ? 'This reset link has expired or was already used. Ask for a new one.'
            : 'Could not send the email. Try again in a few minutes.'));
    } finally {
      setBusy(false);
    }
  };

  const heading = {
    login: 'Welcome back',
    signup: 'Create your free account',
    forgot: 'Forgot your password?',
    reset: 'Choose a new password',
  }[mode];

  return (
    <main className="page page-narrow">
      <div className="auth-hero">
        <span className="brand-mark auth-mark" aria-hidden="true"><LayoutGrid size={28} /></span>
        <h1>{t('Turning designs into cut lists')}</h1>
        <p className="lead">
          {t('Upload a 3D model, get nested sheet layouts, DXF, G-code and a workshop-ready parts list — in one click.')}
        </p>
      </div>

      <section className="card">
        <div className="card-title">
          <h2>{t(heading)}</h2>
        </div>

        {mode === 'forgot' && sent ? (
          <div className="notice notice-info" role="status">
            <CircleCheck size={20} />
            <div>{t('If that email has an account, we have sent a link to choose a new password. It works once, for one hour.')}</div>
          </div>
        ) : (
          <form onSubmit={submit} className="stack">
            {mode === 'forgot' && (
              <p className="small muted">{t('Enter your email and we will send you a link to choose a new password.')}</p>
            )}
            {mode !== 'reset' && (
              <div className="field">
                <label htmlFor="auth-email">{t('Email')}</label>
                <input
                  id="auth-email" className="input" type="email" required autoComplete="email"
                  placeholder="you@workshop.in" value={email} onChange={(e) => setEmail(e.target.value)}
                />
              </div>
            )}
            {mode !== 'forgot' && (
              <div className="field">
                <label htmlFor="auth-password">{mode === 'reset' ? t('New password') : t('Password')}</label>
                <input
                  id="auth-password" className="input" type="password" required minLength={8}
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  placeholder={mode === 'login' ? '' : t('At least 8 characters')}
                  value={password} onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            )}

            {error && <div className="notice notice-danger" role="alert"><span aria-hidden="true">⚠️</span> {error}</div>}

            <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy}>
              {busy
                ? <><LoaderCircle size={20} className="spinner" /> {t('Working…')}</>
                : mode === 'login'
                  ? <><LogIn size={20} /> {t('Sign in')}</>
                  : mode === 'signup'
                    ? <><UserPlus size={20} /> {t('Create account')}</>
                    : mode === 'forgot'
                      ? <><Mail size={20} /> {t('Send me the link')}</>
                      : <><LogIn size={20} /> {t('Save password and sign in')}</>}
            </button>
          </form>
        )}

        <p className="muted small" style={{ textAlign: 'center', marginTop: 14 }}>
          {mode === 'login' && (
            <>
              {t('New here?')} <button type="button" className="linklike" onClick={() => go('signup')}>{t('Create a free account')}</button>
              {' · '}
              <button type="button" className="linklike" onClick={() => go('forgot')}>{t('Forgot password?')}</button>
            </>
          )}
          {mode === 'signup' && (
            <>{t('Already have an account?')} <button type="button" className="linklike" onClick={() => go('login')}>{t('Sign in')}</button></>
          )}
          {(mode === 'forgot' || mode === 'reset') && (
            <button type="button" className="linklike" onClick={() => go('login')}>{t('Back to sign in')}</button>
          )}
        </p>
        {mode === 'signup' && (
          <p className="muted small" style={{ textAlign: 'center', marginTop: 6 }}>
            {t('By creating an account you agree to the')} <a href="/terms.html" target="_blank" rel="noopener">{t('Terms')}</a> {t('and')} <a href="/privacy.html" target="_blank" rel="noopener">{t('Privacy Policy')}</a>.
          </p>
        )}
      </section>

      <p className="muted small" style={{ textAlign: 'center' }}>
        <button type="button" className="linklike" onClick={onTryWithoutAccount}>
          {t('Try it without an account →')}
        </button>
      </p>
      <p className="muted small" style={{ textAlign: 'center' }}>
        <a href="/terms.html" target="_blank" rel="noopener">{t('Terms')}</a>
        {' · '}
        <a href="/privacy.html" target="_blank" rel="noopener">{t('Privacy Policy')}</a>
      </p>
    </main>
  );
}
