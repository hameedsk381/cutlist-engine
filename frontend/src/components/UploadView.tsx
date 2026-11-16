import { useEffect, useRef, useState } from 'react';
import { t } from '../i18n';
import type { DragEvent } from 'react';
import { ArrowRight, Camera, Info, Box, ChevronRight, CircleCheck, LoaderCircle, Mic, PenLine, Square, TriangleAlert, Upload, X } from 'lucide-react';
import { friendlyError, readSketch, transcribeSpeech } from '../api';
import type { ProcessConfig } from '../types';

interface Props {
  onUploadFile: (file: File, config: ProcessConfig) => void;
  onDescribe: (description: string, config: ProcessConfig) => void;
  error: string | null;
  busy: boolean;
  /** M4 offcut shelf — present only in the SaaS flow, when the shelf is non-empty. */
  offcutShelf?: { count: number; totalAreaM2: number };
  useOffcuts?: boolean;
  onUseOffcutsChange?: (value: boolean) => void;
  /** Shows the voice and sketch-photo buttons. Only when the server has AI on. */
  aiEnabled?: boolean;
}

const SHEETS = [
  { label: '8 × 4 ft', w: 2440, h: 1220 },
  { label: '7 × 4 ft', w: 2135, h: 1220 },
  { label: '6 × 4 ft', w: 1830, h: 1220 },
];
const THICKNESSES = [6, 12, 18, 25];
const ACCEPT = '.obj,.dae,.glb,.gltf,.step,.stp,.stl,.dxf,.json';
const EXAMPLES = [
  'Wardrobe 2100 high, 1200 wide, 600 deep, 2 shutters, 4 shelves',
  'Kitchen base unit 720 high, 600 wide, 560 deep, 1 shelf, 1 shutter',
  'Open bookshelf 1800 high, 800 wide, 300 deep, 5 shelves',
];

