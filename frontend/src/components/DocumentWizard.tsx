import React, { useState } from 'react';
import { 
  FileText, Shield, TriangleAlert as AlertTriangle, BookOpen, Lock, 
  ChartBar as BarChart2, Activity, ChevronLeft, Sparkles, RotateCcw, 
  CircleCheck as CheckCircle2, CircleAlert 
} from 'lucide-react';
import type { DocumentType, DocumentTypeId, StandardId, WizardFormData } from '../types';
import { useAppContext } from '../context/AppContext';

// === Интерфейс ошибок валидации ===
interface FormErrors {
  standards?: string;
  protectionObject?: string;
  dataCategory?: string;
  organizationName?: string;
  regulationTopic?: string;
  instructionRole?: string;
  instructionTopic?: string;
  infrastructureType?: string;
  systemType?: string;
}

// === Валидация шага 2 ===
function validateStep2(formData: WizardFormData): FormErrors {
  const errors: FormErrors = {};
  
  // Минимум 1 стандарт
  if (formData.standards.length === 0) {
    errors.standards = 'Выберите хотя бы один стандарт';
  }
  
  // Обязательные поля для всех типов
  if (!formData.organizationName?.trim()) {
    errors.organizationName = 'Укажите наименование организации';
  }
  
  // Поля, специфичные для типов документов
  if (formData.documentType === 'policy' || formData.documentType === 'threat_model' || formData.documentType === 'risk_assessment') {
    if (!formData.protectionObject) errors.protectionObject = 'Выберите объект защиты';
    if (!formData.dataCategory) errors.dataCategory = 'Выберите категорию данных';
  }
  
  if (formData.documentType === 'regulation' && !formData.regulationTopic?.trim()) {
    errors.regulationTopic = 'Укажите тему регламента';
  }
  
  if (formData.documentType === 'instruction') {
    if (!formData.instructionRole?.trim()) errors.instructionRole = 'Укажите должность/роль';
    if (!formData.instructionTopic?.trim()) errors.instructionTopic = 'Укажите тему инструкции';
  }
  
  if (formData.documentType === 'incident_response' && !formData.infrastructureType) {
    errors.infrastructureType = 'Выберите тип инфраструктуры';
  }
  
  if (formData.documentType === 'access_control' && !formData.systemType) {
    errors.systemType = 'Выберите тип системы';
  }
  
  return errors;
}

// === Типы документов ===
const DOCUMENT_TYPES: DocumentType[] = [
  {
    id: 'policy',
    label: 'Политика ИБ',
    description: 'Управленческий документ с принципами защиты',
    estimatedPages: '8–15 стр.',
    icon: 'Shield',
    color: 'bg-blue-50 dark:bg-blue-950/40 border-blue-100 dark:border-blue-900/50',
  },
  {
    id: 'regulation',
    label: 'Регламент',
    description: 'Конкретные процедуры и требования',
    estimatedPages: '10–20 стр.',
    icon: 'BookOpen',
    color: 'bg-slate-50 dark:bg-slate-700/40 border-slate-200 dark:border-slate-600',
  },
  {
    id: 'instruction',
    label: 'Инструкция',
    description: 'Пошаговые правила для сотрудников',
    estimatedPages: '5–10 стр.',
    icon: 'FileText',
    color: 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-100 dark:border-emerald-900/50',
  },
  {
    id: 'threat_model',
    label: 'Модель угроз',
    description: 'Анализ нарушителей и актуальных угроз',
    estimatedPages: '15–30 стр.',
    icon: 'AlertTriangle',
    color: 'bg-red-50 dark:bg-red-950/40 border-red-100 dark:border-red-900/50',
  },
  {
    id: 'risk_assessment',
    label: 'Оценка рисков',
    description: 'Реестр рисков и план обработки',
    estimatedPages: '10–20 стр.',
    icon: 'BarChart2',
    color: 'bg-amber-50 dark:bg-amber-950/40 border-amber-100 dark:border-amber-900/50',
  },
  {
    id: 'incident_response',
    label: 'Реагирование на инциденты',
    description: 'Классификация и процедуры реагирования',
    estimatedPages: '12–25 стр.',
    icon: 'Activity',
    color: 'bg-orange-50 dark:bg-orange-950/40 border-orange-100 dark:border-orange-900/50',
  },
  {
    id: 'access_control',
    label: 'Управление доступом',
    description: 'Политика IAM и жизненный цикл учётных записей',
    estimatedPages: '8–15 стр.',
    icon: 'Lock',
    color: 'bg-teal-50 dark:bg-teal-950/40 border-teal-100 dark:border-teal-900/50',
  },
];

