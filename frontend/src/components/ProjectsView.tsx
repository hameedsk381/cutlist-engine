import { useCallback, useEffect, useRef, useState } from 'react';
import { getLanguage, t } from '../i18n';
import {
  ChevronLeft, Check, Clock, Copy, FileText, FolderOpen, KeyRound,
  LoaderCircle, LogOut, MailWarning, PackagePlus, Plus, RotateCcw, Share2, Sparkles, Trash2, TriangleAlert, Ruler,
} from 'lucide-react';
import UploadView from './UploadView';
import Dashboard from './Dashboard';
import LanguageSwitch from './LanguageSwitch';
import LinearView from './LinearView';
import ChatDrawer from './ChatDrawer';
import { EdgeBandingCard, QuoteCard } from './PlanTools';
import {
  aiAvailable, artifactDownloadUrl, askAssistant, createApiKey, createProject, createProjectFromDescription, deleteOffcut, updateProjectSettings, friendlyError, getProject,
  listApiKeys, listOffcuts, listProjects, rerunProject, resendVerification, revokeApiKey,
  saveProjectOffcuts, shareProject,
} from '../api';
import type {
  FinalizeResult, ProcessConfig, ProcessResult, SaaSApiKey, SaaSApiKeyCreated,
  SaaSJob, SaaSOffcutList, SaaSProject, SaaSUser, PartOverrides, QuoteInput, QuoteTotals, AssistantProposal,
} from '../types';

interface Props {
  user: SaaSUser;
  onSignOut: () => void;
}

type Stage = 'list' | 'new' | 'job' | 'dashboard' | 'linear';

const POLL_MS = 2500;
const ASSISTANT_SUGGESTIONS = [
  'Check this plan for problems',
  'Put tape on the front edge of every part',
  'Write a WhatsApp message for my customer',
  'How many sheets for 3 of these?',
];

function statusTag(status: string) {
  if (status === 'done') return <span className="tag tag-ok">{t('Ready')}</span>;
  if (status === 'failed') return <span className="tag tag-warn">{t('Failed')}</span>;
  if (status === 'processing') return <span className="tag tag-muted">{t('Processing…')}</span>;
  return <span className="tag tag-muted">{t('Queued')}</span>;
}