export default function UploadView({
  onUploadFile, onDescribe, error, busy,
  offcutShelf, useOffcuts = false, onUseOffcutsChange, aiEnabled = false,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<'file' | 'describe'>('file');
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [description, setDescription] = useState('');
  const [dragOver, setDragOver] = useState(false);

  // ---- AI helpers for the describe box. Both only fill in the text; the
  // person reads it, corrects it and then makes the plan as usual.
  const photoRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const [recording, setRecording] = useState(false);
  const [aiBusy, setAiBusy] = useState<string | null>(null);
  const [aiNote, setAiNote] = useState<{ kind: 'info' | 'danger'; text: string } | null>(null);
  const canRecord = typeof window !== 'undefined' && 'MediaRecorder' in window && !!navigator.mediaDevices?.getUserMedia;

  useEffect(() => () => { recorderRef.current?.stream.getTracks().forEach(track => track.stop()); }, []);

  const startRecording = async () => {
    setAiNote(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setAiNote({ kind: 'danger', text: t('We could not use the microphone. Allow it in your browser, then try again.') });
      return;
    }
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
    recorder.onstop = () => {
      stream.getTracks().forEach(track => track.stop());
      recorderRef.current = null;
      setRecording(false);
      const audio = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
      if (audio.size === 0) return;
      setAiBusy(t('Writing down what you said…'));
      transcribeSpeech(audio)
        .then(text => {
          setDescription(d => (d.trim() ? `${d.trim()} ${text}` : text));
          setAiNote({ kind: 'info', text: t('This is what we heard. Check the sizes and correct anything wrong.') });
        })
        .catch(err => setAiNote({ kind: 'danger', text: friendlyError(err, t('We could not hear that recording. Try again.')) }))
        .finally(() => setAiBusy(null));
    };
    recorderRef.current = recorder;
    recorder.start();
    setRecording(true);
    // A description is one or two sentences; stop a forgotten recording.
    window.setTimeout(() => { if (recorder.state === 'recording') recorder.stop(); }, 60_000);
  };

  const stopRecording = () => { if (recorderRef.current?.state === 'recording') recorderRef.current.stop(); };

  const pickPhoto = (photo: File | undefined) => {
    if (!photo) return;
    setAiNote(null);
    setAiBusy(t('Reading the sizes from your photo…'));
    readSketch(photo)
      .then(({ description: text, missing }) => {
        setDescription(text);
        setAiNote(missing.length > 0
          ? { kind: 'danger', text: `${t('We could not read every size. Add the missing ones:')} ${missing.map(m => t(m)).join(', ')}.` }
          : { kind: 'info', text: t('This is what we read from the photo. Check every size against your drawing.') });
      })
      .catch(err => setAiNote({ kind: 'danger', text: friendlyError(err, t('We could not read that photo. Try again in better light.')) }))
      .finally(() => setAiBusy(null));
  };

  const [sheet, setSheet] = useState({ w: 2440, h: 1220 });
  const [customSheet, setCustomSheet] = useState(false);
  const [thickness, setThickness] = useState(18);
  const [customThickness, setCustomThickness] = useState(false);
  const [sheetCost, setSheetCost] = useState(3500);
  const [kerf, setKerf] = useState(3);

  const config: ProcessConfig = {
    sheet_width: sheet.w, sheet_height: sheet.h, thickness, kerf, sheet_cost: sheetCost, currency: 'INR',
  };
  const settingsValid = sheet.w > 0 && sheet.h > 0 && thickness > 0 && kerf > 0 && sheetCost > 0;

  const pickFile = (f: File | undefined) => {
    if (!f) return;
    const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase();
    if (!ACCEPT.split(',').includes(ext)) {
      setFile(null);
      setFileError(`"${f.name}" is not a 3D file we can read. Export your design as OBJ, DAE, GLB, STL or DXF.`);
      return;
    }
    setFileError(null);
    setFile(f);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    pickFile(e.dataTransfer.files[0]);
  };

  const num = (v: string) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };
  const ready = settingsValid && (mode === 'file' ? !!file : description.trim().length >= 10);
  const submit = () => {
    if (!ready || busy) return;
    if (mode === 'file' && file) onUploadFile(file, config);
    else onDescribe(description.trim(), config);
  };

  return (
    <main className="page page-narrow fade-in">
      <div className="page-head">
        <h1>{t('What are you building?')}</h1>
        <p className="lead">{t('Add your furniture design and get a cutting plan: every part, how to cut each sheet, and how many sheets to buy.')}</p>
      </div>

      <div className="stack">
        <div className="choice-grid" role="group" aria-label="How do you want to add your design?">
          <button type="button" className="choice" aria-pressed={mode === 'file'} onClick={() => setMode('file')}>
            <span className="choice-icon"><Box size={24} /></span>
            <span><strong>{t('I have a 3D file')}</strong><span>{t('From SketchUp, Fusion, Blender…')}</span></span>
          </button>
          <button type="button" className="choice" aria-pressed={mode === 'describe'} onClick={() => setMode('describe')}>
            <span className="choice-icon"><PenLine size={24} /></span>
            <span><strong>{t('I\'ll describe it')}</strong><span>{t('Type the size, we work out the parts')}</span></span>
          </button>
        </div>

        {mode === 'file' ? (
          <section className="stack" aria-label="3D file">
            <input ref={fileRef} type="file" accept={ACCEPT} hidden onChange={e => { pickFile(e.target.files?.[0]); e.target.value = ''; }} />
            {file ? (
              <div className="file-chip">
                <CircleCheck size={24} color="var(--ok)" />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <strong>{file.name}</strong>
                  <div className="small muted">{file.size < 1048576 ? `${Math.max(1, Math.round(file.size / 1024))} KB` : `${(file.size / 1048576).toFixed(1)} MB`} · ready</div>
                </div>
                <button type="button" className="btn btn-ghost" onClick={() => fileRef.current?.click()}>{t('Change')}</button>
                <button type="button" className="icon-btn" aria-label={t('Remove file')} onClick={() => setFile(null)}><X size={20} /></button>
              </div>
            ) : (
              <button
                type="button"
                className={`dropzone ${dragOver ? 'is-over' : ''}`}
                onClick={() => fileRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
              >
                <span className="dropzone-icon"><Upload size={28} /></span>
                <strong style={{ fontSize: 18 }}>{t('Choose your 3D file')}</strong>
                <span className="muted">or drag it here · OBJ, DAE, GLB, STL or DXF</span>
              </button>
            )}
            {fileError && (
              <div className="notice notice-danger" role="alert"><TriangleAlert size={20} /><div>{fileError}</div></div>
            )}
            <details className="more">
              <summary><ChevronRight size={18} /> {t('How do I get this file from SketchUp?')}</summary>
              <div className="notice notice-info" style={{ marginTop: 8 }}>
                <div>
                  <ol style={{ margin: 0, paddingLeft: 20 }}>
                    <li>{t('Make every board its own')} <strong>group or component</strong>, drawn at its real thickness.</li>
                    <li>{t('Hide handles, hinges and screws.')}</li>
                    <li>{t('Go to')} <strong>{t('File → Export → 3D Model')}</strong> and save as <strong>{t('OBJ')}</strong> or <strong>{t('DAE')}</strong>, in millimetres.</li>
                  </ol>
                </div>
              </div>
            </details>
          </section>
        ) : (
          <section className="field" aria-label={t('Description')}>
            <label htmlFor="desc">{t('Describe the furniture')}</label>
            <textarea
              id="desc" className="textarea" value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder={t('Example: Wardrobe 2100 high, 1200 wide, 600 deep, 2 shutters, 4 shelves')}
            />
            <span className="field-help">{t('Give height, width and depth in mm, and how many shelves, shutters or drawers.')}</span>
            {aiEnabled && (
              <>
                <input ref={photoRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={e => { pickPhoto(e.target.files?.[0]); e.target.value = ''; }} />
                <div className="row ai-inputs">
                  {canRecord && (recording ? (
                    <button type="button" className="btn btn-danger is-recording" onClick={stopRecording}>
                      <Square size={18} /> {t('Stop and write it down')}
                    </button>
                  ) : (
                    <button type="button" className="btn" disabled={!!aiBusy} onClick={startRecording}>
                      <Mic size={18} /> {t('Say it')}
                    </button>
                  ))}
                  <button type="button" className="btn" disabled={!!aiBusy || recording} onClick={() => photoRef.current?.click()}>
                    <Camera size={18} /> {t('Photo of a sketch')}
                  </button>
                  {aiBusy && <span className="small muted row" role="status"><LoaderCircle size={16} className="spinner" /> {aiBusy}</span>}
                </div>
                <span className="field-help">{t('Speak or type in any language, or photograph a drawing with the sizes written on it.')}</span>
                {aiNote && (
                  <div className={`notice notice-${aiNote.kind}`} role={aiNote.kind === 'danger' ? 'alert' : 'status'}>
                    {aiNote.kind === 'danger' ? <TriangleAlert size={20} /> : <CircleCheck size={20} />}
                    <div className="small">{aiNote.text}</div>
                  </div>
                )}
              </>
            )}
            <div className="chips">
              {EXAMPLES.map(ex => (
                <button key={ex} type="button" className="chip" style={{ fontWeight: 500, fontSize: 14 }} onClick={() => setDescription(ex)}>
                  {ex.split(',')[0]}
                </button>
              ))}
            </div>
            <div className="notice notice-info">
              <Info size={20} />
              <div className="small">{t('We work out every panel with fixed carcass rules and show you the rules used. You check the parts before anything is cut.')}</div>
            </div>
          </section>
        )}

        <section className="card stack" aria-label={t('Your material')}>
          <h2>{t('Your plywood')}</h2>

          <div className="field">
            <span className="field-label" id="sheet-label">{t('Sheet size')}</span>
            <div className="chips" role="group" aria-labelledby="sheet-label">
              {SHEETS.map(s => (
                <button
                  key={s.label} type="button" className="chip"
                  aria-pressed={!customSheet && sheet.w === s.w && sheet.h === s.h}
                  onClick={() => { setCustomSheet(false); setSheet({ w: s.w, h: s.h }); }}
                >
                  {s.label} <small>{s.w} × {s.h}</small>
                </button>
              ))}
              <button type="button" className="chip" aria-pressed={customSheet} onClick={() => setCustomSheet(true)}>{t('Other')}</button>
            </div>
            {customSheet && (
              <div className="input-row">
                <input className="input num" type="number" inputMode="numeric" min={1} aria-label={t('Sheet length in mm')} value={sheet.w || ''} onChange={e => setSheet(s => ({ ...s, w: num(e.target.value) }))} />
                <span className="input-affix">×</span>
                <input className="input num" type="number" inputMode="numeric" min={1} aria-label={t('Sheet width in mm')} value={sheet.h || ''} onChange={e => setSheet(s => ({ ...s, h: num(e.target.value) }))} />
                <span className="input-affix">mm</span>
              </div>
            )}
          </div>

          <div className="field">
            <span className="field-label" id="thick-label">{t('Main board thickness')}</span>
            <div className="chips" role="group" aria-labelledby="thick-label">
              {THICKNESSES.map(t => (
                <button key={t} type="button" className="chip" aria-pressed={!customThickness && thickness === t} onClick={() => { setCustomThickness(false); setThickness(t); }}>
                  {t} mm
                </button>
              ))}
              <button type="button" className="chip" aria-pressed={customThickness} onClick={() => setCustomThickness(true)}>{t('Other')}</button>
            </div>
            {customThickness && (
              <div className="input-row">
                <input className="input num" type="number" inputMode="decimal" min={1} aria-label={t('Thickness in mm')} value={thickness || ''} onChange={e => setThickness(num(e.target.value))} />
                <span className="input-affix">mm</span>
              </div>
            )}
            <span className="field-help">{t('Parts in another thickness, like a 6 mm back, are put on their own sheets automatically.')}</span>
          </div>

          <div className="field">
            <label htmlFor="cost">{t('Price of one sheet')}</label>
            <div className="input-row">
              <span className="input-affix">₹</span>
              <input id="cost" className="input num" type="number" inputMode="numeric" min={1} value={sheetCost || ''} onChange={e => setSheetCost(num(e.target.value))} />
            </div>
          </div>

          {offcutShelf && offcutShelf.count > 0 && onUseOffcutsChange && (
            <div className="field" style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12 }}>
              <label className="switch" style={{ marginTop: 2 }}>
                <input
                  type="checkbox"
                  checked={useOffcuts}
                  onChange={e => onUseOffcutsChange(e.target.checked)}
                  aria-label={t('Use my offcut shelf')}
                />
                <span className="switch-track" aria-hidden="true" />
              </label>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <strong>{t('Use my offcut shelf')}</strong>
                <span className="small muted">
                  {offcutShelf.count} leftover {offcutShelf.count === 1 ? 'piece' : 'pieces'} ({offcutShelf.totalAreaM2.toFixed(2)} m²) from earlier projects — parts that fit are cut from these first, free.
                </span>
              </span>
            </div>
          )}

          <details className="more">
            <summary><ChevronRight size={18} /> {t('More settings')}</summary>
            <div className="field" style={{ marginTop: 8 }}>
              <label htmlFor="kerf">{t('Blade thickness (kerf)')}</label>
              <div className="input-row">
                <input id="kerf" className="input num" type="number" inputMode="decimal" min={0.1} step={0.1} value={kerf || ''} onChange={e => setKerf(num(e.target.value))} />
                <span className="input-affix">mm</span>
              </div>
              <span className="field-help">{t('The width of wood the blade removes on each cut. Most panel saws are about 3 mm.')}</span>
            </div>
          </details>
        </section>

        {error && <div className="notice notice-danger" role="alert"><TriangleAlert size={20} /><div>{error}</div></div>}
      </div>

      <div className="actionbar">
        <div className="actionbar-inner">
          <span className="muted small">
            {ready ? 'Next: check the parts we found.' : mode === 'file' ? 'Choose a 3D file to continue.' : 'Describe the furniture to continue.'}
          </span>
          <button type="button" className="btn btn-primary btn-lg" disabled={!ready || busy} onClick={submit}>
            {mode === 'file' ? 'Find the parts' : 'Make cutting plan'} <ArrowRight size={22} />
          </button>
        </div>
      </div>
    </main>
  );
}