// === Стандарты ===
const STANDARDS: Array<{ id: StandardId; label: string; description: string; tag: string }> = [
  { id: 'FZ152', label: 'ФЗ-152 «О персональных данных»', description: 'Обработка и защита персональных данных', tag: 'РФ' },
  { id: 'FZ187', label: 'ФЗ-187 «О безопасности КИИ»', description: 'Критическая информационная инфраструктура', tag: 'РФ' },
  { id: 'FSTEC239', label: 'Приказ ФСТЭК №239', description: 'Защита значимых объектов КИИ', tag: 'РФ' },
  { id: 'FSTEC17', label: 'Приказ ФСТЭК №17', description: 'Защита информации в ГИС', tag: 'РФ' },
  { id: 'FSTEC21', label: 'Приказ ФСТЭК №21', description: 'Меры безопасности ПДн в ИСПДн', tag: 'РФ' },
  { id: 'FSTEC_MD', label: 'Методика оценки угроз ФСТЭК', description: 'Методический документ ФСТЭК (2021)', tag: 'РФ' },
  { id: 'GOST57580', label: 'ГОСТ Р 57580.1-2017', description: 'Защита информации финансовых организаций', tag: 'РФ' },
  { id: 'ISO27001', label: 'ISO/IEC 27001:2022', description: 'Международный стандарт СМИБ', tag: 'ISO' },
  { id: 'NIST', label: 'NIST SP 800-53 Rev.5', description: 'Меры безопасности и конфиденциальности', tag: 'US' },
  { id: 'GDPR', label: 'GDPR (Регламент ЕС 2016/679)', description: 'Защита персональных данных граждан ЕС', tag: 'EU' },
  { id: 'PCI-DSS', label: 'PCI DSS v4.0', description: 'Безопасность данных платёжных карт', tag: 'PCI' },
  { id: 'CIS', label: 'CIS Controls v8', description: 'Приоритетные меры кибербезопасности', tag: 'CIS' },
];

const ICON_MAP: Record<string, React.ElementType> = {
  Shield, BookOpen, FileText, AlertTriangle, BarChart2, Activity, Lock,
};

// === Опции для полей ===
const DATA_CATEGORIES = [
  'Персональные данные (ПДн)', 'Государственная тайна', 'Коммерческая тайна',
  'Банковская тайна', 'Данные КИИ', 'Конфиденциальные данные', 'Открытые данные',
];

const PROTECTION_OBJECTS = [
  'Информационная система персональных данных (ИСПДн)',
  'Автоматизированная система управления (АСУ)',
  'Корпоративная сеть и инфраструктура',
  'Объект критической информационной инфраструктуры (КИИ)',
  'Государственная информационная система (ГИС)',
  'Финансовая информационная система', 'Облачная инфраструктура',
];

const INFRASTRUCTURE_TYPES = [
  'Корпоративная IT-инфраструктура', 'Промышленные системы управления (ICS/SCADA)',
  'Облачная инфраструктура', 'Финансовая инфраструктура', 'Объекты КИИ',
  'Медицинская информационная система',
];

const SYSTEM_TYPES = [
  'Корпоративная Active Directory / LDAP', 'Веб-приложение и API',
  'Облачная платформа (AWS / Azure / GCP)', 'ERP / CRM-система',
  'Банковская система', 'Государственная информационная система',
];

// === Конфигурация полей по типам документов ===
type FieldConfig = {
  key: keyof WizardFormData;
  label: string;
  required?: boolean;
  type: 'text' | 'select';
  placeholder?: string;
  options?: string[];
};

