import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ChevronLeft, Check, Clock, Copy, FileText, FolderOpen, KeyRound,
  LoaderCircle, LogOut, MailWarning, Plus, RotateCcw, Share2, Trash2, TriangleAlert,
} from 'lucide-react';
import UploadView from './UploadView';
import Dashboard from './Dashboard';
import {
  artifactDownloadUrl, createApiKey, createProject, friendlyError, getProject,
  listApiKeys, listProjects, rerunProject, resendVerification, revokeApiKey,
  shareProject,
} from '../api';
import type {
  FinalizeResult, ProcessConfig, ProcessResult, SaaSApiKey, SaaSApiKeyCreated,
  SaaSJob, SaaSProject, SaaSUser,
} from '../types';

interface Props {
  user: SaaSUser;
  onSignOut: () => void;
}

type Stage = 'list' | 'new' | 'job' | 'dashboard';

const POLL_MS = 2500;

function statusTag(status: string) {
  if (status === 'done') return <span className="tag tag-ok">Ready</span>;
  if (status === 'failed') return <span className="tag tag-warn">Failed</span>;
  if (status === 'processing') return <span className="tag tag-muted">Processing…</span>;
  return <span className="tag tag-muted">Queued</span>;
}

export default function ProjectsView({ user, onSignOut }: Props) {
  const [stage, setStage] = useState<Stage>('list');
  const [projects, setProjects] = useState<SaaSProject[]>([]);
  const [active, setActive] = useState<{ id: number; name: string } | null>(null);
  const [result, setResult] = useState<ProcessResult | null>(null);
  const [finalized, setFinalized] = useState<FinalizeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const pollRef = useRef<number | null>(null);

  // --- M3: verification banner, share links, API keys ----------------------
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [keysOpen, setKeysOpen] = useState(false);
  const [apiKeys, setApiKeys] = useState<SaaSApiKey[]>([]);
  const [newKey, setNewKey] = useState<SaaSApiKeyCreated | null>(null);

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

  const handleNewProject = (file: File, cfg: ProcessConfig) => {
    setBusy('Uploading your design…');
    setError(null);
    void (async () => {
      try {
        const project = await createProject(file, file.name.replace(/\.[^.]+$/, ''), { ...cfg });
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

  const handleRerun = (projectId: number) => {
    setBusy('Queuing a fresh run…');
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
    setActive(null);
    setResult(null);
    setFinalized(null);
    void refreshList();
  };

  const handleResendVerification = async () => {
    setBusy('Sending the verification email…');
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
    setBusy('Creating API key…');
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

  if (stage === 'new') {
    return (
      <main className="page">
        <button type="button" className="btn btn-ghost" onClick={backToList}>
          <ChevronLeft size={20} /> Your projects
        </button>
        <UploadView
          onUploadFile={handleNewProject}
          onDescribe={() => { /* AI describe is part of the legacy flow for now */ }}
          error={error}
          busy={!!busy}
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
          <ChevronLeft size={20} /> Your projects
        </button>
        <section className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <LoaderCircle size={44} className="spinner" style={{ color: 'var(--primary)' }} />
          <h2 style={{ marginTop: 16 }}>Making the cutting plan…</h2>
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
          <ChevronLeft size={20} /> Your projects
        </button>
        <Dashboard
          result={result}
          finalized={finalized}
          fromDescription={false}
          onForce={() => handleRerun(active.id)}
          error={error}
        />
      </main>
    );
  }

  // ---- list ----
  return (
    <main className="page">
      <div className="page-head row">
        <div>
          <h1>Your projects</h1>
          <p className="muted">Signed in as {user.email} · {user.plan} plan</p>
        </div>
        <div className="spacer" />
        <button type="button" className="btn btn-ghost" onClick={onSignOut}>
          <LogOut size={18} /> Sign out
        </button>
        <button type="button" className="btn btn-primary" onClick={() => { setError(null); setStage('new'); }}>
          <Plus size={18} /> New project
        </button>
      </div>

      {error && <div className="notice notice-danger"><TriangleAlert size={20} /> {error}</div>}
      {notice && (
        <div className="notice notice-info" role="status">
          <Check size={20} /> <span className="share-notice-text">{notice}</span>
          <button type="button" className="linklike" onClick={() => setNotice(null)}>Dismiss</button>
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
            Resend email
          </button>
          <button type="button" className="linklike muted" onClick={() => setBannerDismissed(true)}>
            Dismiss
          </button>
        </div>
      )}

      {projects.length === 0 && loaded ? (
        <section className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <FolderOpen size={40} style={{ color: 'var(--text-2)' }} />
          <h2 style={{ marginTop: 12 }}>No projects yet</h2>
          <p className="muted">Upload a 3D model to get your first cutting plan.</p>
          <button type="button" className="btn btn-primary btn-lg" style={{ marginTop: 16 }}
                  onClick={() => { setError(null); setStage('new'); }}>
            <Plus size={18} /> New project
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
                    <button type="button" className="btn" onClick={() => handleShare(p.id)} aria-label="Copy share link">
                      <Share2 size={16} /> Share
                    </button>
                    <button type="button" className="btn" onClick={() => openDashboard(p.id, p.job)}>
                      Open plan
                    </button>
                  </>
                )}
                {(p.job?.status === 'done' || p.job?.status === 'failed') && (
                  <button type="button" className="btn" onClick={() => handleRerun(p.id)} aria-label="Run again">
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

      {/* ---- API keys (programmatic access for CNC shops) ---- */}
      <section className="card keys-panel">
        <div className="row">
          <KeyRound size={20} style={{ color: 'var(--text-2)' }} />
          <h2 style={{ margin: 0 }}>API keys</h2>
          <span className="muted small">Let your CNC software pull plans on its own</span>
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
                  <strong>Copy your new key now — it will not be shown again:</strong>
                  <code className="key-code">{newKey.key}</code>
                </div>
                <button
                  type="button"
                  className="btn"
                  onClick={async () => {
                    try { await navigator.clipboard.writeText(newKey.key); setNotice('API key copied to clipboard.'); } catch { /* clipboard blocked */ }
                  }}
                >
                  <Copy size={16} /> Copy
                </button>
              </div>
            )}
            {apiKeys.length === 0 && !newKey ? (
              <p className="muted small">No keys yet. A key lets scripts and CNC software call the CutList API without your password.</p>
            ) : (
              <table className="keys-table">
                <thead>
                  <tr><th>Name</th><th>Key</th><th>Created</th><th>Last used</th><th /></tr>
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
                          <Trash2 size={16} /> Revoke
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button type="button" className="btn btn-primary" onClick={handleCreateKey} disabled={!!busy} style={{ alignSelf: 'flex-start' }}>
              <Plus size={18} /> Create API key
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
