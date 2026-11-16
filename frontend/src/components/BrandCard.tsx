import { useEffect, useRef, useState } from 'react';
import { BadgeCheck, ImageUp, Trash2 } from 'lucide-react';
import { t } from '../i18n';
import { deleteLogo, friendlyError, getBrand, logoPreviewUrl, saveBrand, uploadLogo } from '../api';
import type { BrandProfile } from '../types';

/**
 * The studio details printed at the top of the client's PDF quote: name, contact, logo,
 * colour, tax and terms. They belong to the account, so they are set once for every quote.
 */
export default function BrandCard() {
  const [brand, setBrand] = useState<BrandProfile | null>(null);
  const [logo, setLogo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const b = await getBrand();
        if (!live) return;
        setBrand(b);
        if (b.has_logo) setLogo(await logoPreviewUrl());
      } catch {
        if (live) setError(t('Could not load your studio details.'));
      }
    })();
    return () => { live = false; };
  }, []);

  if (!brand) return error ? <div className="notice notice-danger" role="alert">{error}</div> : null;

  const set = (patch: Partial<BrandProfile>) => { setBrand({ ...brand, ...patch }); setNotice(null); };
  const text = (id: string, label: string, key: 'studio_name' | 'phone' | 'email' | 'address' | 'tax_id', max: number, placeholder = '') => (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} className="input" maxLength={max} placeholder={placeholder} value={brand[key]} onChange={e => set({ [key]: e.target.value })} />
    </div>
  );

  const save = async () => {
    setBusy(true); setError(null); setNotice(null);
    try {
      const { has_logo: _ignored, ...fields } = brand;
      void _ignored;
      setBrand(await saveBrand(fields));
      setNotice(t('Saved. Every PDF quote now carries these details.'));
    } catch (err) {
      setError(friendlyError(err, 'Could not save your studio details.'));
    } finally {
      setBusy(false);
    }
  };

  const pickLogo = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const next = await uploadLogo(file);
      setBrand(b => (b ? { ...b, has_logo: next.has_logo } : b));
      setLogo(await logoPreviewUrl());
    } catch (err) {
      setError(friendlyError(err, 'Could not use that image. Try a PNG or JPEG under 1 MB.'));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const removeLogo = async () => {
    setBusy(true); setError(null);
    try {
      await deleteLogo();
      setBrand(b => (b ? { ...b, has_logo: false } : b));
      setLogo(null);
    } catch (err) {
      setError(friendlyError(err, 'Could not remove the logo.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="more card">
      <summary><BadgeCheck size={18} /> {t('Your studio details for quotes')}</summary>
      <div className="stack" style={{ marginTop: 8 }}>
        <p className="small muted">{t('These appear at the top of the PDF quote you send a client. Use English letters: the PDF cannot print Hindi yet.')}</p>

        <div className="field">
          <span className="field-label">{t('Logo')}</span>
          <div className="row">
            {logo ? <img src={logo} alt={t('Your logo')} style={{ maxHeight: 56, maxWidth: 160, borderRadius: 6 }} /> : <span className="small muted">{t('No logo yet')}</span>}
            <input ref={fileRef} type="file" accept="image/png,image/jpeg" hidden onChange={e => void pickLogo(e.target.files?.[0])} />
            <button type="button" className="btn" disabled={busy} onClick={() => fileRef.current?.click()}><ImageUp size={16} /> {brand.has_logo ? t('Change') : t('Upload logo')}</button>
            {brand.has_logo && <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => void removeLogo()} aria-label={t('Remove logo')}><Trash2 size={16} /></button>}
          </div>
        </div>

        {text('b-name', t('Studio or business name'), 'studio_name', 80, 'Rao Interiors')}
        <div className="quote-grid">
          {text('b-phone', t('Phone'), 'phone', 40, '+91 98765 43210')}
          {text('b-email', t('Email'), 'email', 120, 'hello@studio.in')}
        </div>
        {text('b-address', t('Address'), 'address', 200)}
        <div className="quote-grid">
          {text('b-taxid', t('GST number'), 'tax_id', 40)}
          <div className="field">
            <label htmlFor="b-tax">{t('GST rate')}</label>
            <div className="input-row">
              <input id="b-tax" className="input num" type="number" inputMode="decimal" min={0} max={100} value={brand.tax_percent || ''} onChange={e => set({ tax_percent: Math.max(0, Math.min(100, parseFloat(e.target.value) || 0)) })} />
              <span className="input-affix">%</span>
            </div>
          </div>
          <div className="field">
            <label htmlFor="b-valid">{t('Quote valid for')}</label>
            <div className="input-row">
              <input id="b-valid" className="input num" type="number" inputMode="numeric" min={1} max={365} value={brand.validity_days} onChange={e => set({ validity_days: Math.max(1, Math.min(365, parseInt(e.target.value, 10) || 1)) })} />
              <span className="input-affix">{t('days')}</span>
            </div>
          </div>
          <div className="field">
            <label htmlFor="b-accent">{t('Colour')}</label>
            <input id="b-accent" className="input" type="color" value={brand.accent} onChange={e => set({ accent: e.target.value })} style={{ padding: 2, minHeight: 44 }} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="b-terms">{t('Payment and other terms')}</label>
          <textarea id="b-terms" className="input" rows={3} maxLength={800} placeholder={t('Example: 50% advance, balance on delivery.')} value={brand.terms} onChange={e => set({ terms: e.target.value })} />
        </div>
        <label className="grain-toggle">
          <input type="checkbox" checked={brand.show_breakdown} onChange={e => set({ show_breakdown: e.target.checked })} />
          {t('Show a price breakdown (material, hardware, labour). Your margin stays hidden inside it.')}
        </label>

        {error && <div className="notice notice-danger" role="alert">{error}</div>}
        {notice && <p className="small" role="status">{notice}</p>}
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void save()} style={{ alignSelf: 'flex-start' }}>
          {t('Save studio details')}
        </button>
      </div>
    </details>
  );
}
