import React from 'react';
import { Package, Trash2, TrendingUp, Coins, Cpu, Download, ArrowLeft, Printer, LayoutGrid, ShieldAlert, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import SheetLayout from './SheetLayout';
import type { ProcessResult, FinalizeResult } from '../types';
import { downloadUrl } from '../api';

interface Props {
  result: ProcessResult;
  finalized?: FinalizeResult | null;
  sessionId?: string;
  onReset: () => void;
}

export default function Dashboard({ result, finalized, sessionId, onReset }: Props) {
  const ms = result.material_summary;
  const [activeTab, setActiveTab] = React.useState<'sheets' | 'cutlist'>('sheets');
  const [dismissedGate, setDismissedGate] = React.useState(false);
  const fixReport = result.model_fix_report;
  const isGated = fixReport && !fixReport.passes_gate;

  return (
    <div style={{ padding: 32, minHeight: '100%' }}>
      <div className="animate-slide-up" style={{ maxWidth: 1200, margin: '0 auto' }}>
        {/* Header */}
        <div className="flex items-center justify-between" style={{ marginBottom: 28 }}>
          <div>
            <h1 style={{ fontSize: '1.6rem' }}>
              <span className="text-gradient">Project Results</span>
            </h1>
            <p style={{ color: 'var(--text-secondary)', marginTop: 4, fontSize: 13 }}>
              Optimized for Indian manufacturing standards
            </p>
          </div>
          <div className="flex gap-2">
            <button className="btn btn-secondary" onClick={onReset}>
              <ArrowLeft size={14} /> New Project
            </button>
            <button className="btn btn-secondary" onClick={() => window.print()}>
              <Printer size={14} /> Print
            </button>
          </div>
        </div>

        {/* Model Quality Gate Banner */}
        {isGated && !dismissedGate && (
          <GateBanner fixReport={fixReport} onDismiss={() => setDismissedGate(true)} />
        )}

        {/* Stat Cards */}
        <div className="grid grid-5 gap-3 stagger" style={{ marginBottom: 28 }}>
          <StatCard
            icon={<Package size={18} />}
            label="Sheets Required"
            value={ms.sheet_count}
            iconBg="var(--accent-dim)"
            iconColor="var(--accent)"
          />
          <StatCard
            icon={<TrendingUp size={18} />}
            label="Utilization"
            value={`${ms.utilization_percent.toFixed(1)}%`}
            iconBg="var(--accent-dim)"
            iconColor="var(--accent)"
            accent={ms.utilization_percent >= 80 ? 'var(--accent)' : 'var(--warning)'}
          />
          <StatCard
            icon={<Trash2 size={18} />}
            label="Waste"
            value={`${ms.waste_percent.toFixed(1)}%`}
            iconBg="var(--danger-bg)"
            iconColor="var(--danger)"
            accent={ms.waste_percent <= 15 ? 'var(--accent)' : 'var(--danger)'}
          />
          <StatCard
            icon={<LayoutGrid size={18} />}
            label="Reusable Offcuts"
            value={`${ms.reusable_offcut_area.toFixed(2)} m²`}
            iconBg="var(--info-bg)"
            iconColor="var(--info)"
          />
          <StatCard
            icon={<Coins size={18} />}
            label="Est. Material Cost"
            value={`₹${ms.total_material_cost.toFixed(0)}`}
            iconBg="var(--warning-bg)"
            iconColor="var(--warning)"
          />
        </div>

        {/* AI Insights */}
        {result.ai_advice && (
          <div className="card card-glow animate-in" style={{ padding: 24, marginBottom: 28 }}>
            <div className="flex items-center gap-2" style={{ marginBottom: 16 }}>
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                background: 'var(--accent-dim)', color: 'var(--accent)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Cpu size={16} />
              </div>
              <div>
                <h3 style={{ fontSize: 14 }}>AI Expert Insights</h3>
                <p style={{ fontSize: 11, color: 'var(--text-dim)' }}>Powered by Groq LLM</p>
              </div>
            </div>
            <div className="chat-md" style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.7 }}>
              <ReactMarkdown>{result.ai_advice}</ReactMarkdown>
            </div>
          </div>
        )}

        {/* Download Artifacts */}
        {finalized && finalized.artifacts.length > 0 && sessionId && (
          <div className="card animate-in" style={{ padding: 20, marginBottom: 28 }}>
            <h3 className="flex items-center gap-2" style={{ marginBottom: 14 }}>
              <Download size={16} /> Download Artifacts
            </h3>
            <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
              {finalized.artifacts.map((a, i) => (
                <a
                  key={i}
                  href={downloadUrl(sessionId, a.name)}
                  download
                  className="btn btn-secondary btn-sm"
                  style={{ textDecoration: 'none' }}
                >
                  <Download size={12} /> {a.name}
                </a>
              ))}
            </div>
          </div>
        )}

        {/* Tabs: Sheets / Cutlist */}
        <div className="flex items-center justify-between" style={{ marginBottom: 20 }}>
          <div className="tab-group" style={{ width: 260 }}>
            <button className={`tab-item ${activeTab === 'sheets' ? 'active' : ''}`} onClick={() => setActiveTab('sheets')}>
              Sheet Layouts
            </button>
            <button className={`tab-item ${activeTab === 'cutlist' ? 'active' : ''}`} onClick={() => setActiveTab('cutlist')}>
              Cut List ({result.cutlist.length})
            </button>
          </div>
        </div>

        {activeTab === 'sheets' ? (
          <div className="flex flex-col gap-6">
            {result.sheets.map(sheet => (
              <SheetLayout key={sheet.sheet_id} sheet={sheet} boards={result.boards} />
            ))}
            {result.sheets.length === 0 && (
              <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)' }}>
                No sheet layouts generated
              </div>
            )}
          </div>
        ) : (
          <div className="card" style={{ overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
              <table className="review-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Part</th>
                    <th>Length</th>
                    <th>Width</th>
                    <th>Thickness</th>
                    <th>Qty</th>
                    <th>Material</th>
                  </tr>
                </thead>
                <tbody>
                  {result.cutlist.map((item, i) => (
                    <tr key={item.id || i}>
                      <td className="mono" style={{ color: 'var(--text-dim)' }}>{i + 1}</td>
                      <td style={{ fontWeight: 600 }}>
                        {item.labels?.[0] || item.id}
                      </td>
                      <td className="mono">{Math.round(item.length)} mm</td>
                      <td className="mono">{Math.round(item.width)} mm</td>
                      <td className="mono">{item.thickness} mm</td>
                      <td>
                        <span className="badge badge-neutral">×{item.quantity}</span>
                      </td>
                      <td style={{ color: 'var(--text-dim)', fontSize: 12 }}>{item.material}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, iconBg, iconColor, accent }: {
  icon: React.ReactNode; label: string; value: string | number;
  iconBg: string; iconColor: string; accent?: string;
}) {
  return (
    <div className="card stat-card">
      <div className="stat-icon" style={{ background: iconBg, color: iconColor }}>
        {icon}
      </div>
      <div>
        <div className="stat-value" style={accent ? { color: accent } : {}}>{value}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  );
}

function GateBanner({ fixReport, onDismiss }: { fixReport: any; onDismiss: () => void }) {
  const conf = Math.round((fixReport?.confidence || 0) * 100);
  const thresh = Math.round((fixReport?.confidence_threshold || 60) * 100);
  return (
    <div className="animate-in" style={{
      padding: '16px 20px', marginBottom: 24, borderRadius: 12,
      border: '1px solid var(--danger)',
      background: 'color-mix(in srgb, var(--danger) 8%, var(--surface))',
      position: 'relative',
    }}>
      <button onClick={onDismiss} className="btn btn-icon btn-sm btn-ghost"
        style={{ position: 'absolute', top: 12, right: 12, opacity: 0.6 }} title="Dismiss">
        <X size={14} />
      </button>
      <div className="flex items-center gap-3" style={{ marginBottom: 12 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: 'var(--danger-bg)', color: 'var(--danger)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <ShieldAlert size={18} />
        </div>
        <div>
          <h3 style={{ fontSize: 14, color: 'var(--danger)', margin: 0 }}>
            Model Quality Gate Failed
          </h3>
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '2px 0 0' }}>
            Extraction confidence {conf}% is below the {thresh}% threshold — cutlist is not production-ready
          </p>
        </div>
      </div>
      {fixReport?.issues?.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--danger)', marginBottom: 6,
            textTransform: 'uppercase', letterSpacing: '0.05em' }}>Issues</div>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {fixReport.issues.map((issue: string, i: number) => (
              <li key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4,
                paddingLeft: 16, position: 'relative' }}>
                <span style={{ position: 'absolute', left: 0, color: 'var(--danger)' }}>✕</span>
                {issue}
              </li>
            ))}
          </ul>
        </div>
      )}
      {fixReport?.recommendations?.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent)', marginBottom: 6,
            textTransform: 'uppercase', letterSpacing: '0.05em' }}>How to Fix</div>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {fixReport.recommendations.map((rec: string, i: number) => (
              <li key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4,
                paddingLeft: 16, position: 'relative' }}>
                <span style={{ position: 'absolute', left: 0, color: 'var(--accent)' }}>→</span>
                {rec}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