const DOC_FIELDS: Record<string, FieldConfig[]> = {
  policy: [
    { key: 'organizationName', label: 'Наименование организации', required: true, type: 'text', placeholder: 'ООО "Пример"...' },
    { key: 'protectionObject', label: 'Объект защиты', required: true, type: 'select', options: PROTECTION_OBJECTS },
    { key: 'dataCategory', label: 'Категория данных', required: true, type: 'select', options: DATA_CATEGORIES },
  ],
  regulation: [
    { key: 'organizationName', label: 'Наименование организации', required: true, type: 'text', placeholder: 'ООО "Пример"...' },
    { key: 'regulationTopic', label: 'Тема регламента', required: true, type: 'text', placeholder: 'Управление паролями...' },
  ],
  instruction: [
    { key: 'organizationName', label: 'Наименование организации', required: true, type: 'text', placeholder: 'ООО "Пример"...' },
    { key: 'instructionRole', label: 'Должность / роль', required: true, type: 'text', placeholder: 'Системный администратор...' },
    { key: 'instructionTopic', label: 'Тема инструкции', required: true, type: 'text', placeholder: 'Работа с паролями...' },
  ],
  threat_model: [
    { key: 'organizationName', label: 'Наименование организации', required: true, type: 'text', placeholder: 'ООО "Пример"...' },
    { key: 'protectionObject', label: 'Объект защиты', required: true, type: 'select', options: PROTECTION_OBJECTS },
    { key: 'dataCategory', label: 'Категория данных', required: true, type: 'select', options: DATA_CATEGORIES },
  ],
  risk_assessment: [
    { key: 'organizationName', label: 'Наименование организации', required: true, type: 'text', placeholder: 'ООО "Пример"...' },
    { key: 'protectionObject', label: 'Объект оценки', required: true, type: 'select', options: PROTECTION_OBJECTS },
  ],
  incident_response: [
    { key: 'organizationName', label: 'Наименование организации', required: true, type: 'text', placeholder: 'ООО "Пример"...' },
    { key: 'infrastructureType', label: 'Тип инфраструктуры', required: true, type: 'select', options: INFRASTRUCTURE_TYPES },
  ],
  access_control: [
    { key: 'organizationName', label: 'Наименование организации', required: true, type: 'text', placeholder: 'ООО "Пример"...' },
    { key: 'systemType', label: 'Тип системы', required: true, type: 'select', options: SYSTEM_TYPES },
  ],
};

const TITLE_PLACEHOLDERS: Record<string, string> = {
  policy: 'Политика информационной безопасности ООО «Пример»',
  regulation: 'Регламент управления паролями ООО «Пример»',
  instruction: 'Инструкция по антивирусной защите',
  threat_model: 'Модель угроз ИСПДн ООО «Пример»',
  risk_assessment: 'Оценка рисков информационной безопасности 2024',
  incident_response: 'Регламент реагирования на инциденты ИБ',
  access_control: 'Политика управления доступом ООО «Пример»',
};

type WizardStep = 1 | 2 | 3;

