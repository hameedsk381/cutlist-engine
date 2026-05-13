import { useState } from 'react';
import { MessageSquare } from 'lucide-react';
import UploadView from './components/UploadView';
import ReviewView from './components/ReviewView';
import Dashboard from './components/Dashboard';
import ChatDrawer from './components/ChatDrawer';
import { extractBoards, finalizeSession, aiDescribe } from './api';
import type {
  AppView, ProcessConfig, ProcessResult,
  ExtractResult, FinalizeResult, ReviewDecisions,
} from './types';

export default function App() {
  const [view, setView] = useState<AppView>('upload');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Extract flow state
  const [extractData, setExtractData] = useState<ExtractResult | null>(null);
  const [sessionId, setSessionId] = useState<string>('');

  // Dashboard state
  const [result, setResult] = useState<ProcessResult | null>(null);
  const [finalized, setFinalized] = useState<FinalizeResult | null>(null);

  // Chat
  const [chatOpen, setChatOpen] = useState(false);

  // --- Handlers ---

  const handleUpload = async (file: File, config: ProcessConfig) => {
    setLoading(true);
    setError(null);
    try {
      const data = await extractBoards(file, {
        sheet_width: config.sheet_width,
        sheet_height: config.sheet_height,
        thickness: config.thickness,
        kerf: config.kerf,
        sheet_cost: config.sheet_cost,
        currency: config.currency,
      });
      setExtractData(data);
      setSessionId(data.session_id);
      setView('review');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Upload failed');
    } finally {
      setLoading(false);
    }
  };

  const handleDescribe = async (description: string, config: ProcessConfig) => {
    setLoading(true);
    setError(null);
    try {
      const data = await aiDescribe(description, {
        thickness: config.thickness,
        sheet_width: config.sheet_width,
        sheet_height: config.sheet_height,
        kerf: config.kerf,
      });
      setResult(data);
      setFinalized(null);
      setSessionId('');
      setView('dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'AI describe failed');
    } finally {
      setLoading(false);
    }
  };

  const handleFinalize = async (decisions: ReviewDecisions) => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await finalizeSession(sessionId, decisions);
      setResult(data.summary);
      setFinalized(data);
      setView('dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Finalize failed');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setView('upload');
    setExtractData(null);
    setResult(null);
    setFinalized(null);
    setSessionId('');
    setError(null);
    setChatOpen(false);
  };

  // --- Render ---

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Top nav bar */}
      <nav style={{
        height: 48, padding: '0 20px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--surface)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div className="flex items-center gap-2">
          <span style={{ fontSize: 20 }}>🪚</span>
          <span style={{ fontWeight: 700, fontSize: 14, letterSpacing: '-0.02em' }}>
            CutList Engine
          </span>
          <span className="badge badge-success" style={{ marginLeft: 4 }}>v1.2</span>
        </div>
        <div className="flex items-center gap-2">
          {view !== 'upload' && (
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => setChatOpen(true)}
            >
              <MessageSquare size={14} /> AI Chat
            </button>
          )}
        </div>
      </nav>

      {/* Main content */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {view === 'upload' && (
          <UploadView
            onUploadFile={handleUpload}
            onDescribe={handleDescribe}
            loading={loading}
            error={error}
          />
        )}

        {view === 'review' && extractData && (
          <ReviewView
            data={extractData}
            onFinalize={handleFinalize}
            onBack={handleReset}
            loading={loading}
          />
        )}

        {view === 'dashboard' && result && (
          <Dashboard
            result={result}
            finalized={finalized}
            sessionId={sessionId}
            onReset={handleReset}
          />
        )}
      </div>

      {/* Chat drawer */}
      {chatOpen && result && (
        <>
          <div
            style={{
              position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
              zIndex: 99, cursor: 'pointer',
            }}
            onClick={() => setChatOpen(false)}
          />
          <ChatDrawer
            context={result}
            sessionId={sessionId}
            onClose={() => setChatOpen(false)}
          />
        </>
      )}

      {/* Floating chat button */}
      {view === 'dashboard' && !chatOpen && (
        <button
          onClick={() => setChatOpen(true)}
          style={{
            position: 'fixed', bottom: 24, right: 24,
            width: 56, height: 56, borderRadius: '50%',
            background: 'var(--accent)', color: '#000',
            border: 'none', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 4px 20px rgba(16,185,129,0.3)',
            transition: 'transform 0.2s, box-shadow 0.2s',
            zIndex: 50,
          }}
          onMouseEnter={e => {
            e.currentTarget.style.transform = 'scale(1.1)';
            e.currentTarget.style.boxShadow = '0 6px 30px rgba(16,185,129,0.4)';
          }}
          onMouseLeave={e => {
            e.currentTarget.style.transform = 'scale(1)';
            e.currentTarget.style.boxShadow = '0 4px 20px rgba(16,185,129,0.3)';
          }}
        >
          <MessageSquare size={24} />
        </button>
      )}
    </div>
  );
}
