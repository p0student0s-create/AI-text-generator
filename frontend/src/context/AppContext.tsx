import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react';
import type {
  PageId,
  WizardFormData,
  GenerationResult,
  GenerationStatus,
  HistoryEntry,
  AppSettings,
  StandardId,
} from '../types';
import { api, downloadGeneratedDocument } from '../services/api';

// === Ключи localStorage ===
const HISTORY_STORAGE_KEY = 'secDocs_history_v1';
const SETTINGS_STORAGE_KEY = 'secDocs_settings_v1';

// === Утилиты для localStorage ===
function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Array<Omit<HistoryEntry, 'generatedAt'> & { generatedAt: string }>;
    return parsed.map((e) => ({ ...e, generatedAt: new Date(e.generatedAt) }));
  } catch {
    return [];
  }
}

function saveHistory(entries: HistoryEntry[]): void {
  try {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // quota exceeded — ignore silently
  }
}

function loadSettings(defaults: AppSettings): AppSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return defaults;
    return { ...defaults, ...JSON.parse(raw) };
  } catch {
    return defaults;
  }
}

function saveSettings(s: AppSettings): void {
  try {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(s));
  } catch {
    // ignore
  }
}

// === Интерфейс контекста ===
interface AppContextValue {
  activePage: PageId;
  setActivePage: (page: PageId) => void;
  formData: WizardFormData;
  updateFormData: (patch: Partial<WizardFormData>) => void;
  resetForm: () => void;
  generationStatus: GenerationStatus;
  generationResult: GenerationResult | null;
  generationError: string | null;
  generateDocument: () => Promise<void>;
  history: HistoryEntry[];
  clearHistory: () => void;
  settings: AppSettings;
  updateSettings: (patch: Partial<AppSettings>) => void;
  actualizeEntry: (entry: HistoryEntry) => void;
  actualizeFormData: WizardFormData | null;
  setActualizeFormData: (data: WizardFormData | null) => void;
}

// === Дефолтные значения ===
const DEFAULT_FORM: WizardFormData = {
  documentType: null,
  standards: ['FZ152', 'FSTEC239'],
  title: '',
  organizationName: '',
  protectionObject: '',
  dataCategory: '',
  regulationTopic: '',
  instructionRole: '',
  instructionTopic: '',
  infrastructureType: '',
  systemType: '',
  additionalContext: '',
};

const DEFAULT_SETTINGS: AppSettings = {
  defaultStandards: ['FZ152', 'FSTEC239'],
  organizationName: '',
  autoSaveHistory: true,
  language: 'ru',
  autoActualize: false,
  autoActualizePeriod: 'yearly',
};

const AppContext = createContext<AppContextValue | null>(null);

// === Провайдер ===
export function AppProvider({ children }: { children: ReactNode }) {
  const [activePage, setActivePage] = useState<PageId>('dashboard');
  const [formData, setFormData] = useState<WizardFormData>(DEFAULT_FORM);
  const [generationStatus, setGenerationStatus] = useState<GenerationStatus>('idle');
  const [generationResult, setGenerationResult] = useState<GenerationResult | null>(null);
  const [generationError, setGenerationError] = useState<string | null>(null);
  
  // Инициализация из localStorage
  const [history, setHistory] = useState<HistoryEntry[]>(() => loadHistory());
  const [settings, setSettings] = useState<AppSettings>(() => loadSettings(DEFAULT_SETTINGS));
  
  const [actualizeFormData, setActualizeFormData] = useState<WizardFormData | null>(null);

  // === Обновление формы ===
  const updateFormData = useCallback((patch: Partial<WizardFormData>) => {
    setFormData((prev) => ({ ...prev, ...patch }));
  }, []);

  // === Сброс формы ===
  const resetForm = useCallback(() => {
    setFormData((prev) => ({ ...DEFAULT_FORM, standards: prev.standards }));
    setGenerationStatus('idle');
    setGenerationResult(null);
    setGenerationError(null);
  }, []);

  // === Генерация документа (реальный API) ===
  const generateDocument = useCallback(async () => {
    if (!formData.documentType) return;
    
    setGenerationStatus('generating');
    setGenerationError(null);
    
    try {
      const result = await api.generateDocument(formData);
      
      setGenerationResult(result);
      setGenerationStatus('success');
      
      // Скачивание файла, если есть ссылка
      if (result.download_url) {
        await downloadGeneratedDocument(
          result.download_url,
          `${result.document_id || result.id || 'document'}.docx`
        );
      }

      // Сохранение в историю
      if (settings.autoSaveHistory) {
        const entry: HistoryEntry = {
          id: result.id,
          title: result.title,
          documentType: result.documentType,
          standards: result.standards,
          organizationName: result.organizationName,
          generatedAt: result.generatedAt,
          wordCount: result.wordCount,
          status: 'completed',
          formSnapshot: { ...formData }, // Сохраняем параметры формы для актуализации
        };
        setHistory((prev) => [entry, ...prev]);
      }
    } catch (err) {
      setGenerationStatus('error');
      setGenerationError(
        err instanceof Error ? err.message : 'Ошибка генерации. Попробуйте снова.'
      );
    }
  }, [formData, settings.autoSaveHistory]);

  // === Синхронизация с localStorage ===
  useEffect(() => { saveHistory(history); }, [history]);
  useEffect(() => { saveSettings(settings); }, [settings]);

  // === Очистка истории ===
  const clearHistory = useCallback(() => setHistory([]), []);

  // === Обновление настроек ===
  const updateSettings = useCallback((patch: Partial<AppSettings>) => {
    setSettings((prev) => ({ ...prev, ...patch }));
  }, []);

  // === Актуализация документа ===
  const actualizeEntry = useCallback((entry: HistoryEntry) => {
    const base: WizardFormData = entry.formSnapshot
      ? { ...DEFAULT_FORM, ...entry.formSnapshot }
      : {
          ...DEFAULT_FORM,
          documentType: entry.documentType,
          standards: entry.standards,
          organizationName: entry.organizationName,
          title: entry.title,
        };
    setActualizeFormData(base);
    setActivePage('actualize');
  }, []);

  return (
    <AppContext.Provider
      value={{
        activePage,
        setActivePage,
        formData,
        updateFormData,
        resetForm,
        generationStatus,
        generationResult,
        generationError,
        generateDocument,
        history,
        clearHistory,
        settings,
        updateSettings,
        actualizeEntry,
        actualizeFormData,
        setActualizeFormData,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

// === Хук для использования контекста ===
export function useAppContext(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used within AppProvider');
  return ctx;
}