export function DocumentWizard() {
  const { formData, updateFormData, resetForm, generateDocument, generationStatus, generationError } = useAppContext();
  const [step, setStep] = useState<WizardStep>(1);
  const [errors, setErrors] = useState<FormErrors>({});
  const [touched, setTouched] = useState(false);

  const isGenerating = generationStatus === 'generating';
  const isDone = generationStatus === 'success' || generationStatus === 'error';

  const selectType = (id: DocumentTypeId) => {
    updateFormData({ documentType: id });
    setStep(2);
  };

  const toggleStandard = (id: StandardId) => {
    const current = formData.standards;
    updateFormData({
      standards: current.includes(id) ? current.filter((s) => s !== id) : [...current, id],
    });
  };

  const handleGenerate = async () => {
    setTouched(true);
    const errs = validateStep2(formData);
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }
    setErrors({});
    setStep(3);
    await generateDocument();
  };

  const handleReset = () => {
    resetForm();
    setStep(1);
    setErrors({});
    setTouched(false);
  };

  const steps = ['Тип документа', 'Параметры', 'Генерация'];

  // === Рендер поля формы ===
  const renderField = (field: FieldConfig) => {
    const errorKey = field.key as keyof FormErrors;
  
  return (
    <div key={field.key as string}>
      <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-1">
        {field.label}
        {field.required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {field.type === 'select' ? (
        <select
          value={formData[field.key] as string || ''}
          onChange={(e) => {
            updateFormData({ [field.key]: e.target.value });
            if (touched) setErrors((prev) => ({ ...prev, [errorKey]: undefined }));
          }}
          className={`input-field ${touched && errors[errorKey] ? 'border-red-400 dark:border-red-600 focus:ring-red-300' : ''}`}
        >
          <option value="">Выберите...</option>
          {field.options?.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <input
          type="text"
          placeholder={field.placeholder}
          value={formData[field.key] as string || ''}
          onChange={(e) => {
            updateFormData({ [field.key]: e.target.value });
            if (touched) setErrors((prev) => ({ ...prev, [errorKey]: undefined }));
          }}
          className={`input-field ${touched && errors[errorKey] ? 'border-red-400 dark:border-red-600 focus:ring-red-300' : ''}`}
        />
      )}
      {touched && errors[errorKey] && (
        <p className="flex items-center gap-1 text-red-600 dark:text-red-400 text-xs mt-1">
          <CircleAlert size={11} /> {errors[errorKey]}
        </p>
      )}
    </div>
  );
};

  return (
    <div className="card p-5 flex flex-col gap-5">
      {/* Шаги */}
      <div className="flex items-center gap-2">
        {steps.map((label, idx) => {
          const s = (idx + 1) as WizardStep;
          const done = step > s;
          const active = step === s;
          return (
            <React.Fragment key={label}>
              <div className={`flex items-center gap-1.5 text-xs font-medium transition-colors ${
                active ? 'text-blue-600 dark:text-blue-400' :
                done ? 'text-emerald-600 dark:text-emerald-400' :
                'text-slate-400 dark:text-slate-500'
              }`}>
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-colors ${
                  active ? 'bg-blue-600 text-white' :
                  done ? 'bg-emerald-500 text-white' :
                  'border border-slate-300 dark:border-slate-600 text-slate-400'
                }`}>
                  {done ? '✓' : s}
                </span>
                <span className="hidden sm:block">{label}</span>
              </div>
              {idx < 2 && <div className="flex-1 h-px bg-slate-200 dark:bg-slate-700" />}
            </React.Fragment>
          );
        })}
      </div>

      {/* Шаг 1: Выбор типа */}
      {step === 1 && (
        <div>
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">
            Выберите тип документа
          </p>
          <div className="grid grid-cols-1 gap-2">
            {DOCUMENT_TYPES.map(({ id, label, description, estimatedPages, icon, color }) => {
              const Icon = ICON_MAP[icon] ?? FileText;
              const selected = formData.documentType === id;
              return (
                <button
                  key={id}
                  onClick={() => selectType(id)}
                  className={`flex items-center gap-3 p-3 rounded-xl border-2 text-left transition-all duration-150 ${color}
                              ${selected ? 'border-blue-500 dark:border-blue-400 shadow-sm' : 'hover:border-blue-300 dark:hover:border-blue-700'}`}
                >
                  <Icon size={18} className="text-slate-600 dark:text-slate-300 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{label}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{description}</p>
                  </div>
                  <span className="text-xs text-blue-600 dark:text-blue-400 font-medium shrink-0">{estimatedPages}</span>
                  {selected && <CheckCircle2 size={16} className="text-blue-600 dark:text-blue-400 shrink-0" />}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Шаг 2: Параметры */}
      {step === 2 && (
        <div className="flex flex-col gap-4">
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            Выберите стандарты и укажите параметры
          </p>

          {/* Стандарты */}
          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-2">
              Стандарты / нормативная база
            </p>
            {touched && errors.standards && (
              <div className="flex items-center gap-1.5 text-red-600 dark:text-red-400 text-xs mb-2">
                <CircleAlert size={13} />
                <span>{errors.standards}</span>
              </div>
            )}
            <div className="flex flex-col gap-1.5">
              {STANDARDS.map(({ id, label, description, tag }) => {
                const checked = formData.standards.includes(id);
                return (
                  <label key={id} className={`flex items-center gap-3 p-2.5 rounded-lg cursor-pointer border transition-colors duration-100 ${
                    checked ? 'border-blue-400 bg-blue-50 dark:bg-blue-950/40 dark:border-blue-700' :
                    touched && errors.standards ? 'border-red-300 dark:border-red-700 hover:border-red-400' :
                    'border-slate-200 dark:border-slate-600 hover:border-slate-300 dark:hover:border-slate-500'
                  }`}>
                    <input type="checkbox" checked={checked} onChange={() => toggleStandard(id)} className="accent-blue-600 w-4 h-4 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">{label}</p>
                      <p className="text-xs text-slate-400 dark:text-slate-500 leading-tight">{description}</p>
                    </div>
                    <span className={`badge shrink-0 ${
                      tag === 'РФ' ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300' :
                      tag === 'ISO' ? 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400' :
                      tag === 'EU' ? 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300' :
                      'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400'
                    }`}>{tag}</span>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Поля формы */}
          <div className="grid grid-cols-1 gap-3">
            <div>
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-1">
                Название документа <span className="text-slate-400">(необязательно)</span>
              </label>
              <input
                type="text"
                placeholder={formData.documentType ? TITLE_PLACEHOLDERS[formData.documentType] : ''}
                value={formData.title}
                onChange={(e) => updateFormData({ title: e.target.value })}
                className="input-field"
              />
            </div>
            {formData.documentType && (DOC_FIELDS[formData.documentType] ?? []).map(renderField)}
          </div>

          {/* Кнопки навигации */}
          <div className="flex justify-between pt-1">
            <button className="btn-secondary" onClick={() => setStep(1)}>
              <ChevronLeft size={15} /> Назад
            </button>
            <button className="btn-primary" disabled={!formData.documentType} onClick={handleGenerate}>
              <Sparkles size={15} /> Сгенерировать
            </button>
          </div>
        </div>
      )}

      {/* Шаг 3: Генерация */}
      {step === 3 && (
        <div className="flex flex-col items-center gap-4 py-8">
          {isGenerating && (
            <>
              <div className="relative w-12 h-12">
                <div className="absolute inset-0 rounded-full border-4 border-blue-100 dark:border-blue-900" />
                <div className="absolute inset-0 rounded-full border-4 border-blue-600 border-t-transparent animate-spin" />
              </div>
              <div className="text-center">
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Генерация документа...</p>
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Применяем требования стандартов</p>
              </div>
            </>
          )}
          {generationStatus === 'success' && (
            <>
              <div className="w-12 h-12 rounded-full bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center">
                <CheckCircle2 size={24} className="text-emerald-600 dark:text-emerald-400" />
              </div>
              <div className="text-center">
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Документ сформирован</p>
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Результат отображён справа</p>
              </div>
              <button className="btn-secondary text-xs" onClick={handleReset}>
                <RotateCcw size={13} /> Новый документ
              </button>
            </>
          )}
          {generationStatus === 'error' && (
            <>
              <div className="w-full rounded-xl border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/40 p-4 flex flex-col items-center gap-3 text-center">
                <AlertTriangle size={24} className="text-red-500 dark:text-red-400" />
                <div>
                  <p className="text-sm font-semibold text-red-700 dark:text-red-300">Ошибка генерации</p>
                  <p className="text-xs text-red-500 dark:text-red-400 mt-1 break-words max-w-xs">
                    {generationError ?? 'Не удалось создать документ. Попробуйте снова.'}
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <button className="btn-secondary text-xs" onClick={() => setStep(2)}>
                  <ChevronLeft size={13} /> Вернуться к настройкам
                </button>
                <button className="btn-primary text-xs" onClick={handleGenerate}>
                  <RotateCcw size={13} /> Повторить
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
