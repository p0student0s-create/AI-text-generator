import React, { useState, useEffect } from 'react';
import { RefreshCw, ChevronLeft, Sparkles, RotateCcw, CircleCheck as CheckCircle2, Info } from 'lucide-react';
import type { StandardId } from '../types';
import { useAppContext } from '../context/AppContext';

const STANDARDS: Array<{ id: StandardId; label: string; description: string; tag: string }> = [
  { id: 'FZ152', label: '152-ФЗ', description: 'О персональных данных', tag: 'РФ' },
  { id: 'FZ187', label: '187-ФЗ', description: 'Безопасность КИИ', tag: 'РФ' },
  { id: 'FSTEC239', label: 'ФСТЭК №239', description: 'Приказ о защите КИИ', tag: 'РФ' },
  { id: 'FSTEC17', label: 'ФСТЭК №17', description: 'Защита информации в ГИС', tag: 'РФ' },
  { id: 'FSTEC21', label: 'ФСТЭК №21', description: 'Меры безопасности ПДн в ИСПДн', tag: 'РФ' },
  { id: 'FSTEC_MD', label: 'Методика оценки угроз ФСТЭК', description: 'Методический документ ФСТЭК (2021)', tag: 'РФ' },
  { id: 'GOST57580', label: 'ГОСТ Р 57580.1-2017', description: 'Защита информации финансовых организаций', tag: 'РФ' },
  { id: 'ISO27001', label: 'ISO/IEC 27001:2022', description: 'Международный стандарт СМИБ', tag: 'ISO' },
  { id: 'NIST', label: 'NIST SP 800-53 Rev.5', description: 'Меры безопасности и конфиденциальности', tag: 'US' },
  { id: 'GDPR', label: 'GDPR (Регламент ЕС 2016/679)', description: 'Защита персональных данных граждан ЕС', tag: 'EU' },
  { id: 'PCI-DSS', label: 'PCI DSS v4.0', description: 'Безопасность платёжных карт', tag: 'PCI' },
  { id: 'CIS', label: 'CIS Controls v8', description: 'Приоритетные меры кибербезопасности', tag: 'CIS' },
];

const DOC_TYPE_LABELS: Record<string, string> = {
  policy: 'Политика ИБ',
  regulation: 'Регламент',
  instruction: 'Инструкция',
  threat_model: 'Модель угроз',
  risk_assessment: 'Оценка рисков',
  incident_response: 'Реагирование на инциденты',
  access_control: 'Управление доступом',
};

type ActualizeStep = 1 | 2;

