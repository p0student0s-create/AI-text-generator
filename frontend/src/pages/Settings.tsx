import React, { useState } from 'react';
import { Settings as SettingsIcon, Save, CircleCheck as CheckCircle2 } from 'lucide-react';
import type { StandardId, AutoActualizePeriod } from '../types';
import { useAppContext } from '../context/AppContext';
import { useTheme } from '../hooks/useTheme';

const ACTUALIZE_PERIODS: Array<{ value: AutoActualizePeriod; label: string; hint: string }> = [
  { value: 'daily',    label: 'Ежедневно',       hint: 'Для систем с высоким уровнем угроз (КИИ, ГИС I кл.)' },
  { value: 'weekly',   label: 'Еженедельно',      hint: 'Для систем с частыми изменениями' },
  { value: 'monthly',  label: 'Ежемесячно',       hint: 'ГОСТ Р 57580, финансовые организации' },
  { value: 'quarterly',label: 'Ежеквартально',    hint: 'ФСТЭК №239, КИИ второй и третьей категорий' },
  { value: 'biannual', label: 'Каждые полгода',   hint: 'ИСПДн (152-ФЗ), ФСТЭК №21' },
  { value: 'yearly',   label: 'Ежегодно',         hint: 'ISO 27001, базовый уровень (ФСТЭК №17)' },
];

const ALL_STANDARDS: Array<{ id: StandardId; label: string; tag: string }> = [
  { id: 'GOST57580', label: 'ГОСТ Р 57580', tag: 'РФ' },
  { id: 'FSTEC239', label: 'ФСТЭК №239', tag: 'РФ' },
  { id: 'ISO27001', label: 'ISO/IEC 27001:2022', tag: 'ISO' },
  { id: 'NIST', label: 'NIST SP 800-53', tag: 'NIST' },
  { id: 'GDPR', label: 'GDPR', tag: 'EU' },
  { id: 'PCI-DSS', label: 'PCI DSS v4.0', tag: 'PCI' },
  { id: 'CIS', label: 'CIS Controls v8', tag: 'CIS' },
];

