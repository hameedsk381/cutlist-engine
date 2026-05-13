import React, { useRef, useState, useCallback } from 'react';
import { Upload, Zap, AlertCircle, Settings, ChevronDown, ChevronUp } from 'lucide-react';
import type { ProcessConfig } from '../types';

interface Props {
  onUploadFile: (file: File, config: ProcessConfig) => void;
  onDescribe: (desc: string, config: ProcessConfig) => void;
  loading: boolean;
  error: string | null;
}

const DEFAULT_CONFIG: ProcessConfig = {
  sheet_width: 2440,
  sheet_height: 1220,
  thickness: 18,
  kerf: 3,
  sheet_cost: 3500,
  currency: 'INR',
};

export default function UploadView({ onUploadFile, onDescribe, loading, error }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<'cad' | 'ai'>('cad');
  const [description, setDescription] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [config, setConfig] = useState<ProcessConfig>(DEFAULT_CONFIG);

  const updateConfig = (key: keyof ProcessConfig, val: string) => {
    const num = parseFloat(val);
    if (!isNaN(num)) setConfig(c => ({ ...c, [key]: num }));
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) onUploadFile(f, config);
  }, [config, onUploadFile]);

  return (
    <div style={{ minHeight: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div className="animate-slide-up" style={{ width: '100%', maxWidth: 640 }}>
        {/* Hero */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🪚</div>
          <h1>
            <span className="text-gradient">CutList</span> Engine
          </h1>
          <p style={{ color: 'var(--text-secondary)', marginTop: 8, fontSize: 15 }}>
            AI-powered plywood optimization for Indian modular furniture
          </p>
          <div className="flex items-center justify-center gap-2" style={{ marginTop: 12 }}>
            <span className="badge badge-success">v1.2</span>
            <span className="badge badge-info">Groq AI</span>
          </div>
        </div>

        {/* Main Card */}
        <div className="card" style={{ padding: 32 }}>
          {/* Mode Tabs */}
          <div className="tab-group" style={{ marginBottom: 24 }}>
            <button className={`tab-item ${mode === 'cad' ? 'active' : ''}`} onClick={() => setMode('cad')}>
              <Upload size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
              CAD Upload
            </button>
            <button className={`tab-item ${mode === 'ai' ? 'active' : ''}`} onClick={() => setMode('ai')}>
              <Zap size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
              AI Describe
            </button>
          </div>

          {mode === 'cad' ? (
            <div
              className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
              onClick={() => fileRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
            >
              <input
                type="file"
                ref={fileRef}
                accept=".obj,.stl,.dae,.dxf,.json"
                style={{ display: 'none' }}
                onChange={e => e.target.files?.[0] && onUploadFile(e.target.files[0], config)}
              />
              {loading ? (
                <div className="flex flex-col items-center gap-3">
                  <div className="spinner spinner-lg" />
                  <p style={{ color: 'var(--text-secondary)' }}>Processing model…</p>
                </div>
              ) : (
                <>
                  <Upload size={40} style={{ color: 'var(--text-dim)', marginBottom: 12 }} />
                  <h3 style={{ marginBottom: 4 }}>Drop your 3D model here</h3>
                  <p style={{ color: 'var(--text-dim)', fontSize: 13 }}>
                    OBJ, STL, DAE, DXF, JSON — up to 500 MB
                  </p>
                </>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <textarea
                className="input"
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="e.g., L-shaped Modular Kitchen with 18mm BWP Marine Plywood. Base cabinets 720mm high with 75mm skirting, 3 wall units 900mm wide…"
                style={{ minHeight: 140 }}
              />
              <button
                className="btn btn-primary btn-lg w-full"
                disabled={loading || !description.trim()}
                onClick={() => onDescribe(description, config)}
              >
                {loading ? (
                  <><div className="spinner" style={{ borderTopColor: '#000' }} /> Generating…</>
                ) : (
                  <><Zap size={18} /> Generate Cutlist from Description</>
                )}
              </button>
            </div>
          )}

          {/* Config Toggle */}
          <button
            className="btn btn-ghost w-full"
            style={{ marginTop: 16, justifyContent: 'space-between' }}
            onClick={() => setShowConfig(!showConfig)}
          >
            <span className="flex items-center gap-2">
              <Settings size={14} /> Sheet & Material Settings
            </span>
            {showConfig ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {showConfig && (
            <div className="config-grid animate-in" style={{ marginTop: 12 }}>
              {([
                ['sheet_width', 'Sheet Width (mm)'],
                ['sheet_height', 'Sheet Height (mm)'],
                ['thickness', 'Thickness (mm)'],
                ['kerf', 'Kerf (mm)'],
                ['sheet_cost', 'Sheet Cost (₹)'],
              ] as [keyof ProcessConfig, string][]).map(([key, label]) => (
                <div className="config-field" key={key}>
                  <label>{label}</label>
                  <input
                    className="input input-sm"
                    type="number"
                    value={config[key]}
                    onChange={e => updateConfig(key, e.target.value)}
                  />
                </div>
              ))}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 animate-in" style={{
              marginTop: 16, padding: 12, borderRadius: 'var(--radius-sm)',
              background: 'var(--danger-bg)', color: 'var(--danger)', fontSize: 13,
              border: '1px solid rgba(239,68,68,0.2)'
            }}>
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <p style={{ textAlign: 'center', marginTop: 24, fontSize: 12, color: 'var(--text-dim)' }}>
          Indian manufacturing standards • BWP/BWR plywood • Hettich/Hafele hardware
        </p>
      </div>
    </div>
  );
}
