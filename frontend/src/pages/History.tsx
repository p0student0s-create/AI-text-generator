import React, { useState, useMemo } from 'react';
import { History as HistoryIcon, Trash2, Filter, FileText, Search, RefreshCw } from 'lucide-react';
import type { DocumentTypeId } from '../types';
import { useAppContext } from '../context/AppContext';

const TYPE_LABELS: Record<DocumentTypeId, string> = {
  policy: 'Политика ИБ',
  regulation: 'Регламент',
  instruction: 'Инструкция',
  threat_model: 'Модель угроз',
  risk_assessment: 'Оценка рисков',
  incident_response: 'Реагирование на инциденты',
  access_control: 'Управление доступом',
};

type FilterOption = 'all' | DocumentTypeId;

export function History() {
  const { history, clearHistory, actualizeEntry } = useAppContext();
  const [filter, setFilter] = useState<FilterOption>('all');
  const [search, setSearch] = useState('');

  const uniqueTypes = useMemo(
    () => [...new Set(history.map((e) => e.documentType))],
    [history]
  );

  const filtered = useMemo(() => {
    return history
      .filter((e) => filter === 'all' || e.documentType === filter)
      .filter((e) => {
        const q = search.toLowerCase();
        return (
          !q ||
          e.title.toLowerCase().includes(q) ||
          e.organizationName.toLowerCase().includes(q)
        );
      });
  }, [history, filter, search]);

  return (
    <div className="p-5 flex flex-col gap-4 max-w-3xl mx-auto w-full">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <HistoryIcon size={20} />
            История генераций
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            {history.length === 0
              ? 'Нет сгенерированных документов'
              : `${history.length} документ${history.length === 1 ? '' : history.length < 5 ? 'а' : 'ов'} за сессию`}
          </p>
        </div>
        {history.length > 0 && (
          <button
            onClick={clearHistory}
            className="btn-secondary text-xs text-red-600 dark:text-red-400
                       hover:bg-red-50 dark:hover:bg-red-950/30"
          >
            <Trash2 size={13} /> Очистить
          </button>
        )}
      </div>

      {history.length > 0 && (
        <div className="card p-3 flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Filter size={13} className="text-slate-400" />
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Фильтры</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {(['all', ...uniqueTypes] as FilterOption[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`text-xs px-3 py-1 rounded-full font-medium transition-colors ${
                  filter === f
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-600'
                }`}
              >
                {f === 'all' ? 'Все типы' : TYPE_LABELS[f as DocumentTypeId]}
              </button>
            ))}
          </div>
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              placeholder="Поиск по названию или организации..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input-field pl-8"
            />
          </div>
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="card p-12 flex flex-col items-center gap-3 text-center">
          <div className="w-14 h-14 rounded-2xl bg-slate-100 dark:bg-slate-700/50 flex items-center justify-center">
            <FileText size={24} className="text-slate-400" />
          </div>
          <p className="text-sm font-medium text-slate-600 dark:text-slate-400">
            {history.length === 0
              ? 'История пуста. Создайте первый документ!'
              : 'Ничего не найдено по вашему запросу.'}
          </p>
          {history.length === 0 && (
            <p className="text-xs text-slate-400 dark:text-slate-500">
              Перейдите в «Новый документ» и сгенерируйте документ
            </p>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map((entry) => {
            const standardLabels: Record<string, string> = {
              GOST57580: 'ГОСТ 57580',
              FSTEC239: 'ФСТЭК №239',
              ISO27001: 'ISO 27001',
              NIST: 'NIST',
              GDPR: 'GDPR',
              'PCI-DSS': 'PCI DSS',
              CIS: 'CIS v8',
            };
            return (
              <div
                key={entry.id}
                className="card p-4 flex items-start justify-between gap-3
                           hover:border-blue-200 dark:hover:border-blue-800 transition-colors"
              >
                <div className="flex flex-col gap-1.5 min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 truncate">
                    {entry.title}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    <span className="badge bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
                      {TYPE_LABELS[entry.documentType]}
                    </span>
                    {entry.standards.map((s) => (
                      <span
                        key={s}
                        className="badge bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400"
                      >
                        {standardLabels[s] || s}
                      </span>
                    ))}
                  </div>
                  <p className="text-xs text-slate-400 dark:text-slate-500">
                    {entry.organizationName && `${entry.organizationName} · `}
                    {entry.wordCount.toLocaleString('ru-RU')} слов ·{' '}
                    {new Date(entry.generatedAt).toLocaleString('ru-RU', {
                      day: 'numeric', month: 'short', year: 'numeric',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-2 shrink-0">
                  <span
                    className={`badge ${
                      entry.status === 'completed'
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400'
                        : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400'
                    }`}
                  >
                    {entry.status === 'completed' ? 'Готов' : 'Ошибка'}
                  </span>
                  {entry.status === 'completed' && (
                    <button
                      onClick={() => actualizeEntry(entry)}
                      className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg
                                 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300
                                 hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-blue-950/40 dark:hover:text-blue-400
                                 transition-colors font-medium"
                    >
                      <RefreshCw size={11} /> Актуализировать
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