export function Settings() {
  const { settings, updateSettings } = useAppContext();
  const { theme, toggleTheme } = useTheme();
  const [saved, setSaved] = useState(false);

  const toggleDefaultStandard = (id: StandardId) => {
    const current = settings.defaultStandards;
    updateSettings({
      defaultStandards: current.includes(id)
        ? current.filter((s) => s !== id)
        : [...current, id],
    });
  };

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="p-5 flex flex-col gap-5 max-w-2xl mx-auto w-full">
      <div className="flex items-center gap-2">
        <SettingsIcon size={20} className="text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">Настройки</h1>
      </div>

      <div className="card p-4 flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Внешний вид</h2>
        <div className="flex items-center justify-between py-1">
          <div>
            <p className="text-sm font-medium text-slate-700 dark:text-slate-300">Тема оформления</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
              Текущая: {theme === 'dark' ? 'Тёмная' : 'Светлая'}
            </p>
          </div>
          <button onClick={toggleTheme} className="btn-secondary">
            Переключить на {theme === 'dark' ? 'светлую' : 'тёмную'}
          </button>
        </div>
      </div>

      <div className="card p-4 flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
          Параметры организации
        </h2>
        <div>
          <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-1">
            Наименование организации по умолчанию
          </label>
          <input
            type="text"
            value={settings.organizationName}
            onChange={(e) => updateSettings({ organizationName: e.target.value })}
            placeholder='ООО "Организация", ПАО "Банк"...'
            className="input-field"
          />
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
            Будет подставляться автоматически при создании документов
          </p>
        </div>
      </div>

      <div className="card p-4 flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
          Стандарты по умолчанию
        </h2>
        <p className="text-xs text-slate-400 dark:text-slate-500 -mt-2">
          Будут выбраны автоматически при открытии мастера создания документов
        </p>
        <div className="flex flex-col gap-1.5">
          {ALL_STANDARDS.map(({ id, label, tag }) => {
            const checked = settings.defaultStandards.includes(id);
            return (
              <label
                key={id}
                className={`flex items-center gap-3 p-2.5 rounded-lg cursor-pointer border transition-colors ${
                  checked
                    ? 'border-blue-400 bg-blue-50 dark:bg-blue-950/40 dark:border-blue-700'
                    : 'border-slate-200 dark:border-slate-600 hover:border-slate-300 dark:hover:border-slate-500'
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleDefaultStandard(id)}
                  className="accent-blue-600 w-4 h-4 shrink-0"
                />
                <span className="flex-1 text-sm font-medium text-slate-700 dark:text-slate-300">{label}</span>
                <span className="badge bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400">
                  {tag}
                </span>
              </label>
            );
          })}
        </div>
      </div>

      <div className="card p-4 flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Поведение</h2>
        <div className="flex items-center justify-between py-1">
          <div>
            <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
              Автосохранение в историю
            </p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
              Автоматически сохранять успешные генерации
            </p>
          </div>
          <button
            role="switch"
            aria-checked={settings.autoSaveHistory}
            onClick={() => updateSettings({ autoSaveHistory: !settings.autoSaveHistory })}
            className={`relative inline-flex items-center w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-slate-800 ${
              settings.autoSaveHistory ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-600'
            }`}
          >
            <span
              className={`inline-block w-5 h-5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                settings.autoSaveHistory ? 'translate-x-5' : 'translate-x-0.5'
              }`}
            />
          </button>
        </div>
      </div>

      <div className="card p-4 flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Актуализация документов</h2>

        <div className="flex items-center justify-between py-1">
          <div>
            <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
              Автоматическая актуализация
            </p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
              Напоминать о необходимости обновить документы
            </p>
          </div>
          <button
            role="switch"
            aria-checked={settings.autoActualize}
            onClick={() => updateSettings({ autoActualize: !settings.autoActualize })}
            className={`relative inline-flex items-center w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-slate-800 ${
              settings.autoActualize ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-600'
            }`}
          >
            <span
              className={`inline-block w-5 h-5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                settings.autoActualize ? 'translate-x-5' : 'translate-x-0.5'
              }`}
            />
          </button>
        </div>

        {settings.autoActualize && (
          <div className="flex flex-col gap-2 pt-1">
            <p className="text-xs font-medium text-slate-600 dark:text-slate-400">
              Периодичность актуализации
            </p>
            <div className="flex flex-col gap-1.5">
              {ACTUALIZE_PERIODS.map(({ value, label, hint }) => {
                const selected = settings.autoActualizePeriod === value;
                return (
                  <label
                    key={value}
                    className={`flex items-start gap-3 p-2.5 rounded-lg cursor-pointer border transition-colors ${
                      selected
                        ? 'border-blue-400 bg-blue-50 dark:bg-blue-950/40 dark:border-blue-700'
                        : 'border-slate-200 dark:border-slate-600 hover:border-slate-300 dark:hover:border-slate-500'
                    }`}
                  >
                    <input
                      type="radio"
                      name="actualizePeriod"
                      checked={selected}
                      onChange={() => updateSettings({ autoActualizePeriod: value })}
                      className="accent-blue-600 w-4 h-4 shrink-0 mt-0.5"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-700 dark:text-slate-300">{label}</p>
                      <p className="text-xs text-slate-400 dark:text-slate-500 leading-tight">{hint}</p>
                    </div>
                  </label>
                );
              })}
            </div>
            <p className="text-xs text-slate-400 dark:text-slate-500 pt-1">
              Периоды указаны согласно требованиям нормативных актов РФ и международных стандартов
            </p>
          </div>
        )}
      </div>

      <button onClick={handleSave} className={`self-start flex items-center gap-2 ${saved ? 'btn-success' : 'btn-primary'}`}>
        {saved ? <CheckCircle2 size={15} /> : <Save size={15} />}
        {saved ? 'Сохранено!' : 'Сохранить настройки'}
      </button>
    </div>
  );
}
