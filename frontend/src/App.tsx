import { useEffect, useState } from 'react';
import { t } from './i18n';
import { Check, LayoutGrid, LoaderCircle, LogIn, MessageCircle, RotateCcw } from 'lucide-react';
import LanguageSwitch from './components/LanguageSwitch';
import UploadView from './components/UploadView';
import ReviewView from './components/ReviewView';
import Dashboard from './components/Dashboard';
import ChatDrawer from './components/ChatDrawer';
import AuthView from './components/AuthView';
import LandingView from './components/LandingView';
import ProjectsView from './components/ProjectsView';
import {
  clearSaasToken, describeToModel, extractBoards, finalizeSession, friendlyError, getSaasToken, saasMe,
  aiChat,
} from './api';
import type {
  AppView, ExtractResult, FinalizeResult, ProcessConfig, ProcessResult, ReviewDecisions, SaaSUser,
} from './types';

const STEPS: { view: AppView; label: string }[] = [
  { view: 'upload', label: 'Add your design' },
  { view: 'review', label: 'Check the parts' },
  { view: 'dashboard', label: 'Cutting plan' },
];

const OPENED_BY_RESET_LINK = new URLSearchParams(window.location.search).has('reset');

export default function App() {
  const [view, setView] = useState<AppView>('upload');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [designNotes, setDesignNotes] = useState<string[]>([]);

  // SaaS session: 'unknown' while we check for a stored token on load.
  // A password-reset link goes straight to the sign-in form, even if someone is already signed in.
  const [authState, setAuthState] = useState<'unknown' | 'anon' | 'auth' | 'saas' | 'legacy'>(
    () => (OPENED_BY_RESET_LINK ? 'auth' : getSaasToken() ? 'unknown' : 'anon'),
  );
  const [user, setUser] = useState<SaaSUser | null>(null);

  useEffect(() => {
    if (OPENED_BY_RESET_LINK || !getSaasToken()) return; // 'auth' or 'anon' already
    saasMe()
      .then((u) => {
        setUser(u);
        setAuthState('saas');
      })
      .catch(() => {
        clearSaasToken();
        setAuthState('anon');
      });
  }, []);

  const [config, setConfig] = useState<ProcessConfig | null>(null);
  const [extractData, setExtractData] = useState<ExtractResult | null>(null);
  const [decisions, setDecisions] = useState<ReviewDecisions>({});
  const [sessionId, setSessionId] = useState('');
  const [result, setResult] = useState<ProcessResult | null>(null);
  const [finalized, setFinalized] = useState<FinalizeResult | null>(null);
  const [chatOpen, setChatOpen] = useState(false);

  const handleUpload = async (file: File, cfg: ProcessConfig, described = false) => {
    if (!described) setDesignNotes([]);
    setBusy(t('Reading your design and finding the parts…'));
    setError(null);
    try {
      const data = await extractBoards(file, { ...cfg });
      const initial: ReviewDecisions = {};
      // Anything under 50 mm is almost always hardware; start with it switched off.
      data.boards.forEach(b => {
        const tiny = Math.min(b.length, b.width) < 50;
        initial[b.id] = { accepted: !tiny, rename: '', reason: tiny ? 'Too small to be a board' : '' };
      });
      setConfig(cfg);
      setExtractData(data);
      setDecisions(initial);
      setSessionId(data.session_id);
      setResult(null);
      setFinalized(null);
      setView('review');
    } catch (err) {
      setError(friendlyError(err, 'We could not read that file. Check it is a 3D export (OBJ, DAE, GLB, STL or DXF) and try again.'));
    } finally {
      setBusy(null);
    }
  };

  const handleDescribe = async (description: string, cfg: ProcessConfig) => {
    setBusy(t('Working out the parts from your description…'));
    setError(null);
    try {
      // The server turns the description into a real 3D model; from here it is
      // handled exactly like an uploaded file, so it gets review and CNC files.
      const model = await describeToModel(description, cfg.thickness);
      setDesignNotes(model.notes);
      await handleUpload(new File([model.obj], model.filename, { type: 'text/plain' }), cfg, true);
    } catch (err) {
      setBusy(null);
      setError(friendlyError(err, 'We could not turn that description into parts. Give the height, width and depth in mm.'));
    }
  };

  const handleFinalize = async (force = false) => {
    if (!sessionId) return;
    setBusy(t('Fitting the parts onto sheets…'));
    setError(null);
    try {
      const data = await finalizeSession(sessionId, decisions, {}, force);
      setResult(data.summary);
      setFinalized(data);
      setView('dashboard');
      window.scrollTo({ top: 0 });
    } catch (err) {
      setError(friendlyError(err, 'We could not make the cutting plan. Please try again.'));
    } finally {
      setBusy(null);
    }
  };

  const handleReset = () => {
    if (view !== 'upload' && !window.confirm('Start a new job? The current one will be cleared.')) return;
    setView('upload');
    setExtractData(null);
    setDecisions({});
    setResult(null);
    setFinalized(null);
    setSessionId('');
    setError(null);
    setChatOpen(false);
  };

  // --- SaaS routing --------------------------------------------------------
  if (authState === 'unknown') {
    return (
      <div className="app" style={{ alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <LoaderCircle size={36} className="spinner" style={{ color: 'var(--primary)' }} />
      </div>
    );
  }

  if (authState === 'saas' && user) {
    return (
      <div className="app">
        <ProjectsView
          user={user}
          onSignOut={() => {
            clearSaasToken();
            setUser(null);
            setAuthState('anon');
          }}
        />
      </div>
    );
  }

  if (authState === 'anon') {
    return (
      <div className="app">
        <header className="topbar">
          <div className="topbar-inner">
            <div className="brand">
              <span className="brand-mark" aria-hidden="true"><LayoutGrid size={20} /></span>
              <span className="brand-name">CutList</span>
            </div>
            <div className="topbar-actions">
            <LanguageSwitch />
              <button type="button" className="btn btn-ghost" onClick={() => setAuthState('auth')}>
                <LogIn size={18} /> {t('Sign in')}
              </button>
            </div>
          </div>
        </header>
        <LandingView onOpenApp={() => setAuthState('auth')} />
      </div>
    );
  }

  if (authState === 'auth') {
    return (
      <div className="app">
        <AuthView
          onAuthed={(u) => {
            setUser(u);
            setAuthState('saas');
          }}
          onTryWithoutAccount={() => setAuthState('legacy')}
        />
      </div>
    );
  }

  // --- Legacy anonymous flow (upload → review → dashboard) -----------------

  const currentIndex = STEPS.findIndex(s => s.view === view);
  const canGoTo = (target: AppView) => target === 'review' && view === 'dashboard' && !!extractData;

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true"><LayoutGrid size={20} /></span>
            <span className="brand-name">CutList</span>
          </div>

          <nav className="stepper" aria-label={t('Progress')}>
            {STEPS.map((step, i) => {
              const state = i < currentIndex ? 'is-done' : i === currentIndex ? 'is-current' : '';
              const clickable = canGoTo(step.view);
              return (
                <span key={step.view} style={{ display: 'contents' }}>
                  {i > 0 && <span className="step-line" aria-hidden="true" />}
                  <button
                    type="button"
                    className={`step ${state}`}
                    disabled={!clickable}
                    aria-current={i === currentIndex ? 'step' : undefined}
                    onClick={() => clickable && setView(step.view)}
                  >
                    <span className="step-dot">{i < currentIndex ? <Check size={16} /> : i + 1}</span>
                    <span className="step-label">{t(step.label)}</span>
                  </button>
                </span>
              );
            })}
          </nav>

          <div className="topbar-actions">
            <LanguageSwitch />
            {authState === 'legacy' && (
              <button type="button" className="btn btn-ghost" onClick={() => setAuthState('anon')}>
                <span className="brand-name">{t('Sign in')}</span>
              </button>
            )}
            {view === 'dashboard' && result && (
              <button type="button" className="btn btn-ghost" onClick={() => setChatOpen(true)}>
                <MessageCircle size={20} /> <span className="brand-name">{t('Ask')}</span>
              </button>
            )}
            {view !== 'upload' && (
              <button type="button" className="btn btn-ghost" onClick={handleReset} aria-label={t('Start a new job')}>
                <RotateCcw size={20} /> <span className="brand-name">{t('New job')}</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {view === 'upload' && (
        <UploadView onUploadFile={handleUpload} onDescribe={handleDescribe} error={error} busy={!!busy} />
      )}

      {view === 'review' && extractData && config && (
        <ReviewView
          data={extractData}
          config={config}
          decisions={decisions}
          onChange={setDecisions}
          onContinue={() => handleFinalize(false)}
          designNotes={designNotes}
          error={error}
          busy={!!busy}
        />
      )}

      {view === 'dashboard' && result && (
        <Dashboard
          result={result}
          finalized={finalized}
          designNotes={designNotes}
          onBackToParts={extractData ? () => setView('review') : undefined}
          onForce={() => handleFinalize(true)}
          error={error}
        />
      )}

      {busy && (
        <div className="overlay" role="alertdialog" aria-live="assertive" aria-label={busy}>
          <div className="busy">
            <LoaderCircle size={40} className="spinner" />
            <h2 style={{ marginTop: 12 }}>{busy}</h2>
            <p className="muted small" style={{ marginTop: 6 }}>{t('Large designs can take up to a minute.')}</p>
          </div>
        </div>
      )}

      {chatOpen && result && (
        <>
          <div className="overlay" style={{ zIndex: 65 }} onClick={() => setChatOpen(false)} />
          <ChatDrawer
            ask={async (question, history) => ({ reply: await aiChat(question, result, history, sessionId), proposals: [] })}
            onClose={() => setChatOpen(false)}
          />
        </>
      )}
    </div>
  );
}
