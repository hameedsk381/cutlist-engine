import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ChevronLeft, Clock, FileText, FolderOpen, LoaderCircle, LogOut,
  Plus, RotateCcw, TriangleAlert,
} from 'lucide-react';
import UploadView from './UploadView';
import Dashboard from './Dashboard';
import {
  artifactDownloadUrl, createProject, friendlyError, getProject,
  listProjects, rerunProject,
} from '../api';
import type { FinalizeResult, ProcessConfig, ProcessResult, SaaSJob, SaaSProject, SaaSUser } from '../types';

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
  const pollRef = useRef<number | null>(null);

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

      {projects.length === 0 ? (
        <section className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <FolderOpen size={40} style={{ color: 'var(--text-2)' }} />
          <h2 style={{ marginTop: 12 }}>No projects yet</h2>
          <p className="muted">Upload a 3D model to get your first cutting plan.</p>
          <button type="button" className="btn btn-primary btn-lg" style={{ marginTop: 16 }}
                  onClick={() => { setError(null); setStage('new'); }}>
            <Plus size={18} /> New project
          </button>
        </section>
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
                  <button type="button" className="btn" onClick={() => openDashboard(p.id, p.job)}>
                    Open plan
                  </button>
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
    </main>
  );
}