export default function ProjectsView({ user, onSignOut }: Props) {
  const [stage, setStage] = useState<Stage>('list');
  const [projects, setProjects] = useState<SaaSProject[]>([]);
  const [active, setActive] = useState<{ id: number; name: string } | null>(null);
  const [result, setResult] = useState<ProcessResult | null>(null);
  const [finalized, setFinalized] = useState<FinalizeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [quote, setQuote] = useState<QuoteInput | null>(null);
  const [savedOverrides, setSavedOverrides] = useState<PartOverrides>({});
  const [quoteTotals, setQuoteTotals] = useState<QuoteTotals | null>(null);
  const [loaded, setLoaded] = useState(false);
  const pollRef = useRef<number | null>(null);

  // --- AI: shown only when the server has it switched on --------------------
  const [aiOn, setAiOn] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  useEffect(() => { void aiAvailable().then(setAiOn); }, []);

  // --- M3: verification banner, share links, API keys ----------------------
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [keysOpen, setKeysOpen] = useState(false);
  const [apiKeys, setApiKeys] = useState<SaaSApiKey[]>([]);
  const [newKey, setNewKey] = useState<SaaSApiKeyCreated | null>(null);

  // --- M4: offcut shelf -----------------------------------------------------
  const [shelf, setShelf] = useState<SaaSOffcutList | null>(null);
  const [useOffcuts, setUseOffcuts] = useState(false);

  const refreshShelf = useCallback(async () => {
    try {
      const data = await listOffcuts();
      setShelf(data);
    } catch {
      setShelf(null); // shelf is optional — never block a project over it
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const refreshList = useCallback(async () => {
    try {
      setProjects(await listProjects());
    } catch (err) {
      setError(friendlyError(err, 'Could not load your projects.'));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => { void refreshList(); }, [refreshList]);

  const openDashboard = useCallback((projectId: number, job: SaaSJob | null) => {
    void (async () => {
      const detail = await getProject(projectId);
      if (!detail.result) return;
      setActive({ id: detail.id, name: detail.name });
      setResult(detail.result);
      setQuote(detail.settings?.quote ?? null);
      setSavedOverrides(detail.settings?.overrides ?? {});
      setQuoteTotals(detail.quote_totals ?? null);
      setFinalized({
        gated: !!job?.gated,
        artifacts: (job?.artifacts ?? []).map((a) => ({
          name: a.name,
          url: artifactDownloadUrl(projectId, a.path),
        })),
        summary: detail.result,
      });
      setStage('dashboard');
      window.scrollTo({ top: 0 });
    })();
  }, []);

  const startPolling = useCallback((projectId: number) => {
    stopPolling();
    pollRef.current = window.setInterval(() => {
      void (async () => {
        try {
          const detail = await getProject(projectId);
          const job = detail.job;
          if (!job) return;
          if (job.status === 'done') {
            stopPolling();
            openDashboard(projectId, job);
          } else if (job.status === 'failed') {
            stopPolling();
            setError(job.error || 'Processing failed.');
            void refreshList();
            setStage('list');
          }
        } catch {
          /* transient network blips: keep polling */
        }
      })();
    }, POLL_MS);
  }, [openDashboard, refreshList, stopPolling]);

  const [designNotes, setDesignNotes] = useState<string[]>([]);

  const handleNewProject = (file: File, cfg: ProcessConfig) => {
    setDesignNotes([]);
    setBusy(t('Uploading your design…'));
    setError(null);
    void (async () => {
      try {
        const project = await createProject(file, file.name.replace(/\.[^.]+$/, ''), { ...cfg }, useOffcuts);
        setUseOffcuts(false); // the shelf claim happens on the server for this project only
        setActive({ id: project.id, name: project.name });
        setStage('job');
        startPolling(project.id);
      } catch (err) {
        setError(friendlyError(err, 'We could not process that file. Try again.'));
        setStage('list');
      } finally {
        setBusy(null);
      }
    })();
  };

  const handleDescribeProject = (description: string, cfg: ProcessConfig) => {
    setBusy(t('Working out the parts from your description…'));
    setError(null);
    void (async () => {
      try {
        const { project, notes } = await createProjectFromDescription(description, { ...cfg }, useOffcuts);
        setUseOffcuts(false);
        setDesignNotes(notes);
        setActive({ id: project.id, name: project.name });
        setStage('job');
        startPolling(project.id);
      } catch (err) {
        // Stay on the form so the description can be corrected.
        setError(friendlyError(err, 'We could not turn that description into parts. Give the height, width and depth in mm.'));
      } finally {
        setBusy(null);
      }
    })();
  };

  const handleApplyBanding = (overrides: PartOverrides) => {
    if (!active) return;
    setBusy(t('Updating the cutting plan…'));
    setError(null);
    void (async () => {
      try {
        const r = await updateProjectSettings(active.id, { overrides });
        if (r.rerun) {
          setResult(null);
          setFinalized(null);
          setStage('job');
          startPolling(active.id);
        }
      } catch (err) {
        setError(friendlyError(err, 'Could not save the part settings. Try again.'));
      } finally {
        setBusy(null);
      }
    })();
  };

  const handleSaveQuote = (next: QuoteInput | null) => {
    if (!active) return;
    setBusy(t('Saving the quote…'));
    setError(null);
    void (async () => {
      try {
        const r = await updateProjectSettings(active.id, { quote: next });
        setQuote(r.project.settings?.quote ?? null);
        setQuoteTotals(r.project.quote_totals ?? null);
      } catch (err) {
        setError(friendlyError(err, 'Could not save the quote. Check the amounts and try again.'));
      } finally {
        setBusy(null);
      }
    })();
  };

  const handleApplyProposal = (proposal: AssistantProposal) => {
    if (proposal.type === 'overrides') {
      setAssistantOpen(false); // the plan is made again, so this screen is replaced
      handleApplyBanding(proposal.overrides);
    } else {
      handleSaveQuote(proposal.quote);
    }
  };

  const handleRerun = (projectId: number) => {
    setBusy(t('Queuing a fresh run…'));
    setError(null);
    void (async () => {
      try {
        await rerunProject(projectId);
        setActive({ id: projectId, name: active?.name ?? 'Project' });
        setResult(null);
        setFinalized(null);
        setStage('job');
        startPolling(projectId);
      } catch (err) {
        setError(friendlyError(err, 'Could not start a new run.'));
      } finally {
        setBusy(null);
      }
    })();
  };

  const backToList = () => {
    stopPolling();
    setStage('list');
    setAssistantOpen(false);
    setActive(null);
    setResult(null);
    setFinalized(null);
    void refreshList();
  };

  const handleResendVerification = async () => {
    setBusy(t('Sending the verification email…'));
    setError(null);
    try {
      const r = await resendVerification();
      setNotice(r.verified
        ? 'Your email is already verified.'
        : 'Verification email sent — check your inbox (and spam).');
    } catch (err) {
      setError(friendlyError(err, 'Could not send the email right now — try again later.'));
    } finally {
      setBusy(null);
    }
  };

  const handleShare = async (projectId: number) => {
    setError(null);
    try {
      const { share_url } = await shareProject(projectId);
      const full = `${window.location.origin}${share_url}`;
      try {
        await navigator.clipboard.writeText(full);
        setNotice(`Share link copied to clipboard: ${full}`);
      } catch {
        setNotice(`Anyone with this link can view the plan: ${full}`);
      }
    } catch (err) {
      setError(friendlyError(err, 'Could not create the share link.'));
    }
  };

  const refreshKeys = useCallback(async () => {
    try {
      setApiKeys(await listApiKeys());
    } catch {
      /* banner-level error already covers auth problems */
    }
  }, []);

  useEffect(() => {
    if (keysOpen) void refreshKeys();
  }, [keysOpen, refreshKeys]);

  const handleCreateKey = async () => {
    setBusy(t('Creating API key…'));
    setError(null);
    try {
      const key = await createApiKey(`Key ${apiKeys.length + 1}`);
      setNewKey(key);
      await refreshKeys();
    } catch (err) {
      setError(friendlyError(err, 'Could not create the API key.'));
    } finally {
      setBusy(null);
    }
  };

  const handleRevokeKey = async (id: number) => {
    setError(null);
    try {
      await revokeApiKey(id);
      if (newKey?.id === id) setNewKey(null);
      await refreshKeys();
    } catch (err) {
      setError(friendlyError(err, 'Could not revoke the key.'));
    }
  };

  // --- M4: offcut shelf actions --------------------------------------------

  const startNewProject = () => {
    setError(null);
    setUseOffcuts(false);
    setStage('new');
    void refreshShelf();
  };

  const handleSaveOffcuts = async (projectId: number) => {
    setError(null);
    try {
      const saved = await saveProjectOffcuts(projectId);
      setNotice(saved > 0
        ? `Saved ${saved} leftover ${saved === 1 ? 'piece' : 'pieces'} to your offcut shelf.`
        : 'No reusable leftovers big enough to save on this one.');
      await refreshShelf();
    } catch (err) {
      setError(friendlyError(err, 'Could not save the offcuts.'));
    }
  };

  const handleDeleteOffcut = async (id: number) => {
    setError(null);
    try {
      await deleteOffcut(id);
      await refreshShelf();
    } catch (err) {
      setError(friendlyError(err, 'Could not discard that piece.'));
    }
  };

  if (stage === 'new') {
    return (
      <main className="page">
        <button type="button" className="btn btn-ghost" onClick={backToList}>
          <ChevronLeft size={20} /> {t('Your projects')}
        </button>
        <UploadView
          onUploadFile={handleNewProject}
          onDescribe={handleDescribeProject}
          error={error}
          busy={!!busy}
          offcutShelf={shelf && shelf.count > 0 ? { count: shelf.count, totalAreaM2: shelf.total_area_m2 } : undefined}
          useOffcuts={useOffcuts}
          onUseOffcutsChange={setUseOffcuts}
          aiEnabled={aiOn}
        />
        {busy && (
          <div className="overlay" role="alertdialog" aria-live="assertive" aria-label={busy}>
            <div className="busy">
              <LoaderCircle size={40} className="spinner" />
              <h2 style={{ marginTop: 12 }}>{busy}</h2>
            </div>
          </div>
        )}
      </main>
    );
  }

  if (stage === 'job') {
    return (
      <main className="page page-narrow">
        <button type="button" className="btn btn-ghost" onClick={backToList}>
          <ChevronLeft size={20} /> {t('Your projects')}
        </button>
        <section className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <LoaderCircle size={44} className="spinner" style={{ color: 'var(--primary)' }} />
          <h2 style={{ marginTop: 16 }}>{t('Making the cutting plan…')}</h2>
          <p className="muted">{active?.name}</p>
          <p className="muted small" style={{ marginTop: 8 }}>
            Finding parts, nesting sheets, writing DXF and G-code.
            You can leave this page — the plan will be in your projects when it is ready.
          </p>
        </section>
      </main>
    );
  }

  if (stage === 'dashboard' && result && active) {
    return (
      <main className="page">
        <button type="button" className="btn btn-ghost" onClick={backToList}>
          <ChevronLeft size={20} /> {t('Your projects')}
        </button>
        <Dashboard
          result={result}
          finalized={finalized}
          designNotes={designNotes}
          tools={finalized?.gated ? undefined : (
            <>
              <EdgeBandingCard key={`band-${active.id}`} result={result} saved={savedOverrides} onApply={handleApplyBanding} busy={!!busy} />
              <QuoteCard key={`quote-${active.id}-${JSON.stringify(quote)}`} result={result} saved={quote} totals={quoteTotals} onSave={handleSaveQuote} busy={!!busy} />
            </>
          )}
          onForce={() => handleRerun(active.id)}
          error={error}
        />
        {aiOn && !finalized?.gated && !assistantOpen && (
          <button type="button" className="fab no-print" onClick={() => setAssistantOpen(true)}>
            <Sparkles size={20} /> {t('Ask AI')}
          </button>
        )}
        {assistantOpen && (
          <>
            <div className="overlay" style={{ zIndex: 65 }} onClick={() => setAssistantOpen(false)} />
            <ChatDrawer
              key={`chat-${active.id}`}
              ask={(question, history) => askAssistant(active.id, question, history, getLanguage())}
              onApply={handleApplyProposal}
              suggestions={ASSISTANT_SUGGESTIONS}
              onClose={() => setAssistantOpen(false)}
            />
          </>
        )}
      </main>
    );
  }

  if (stage === 'linear') return <LinearView onBack={backToList} />;

  // ---- list ----
  return (
    <main className="page">
      <div className="page-head row">
        <div>
          <h1>{t('Your projects')}</h1>
          <p className="muted">Signed in as {user.email} · {user.plan} plan</p>
        </div>
        <div className="spacer" />
        <LanguageSwitch />
        <button type="button" className="btn btn-ghost" onClick={onSignOut}>
          <LogOut size={18} /> {t('Sign out')}
        </button>
        <button type="button" className="btn" onClick={() => setStage('linear')}>
          <Ruler size={18} /> {t('Cut lengths')}
        </button>
        <button type="button" className="btn btn-primary" onClick={startNewProject}>
          <Plus size={18} /> {t('New project')}
        </button>
      </div>

      {error && <div className="notice notice-danger"><TriangleAlert size={20} /> {error}</div>}
      {notice && (
        <div className="notice notice-info" role="status">
          <Check size={20} /> <span className="share-notice-text">{notice}</span>
          <button type="button" className="linklike" onClick={() => setNotice(null)}>{t('Dismiss')}</button>
        </div>
      )}
      {!user.email_verified && !bannerDismissed && (
        <div className="notice notice-warn">
          <MailWarning size={20} />
          <span>
            Verify your email so you can recover your account.
            We sent a link to <strong>{user.email}</strong>.
          </span>
          <button type="button" className="linklike" onClick={handleResendVerification} disabled={!!busy}>
            {t('Resend email')}
          </button>
          <button type="button" className="linklike muted" onClick={() => setBannerDismissed(true)}>
            {t('Dismiss')}
          </button>
        </div>
      )}

      {projects.length === 0 && loaded ? (
        <section className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <FolderOpen size={40} style={{ color: 'var(--text-2)' }} />
          <h2 style={{ marginTop: 12 }}>{t('No projects yet')}</h2>
          <p className="muted">{t('Upload a 3D model to get your first cutting plan.')}</p>
          <button type="button" className="btn btn-primary btn-lg" style={{ marginTop: 16 }}
                  onClick={startNewProject}>
            <Plus size={18} /> {t('New project')}
          </button>
        </section>
      ) : projects.length === 0 ? (
        <div className="row" style={{ justifyContent: 'center', padding: '40px 0' }}>
          <LoaderCircle size={28} className="spinner" style={{ color: 'var(--primary)' }} />
        </div>
      ) : (
        <div className="stack">
          {projects.map((p) => (
            <section key={p.id} className="card card-flat project-row">
              <div className="row">
                <div>
                  <strong>{p.name}</strong>
                  <p className="muted small">
                    <FileText size={13} /> {p.original_filename}
                    {p.created_at && (
                      <><Clock size={13} /> {new Date(p.created_at).toLocaleDateString()}</>
                    )}
                  </p>
                </div>
                <div className="spacer" />
                {statusTag(p.job?.status ?? 'queued')}
                {p.job?.status === 'done' && (
                  <>
                    <button type="button" className="btn" onClick={() => handleShare(p.id)} aria-label={t('Copy share link')}>
                      <Share2 size={16} /> {t('Share')}
                    </button>
                    <button type="button" className="btn" onClick={() => handleSaveOffcuts(p.id)} aria-label={t('Save reusable offcuts')}>
                      <PackagePlus size={16} /> {t('Save offcuts')}
                    </button>
                    <button type="button" className="btn" onClick={() => openDashboard(p.id, p.job)}>
                      {t('Open plan')}
                    </button>
                  </>
                )}
                {(p.job?.status === 'done' || p.job?.status === 'failed') && (
                  <button type="button" className="btn" onClick={() => handleRerun(p.id)} aria-label={t('Run again')}>
                    <RotateCcw size={16} />
                  </button>
                )}
              </div>
              {p.job?.status === 'failed' && p.job.error && (
                <p className="muted small" style={{ color: 'var(--warn)', marginTop: 8 }}>{p.job.error}</p>
              )}
            </section>
          ))}
        </div>
      )}

      {/* ---- Offcut shelf (M4: leftovers from one plan become the next one's free stock) ---- */}
      {shelf && shelf.count > 0 && (
        <section className="card keys-panel">
          <div className="row">
            <PackagePlus size={20} style={{ color: 'var(--text-2)' }} />
            <h2 style={{ margin: 0 }}>{t('Offcut shelf')}</h2>
            <span className="muted small">
              {shelf.count} {shelf.count === 1 ? 'piece' : 'pieces'} · {shelf.total_area_m2.toFixed(2)} m² — reused free when you tick “Use my offcut shelf”
            </span>
            <div className="spacer" />
          </div>
          <table className="keys-table">
            <thead>
              <tr><th>{t('Size')}</th><th>{t('Thickness')}</th><th>{t('Area')}</th><th /></tr>
            </thead>
            <tbody>
              {shelf.offcuts.map((o) => (
                <tr key={o.id}>
                  <td>{Math.round(o.length)} × {Math.round(o.width)} mm</td>
                  <td>{o.thickness} mm</td>
                  <td>{o.area_m2.toFixed(2)} m²</td>
                  <td>
                    <button type="button" className="btn" onClick={() => handleDeleteOffcut(o.id)} aria-label={t('Discard offcut')}>
                      <Trash2 size={16} /> {t('Discard')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* ---- API keys (programmatic access for CNC shops) ---- */}
      <section className="card keys-panel">
        <div className="row">
          <KeyRound size={20} style={{ color: 'var(--text-2)' }} />
          <h2 style={{ margin: 0 }}>{t('API keys')}</h2>
          <span className="muted small">{t('Let your CNC software pull plans on its own')}</span>
          <div className="spacer" />
          <button type="button" className="btn" onClick={() => setKeysOpen(!keysOpen)}>
            {keysOpen ? 'Hide' : 'Manage'}
          </button>
        </div>
        {keysOpen && (
          <div className="stack" style={{ marginTop: 16 }}>
            {newKey && (
              <div className="notice notice-warn key-reveal">
                <div>
                  <strong>{t('Copy your new key now — it will not be shown again:')}</strong>
                  <code className="key-code">{newKey.key}</code>
                </div>
                <button
                  type="button"
                  className="btn"
                  onClick={async () => {
                    try { await navigator.clipboard.writeText(newKey.key); setNotice('API key copied to clipboard.'); } catch { /* clipboard blocked */ }
                  }}
                >
                  <Copy size={16} /> {t('Copy')}
                </button>
              </div>
            )}
            {apiKeys.length === 0 && !newKey ? (
              <p className="muted small">{t('No keys yet. A key lets scripts and CNC software call the CutList API without your password.')}</p>
            ) : (
              <table className="keys-table">
                <thead>
                  <tr><th>{t('Name')}</th><th>{t('Key')}</th><th>{t('Created')}</th><th>{t('Last used')}</th><th /></tr>
                </thead>
                <tbody>
                  {apiKeys.map((k) => (
                    <tr key={k.id}>
                      <td>{k.name}</td>
                      <td><code>{k.key_prefix}…</code></td>
                      <td>{k.created_at ? new Date(k.created_at).toLocaleDateString() : '—'}</td>
                      <td>{k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : 'Never'}</td>
                      <td>
                        <button type="button" className="btn" onClick={() => handleRevokeKey(k.id)} aria-label={`Revoke ${k.name}`}>
                          <Trash2 size={16} /> {t('Revoke')}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button type="button" className="btn btn-primary" onClick={handleCreateKey} disabled={!!busy} style={{ alignSelf: 'flex-start' }}>
              <Plus size={18} /> {t('Create API key')}
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