export function Actualize() {
  const {
    actualizeFormData,
    setActualizeFormData,
    setActivePage,
    generateDocument,
    generationStatus,
    generationResult,
    resetForm,
    updateFormData,
    formData,
  } = useAppContext();

  const [step, setStep] = useState<ActualizeStep>(1);
  const [localData, setLocalData] = useState(actualizeFormData);
  const [changeNote, setChangeNote] = useState('');

  useEffect(() => {
    setLocalData(actualizeFormData);
  }, [actualizeFormData]);

  const isGenerating = generationStatus === 'generating';
  const isDone = generationStatus === 'success' || generationStatus === 'error';

  const patch = (partial: Partial<typeof localData>) => {
    if (!localData) return;
    setLocalData((prev) => prev ? { ...prev, ...partial } : prev);
  };

  const toggleStandard = (id: StandardId) => {
    if (!localData) return;
    const current = localData.standards;
    patch({
      standards: current.includes(id)
        ? current.filter((s) => s !== id)
        : [...current, id],
    });
  };

  const handleGenerate = async () => {
    if (!localData) return;
    // merge localData + changeNote into formData via updateFormData
    updateFormData({ ...localData });
    setStep(2);
    await generateDocument();
  };

  const handleReset = () => {
    resetForm();
    setActualizeFormData(null);
    setActivePage('history');
  };

  if (!localData) {
    return (
      <div className="p-5 flex flex-col gap-4 max-w-2xl mx-auto w-full">
        <div className="card p-12 flex flex-col items-center gap-3 text-center">
          <RefreshCw size={32} className="text-slate-400" />
          <p className="text-sm font-medium text-slate-600 dark:text-slate-400">
            Нет документа для актуализации
          </p>
          <p className="text-xs text-slate-400">Выберите документ в «Истории» и нажмите «Актуализировать»</p>
          <button className="btn-secondary mt-2" onClick={() => setActivePage('history')}>
            <ChevronLeft size={14} /> Перейти в историю
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-5 flex flex-col gap-5 max-w-2xl mx-auto w-full">
      <div className="flex items-center gap-3">
        <button onClick={() => setActivePage('history')} className="btn-secondary text-xs px-3 py-1.5">
          <ChevronLeft size={14} /> Назад
        </button>
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <RefreshCw size={18} className="text-blue-500" />
            Актуализация документа
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            {DOC_TYPE_LABELS[localData.documentType ?? ''] ?? 'Документ'} · {localData.title || 'без названия'}
          </p>
        </div>
      </div>

      <div className="card p-3 flex items-start gap-3 border-l-4 border-blue-400 bg-blue-50 dark:bg-blue-950/30">
        <Info size={16} className="text-blue-500 shrink-0 mt-0.5" />
        <p className="text-xs text-blue-700 dark:text-blue-300">
          Отредактируйте параметры: исправьте данные, которые изменились (название организации, ФИО, стандарты). Поля без изменений можно оставить как есть.
        </p>
      </div>

      {step === 1 && (
        <div className="flex flex-col gap-4">
          <div className="card p-4 flex flex-col gap-3">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Основные параметры</h2>

            <div>
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-1">
                Название документа <span className="text-slate-400">(необязательно)</span>
              </label>
              <input
                type="text"
                value={localData.title}
                onChange={(e) => patch({ title: e.target.value })}
                className="input-field"
                placeholder="Оставьте пустым для автогенерации"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-1">
                Наименование организации
              </label>
              <input
                type="text"
                value={localData.organizationName}
                onChange={(e) => patch({ organizationName: e.target.value })}
                className="input-field"
                placeholder='ООО "Пример", ПАО "Банк"...'
              />
            </div>

            {localData.documentType === 'policy' || localData.documentType === 'threat_model' || localData.documentType === 'risk_assessment' ? (
              <div>
                <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-1">
                  Объект защиты
                </label>
                <input
                  type="text"
                  value={localData.protectionObject}
                  onChange={(e) => patch({ protectionObject: e.target.value })}
                  className="input-field"
                />
              </div>
            ) : null}

            {localData.documentType === 'policy' || localData.documentType === 'threat_model' ? (
              <div>
                <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-1">
                  Категория данных
                </label>
                <input
                  type="text"
                  value={localData.dataCategory}
                  onChange={(e) => patch({ dataCategory: e.target.value })}
                  className="input-field"
                />
              </div>
            ) : null}

            {localData.documentType === 'regulation' ? (
              <div>
                <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-1">
                  Тема регламента
                </label>
                <input
                  type="text"
                  value={localData.regulationTopic}
                  onChange={(e) => patch({ regulationTopic: e.target.value })}
                  className="input-field"
                />
              </div>
            ) : null}

            {localData.documentType === 'instruction' ? (
              <>
                <div>
                  <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-1">
                    Должность / роль
                  </label>
                  <input
                    type="text"
                    value={localData.instructionRole}
                    onChange={(e) => patch({ instructionRole: e.target.value })}
                    className="input-field"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-1">
                    Тема инструкции
                  </label>
                  <input
                    type="text"
                    value={localData.instructionTopic}
                    onChange={(e) => patch({ instructionTopic: e.target.value })}
                    className="input-field"
                  />
                </div>
              </>
            ) : null}

            {localData.documentType === 'incident_response' ? (
              <div>
                <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-1">
                  Тип инфраструктуры
                </label>
                <input
                  type="text"
                  value={localData.infrastructureType}
                  onChange={(e) => patch({ infrastructureType: e.target.value })}
                  className="input-field"
                />
              </div>
            ) : null}

            {localData.documentType === 'access_control' ? (
              <div>
                <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-1">
                  Тип системы
                </label>
                <input
                  type="text"
                  value={localData.systemType}
                  onChange={(e) => patch({ systemType: e.target.value })}
                  className="input-field"
                />
              </div>
            ) : null}
          </div>

          <div className="card p-4 flex flex-col gap-3">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Нормативная база</h2>
            <div className="flex flex-col gap-1.5">
              {STANDARDS.map(({ id, label, description, tag }) => {
                const checked = localData.standards.includes(id);
                return (
                  <label
                    key={id}
                    className={`flex items-center gap-3 p-2.5 rounded-lg cursor-pointer border transition-colors duration-100 ${
                      checked
                        ? 'border-blue-400 bg-blue-50 dark:bg-blue-950/40 dark:border-blue-700'
                        : 'border-slate-200 dark:border-slate-600 hover:border-slate-300 dark:hover:border-slate-500'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleStandard(id)}
                      className="accent-blue-600 w-4 h-4 shrink-0"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">{label}</p>
                      <p className="text-xs text-slate-400 dark:text-slate-500 leading-tight">{description}</p>
                    </div>
                    <span className={`badge shrink-0 ${
                      tag === 'РФ' ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300' :
                      tag === 'ISO' ? 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400' :
                      tag === 'EU' ? 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300' :
                      'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400'
                    }`}>
                      {tag}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="card p-4 flex flex-col gap-3">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Комментарий к изменениям</h2>
            <textarea
              value={changeNote}
              onChange={(e) => setChangeNote(e.target.value)}
              placeholder="Опционально: опишите что изменилось — новые требования, смена ответственного, изменение организационной структуры..."
              rows={3}
              className="input-field resize-none"
            />
            <p className="text-xs text-slate-400 dark:text-slate-500">
              Комментарий передаётся в генератор как контекст для учёта изменений
            </p>
          </div>

          <div className="flex justify-end">
            <button className="btn-primary" onClick={handleGenerate}>
              <Sparkles size={15} /> Актуализировать документ
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="card p-8 flex flex-col items-center gap-4">
          {isGenerating && (
            <>
              <div className="relative w-12 h-12">
                <div className="absolute inset-0 rounded-full border-4 border-blue-100 dark:border-blue-900" />
                <div className="absolute inset-0 rounded-full border-4 border-blue-600 border-t-transparent animate-spin" />
              </div>
              <div className="text-center">
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  Актуализация документа...
                </p>
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                  Генерируем обновлённую версию с учётом изменений
                </p>
              </div>
            </>
          )}
          {isDone && (
            <>
              <div className="w-12 h-12 rounded-full bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center">
                <CheckCircle2 size={24} className="text-emerald-600 dark:text-emerald-400" />
              </div>
              <div className="text-center">
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  Документ актуализирован
                </p>
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                  Результат доступен на панели справа
                </p>
              </div>
              <div className="flex gap-2">
                <button className="btn-secondary text-xs" onClick={handleReset}>
                  <RotateCcw size={13} /> В историю
                </button>
                <button className="btn-secondary text-xs" onClick={() => { setStep(1); }}>
                  <RefreshCw size={13} /> Ещё раз
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
