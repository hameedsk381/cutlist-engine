import { Languages } from 'lucide-react';
import { LANGUAGES, getLanguage, setLanguage } from '../i18n';
import type { Language } from '../i18n';

/** Language picker. Changing it reloads the page so every screen switches. */
export default function LanguageSwitch() {
  return (
    <label className="lang-switch">
      <Languages size={18} aria-hidden="true" />
      <select
        aria-label="Language / भाषा"
        value={getLanguage()}
        onChange={e => setLanguage(e.target.value as Language)}
      >
        {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
      </select>
    </label>
  );
}
