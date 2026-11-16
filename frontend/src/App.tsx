import { useEffect, useState } from 'react';
import { Check, LayoutGrid, LoaderCircle, MessageCircle, RotateCcw } from 'lucide-react';
import UploadView from './components/UploadView';
import ReviewView from './components/ReviewView';
import Dashboard from './components/Dashboard';
import ChatDrawer from './components/ChatDrawer';
import AuthView from './components/AuthView';
import ProjectsView from './components/ProjectsView';
import {
  aiDescribe, clearSaasToken, extractBoards, finalizeSession, friendlyError, getSaasToken, saasMe,
} from './api';
import type {
  AppView, ExtractResult, FinalizeResult, ProcessConfig, ProcessResult, ReviewDecisions, SaaSUser,
} from './types';

const STEPS: { view: AppView; label: string }[] = [
  { view: 'upload', label: 'Add your design' },
  { view: 'review', label: 'Check the parts' },
  { view: 'dashboard', label: 'Cutting plan' },
];

export default function App() {
  const [view, setView] = useState<AppView>('upload');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // SaaS session: 'unknown' while we check for a stored token on load.
  const [authState, setAuthState] = useState<'unknown' | 'anon' | 'saas' | 'legacy'>('unknown');
  const [user, setUser] = useState<SaaSUser | null>(null);

  useEffect(() => {
    if (!getSaasToken()) {
      setAuthState('anon');
      return;
    }
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

  const handleUpload = async (file: File, cfg: ProcessConfig) => {
    setBusy('Reading your design and finding the parts…');
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
      setError(friendlyError(err, 'We could not read that file. Check it is a 3D export (OBJ, DAE, STL or DXF) and try again.'));
    } finally {
      setBusy(null);
    }
  };

  const handleDescribe = async (description: string, cfg: ProcessConfig) => {
    setBusy('Working out the parts from your description…');
    setError(null);
    try {
      const data = await aiDescribe(description, {
        thickness: cfg.thickness, sheet_width: cfg.sheet_width, sheet_height: cfg.sheet_height, kerf: cfg.kerf,
      });
      setConfig(cfg);
      setExtractData(null);
      setSessionId('');
      setResult(data);
      setFinalized(null);
      setView('dashboard');
    } catch (err) {
      setError(friendlyError(err, 'We could not turn that description into parts. Try adding the overall width, height and depth.'));
    } finally {
      setBusy(null);
    }
  };

  const handleFinalize = async (force = false) => {
    if (!sessionId) return;
    setBusy('Fitting the parts onto sheets…');
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

          <nav className="stepper" aria-label="Progress">
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
                    <span className="step-label">{step.label}</span>
                  </button>
                </span>
              );
            })}
          </nav>

          <div className="topbar-actions">
            {authState === 'legacy' && (
              <button type="button" className="btn btn-ghost" onClick={() => setAuthState('anon')}>
                <span className="brand-name">Sign in</span>
              </button>
            )}
            {view === 'dashboard' && result && (
              <button type="button" className="btn btn-ghost" onClick={() => setChatOpen(true)}>
                <MessageCircle size={20} /> <span className="brand-name">Ask</span>
              </button>
            )}
            {view !== 'upload' && (
              <button type="button" className="btn btn-ghost" onClick={handleReset} aria-label="Start a new job">
                <RotateCcw size={20} /> <span className="brand-name">New job</span>
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
          error={error}
          busy={!!busy}
        />
      )}

      {view === 'dashboard' && result && (
        <Dashboard
          result={result}
          finalized={finalized}
          fromDescription={!extractData}
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
            <p className="muted small" style={{ marginTop: 6 }}>Large designs can take up to a minute.</p>
          </div>
        </div>
      )}

      {chatOpen && result && (
        <>
          <div className="overlay" style={{ zIndex: 65 }} onClick={() => setChatOpen(false)} />
          <ChatDrawer context={result} sessionId={sessionId} onClose={() => setChatOpen(false)} />
        </>
      )}
    </div>
  );
}
