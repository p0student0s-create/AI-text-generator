import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
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
  GeneratedSection,
  StreamEvent,
  StreamingState,
} from '../types';
import {
  api,
  generateDocumentStream,
  sendAdditionalPrompt,
  cancelGeneration,
  downloadGeneratedDocument,
} from '../services/api';

const HISTORY_STORAGE_KEY = 'secDocs_history_v1';
const SETTINGS_STORAGE_KEY = 'secDocs_settings_v1';

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
  } catch {}
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
  } catch {}
}

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
  // Streaming
  streamingState: StreamingState;
  sendPrompt: (prompt: string) => Promise<void>;
  cancelGen: () => Promise<void>;
}

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

const DEFAULT_STREAMING_STATE: StreamingState = {
  generationId: null,
  currentStage: '',
  currentSection: null,
  currentSectionIndex: 0,
  totalSections: 0,
  progress: 0,
  sections: [],
  additionalPrompts: [],
  error: null,
};

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activePage, setActivePage] = useState<PageId>('dashboard');
  const [formData, setFormData] = useState<WizardFormData>(DEFAULT_FORM);
  const [generationStatus, setGenerationStatus] = useState<GenerationStatus>('idle');
  const [generationResult, setGenerationResult] = useState<GenerationResult | null>(null);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>(() => loadHistory());
  const [settings, setSettings] = useState<AppSettings>(() => loadSettings(DEFAULT_SETTINGS));
  const [actualizeFormData, setActualizeFormData] = useState<WizardFormData | null>(null);
  const [streamingState, setStreamingState] = useState<StreamingState>(DEFAULT_STREAMING_STATE);
  
  const abortControllerRef = useRef<AbortController | null>(null);
  const generationIdRef = useRef<string | null>(null);

  const updateFormData = useCallback((patch: Partial<WizardFormData>) => {
    setFormData((prev) => ({ ...prev, ...patch }));
  }, []);

  const resetForm = useCallback(() => {
    setFormData((prev) => ({ ...DEFAULT_FORM, standards: prev.standards }));
    setGenerationStatus('idle');
    setGenerationResult(null);
    setGenerationError(null);
    setStreamingState(DEFAULT_STREAMING_STATE);
  }, []);

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    setStreamingState((prev) => {
      const next = { ...prev, sections: [...prev.sections] };
      
      switch (event.type) {
        case 'generation_id':
          next.generationId = event.generation_id;
          generationIdRef.current = event.generation_id;
          break;
        case 'status':
          next.currentStage = event.stage || event.message || prev.currentStage;
          if (event.progress !== undefined) next.progress = event.progress;
          break;
        case 'industry_detected':
          next.currentStage = `Отрасль: ${event.profile_name}`;
          break;
        case 'standards_filtered':
          next.currentStage = `Стандарты: ${event.standards?.length || 0} выбрано`;
          break;
        case 'structure_ready':
          next.totalSections = event.sections_count;
          next.currentStage = 'Структура готова';
          next.progress = 20;
          break;
        case 'section_start':
          next.currentSection = event.section_title;
          next.currentSectionIndex = event.index;
          next.progress = 30 + (40 * (event.index - 1) / Math.max(event.total, 1));
          break;
        case 'text_chunk': {
          const sectionTitle = event.section_title;
          const existingIdx = next.sections.findIndex(s => s.title.includes(sectionTitle));
          if (existingIdx >= 0) {
            const updated = { ...next.sections[existingIdx] };
            updated.content += event.chunk;
            updated.wordCount = updated.content.split(/\s+/).length;
            next.sections[existingIdx] = updated;
          } else {
            next.sections.push({
              id: `section_${sectionTitle}_${Date.now()}`,
              title: sectionTitle,
              content: event.chunk,
              wordCount: event.chunk.split(/\s+/).length,
            });
          }
          break;
        }
        case 'section_complete':
          next.currentSection = null;
          next.progress = 30 + (40 * event.index / Math.max(event.total, 1));
          const finalIdx = next.sections.findIndex(s => s.title.includes(event.section_title));
          if (finalIdx >= 0) {
            next.sections[finalIdx] = {
              ...next.sections[finalIdx],
              wordCount: event.word_count || next.sections[finalIdx].wordCount,
            };
          }
          break;
        case 'section_error':
          next.error = `Ошибка в разделе: ${event.section_title}`;
          break;
        case 'audit_complete':
          next.currentStage = 'Аудит завершён';
          next.progress = 85;
          break;
        case 'prompt_applied':
          next.additionalPrompts = [...next.additionalPrompts, event.prompt];
          break;
        case 'completed':
          next.progress = 100;
          next.currentStage = 'Завершено';
          break;
        case 'error':
          next.error = event.error;
          break;
      }
      
      return next;
    });
  }, []);

  const generateDocument = useCallback(async () => {
    if (!formData.documentType) return;
    
    setGenerationStatus('generating');
    setGenerationError(null);
    setStreamingState({
      ...DEFAULT_STREAMING_STATE,
      currentStage: 'Инициализация...',
    });
    
    abortControllerRef.current = new AbortController();
    
    try {
      const result = await generateDocumentStream(
        formData,
        handleStreamEvent,
        abortControllerRef.current.signal
      );
      
      setGenerationResult(result);
      setGenerationStatus('success');
      
      if (result.download_url) {
        try {
          await downloadGeneratedDocument(
            result.download_url,
            `${result.document_id || result.id || 'document'}.docx`
          );
        } catch (dlErr) {
          console.warn('Не удалось скачать файл:', dlErr);
        }
      }
      
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
          formSnapshot: { ...formData },
        };
        setHistory((prev) => [entry, ...prev]);
      }
    } catch (err) {
      setGenerationStatus('error');
      const errMsg = err instanceof Error ? err.message : 'Ошибка генерации';
      setGenerationError(errMsg);
      setStreamingState((prev) => ({ ...prev, error: errMsg }));
    }
  }, [formData, settings.autoSaveHistory, handleStreamEvent]);

  const sendPrompt = useCallback(async (prompt: string) => {
    if (!generationIdRef.current) {
      throw new Error('Нет активной генерации');
    }
    await sendAdditionalPrompt(generationIdRef.current, prompt);
    setStreamingState((prev) => ({
      ...prev,
      additionalPrompts: [...prev.additionalPrompts, prompt],
    }));
  }, []);

  const cancelGen = useCallback(async () => {
    if (generationIdRef.current) {
      try {
        await cancelGeneration(generationIdRef.current);
      } catch {}
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setGenerationStatus('error');
    setGenerationError('Генерация отменена пользователем');
  }, []);

  useEffect(() => { saveHistory(history); }, [history]);
  useEffect(() => { saveSettings(settings); }, [settings]);

  const clearHistory = useCallback(() => setHistory([]), []);
  const updateSettings = useCallback((patch: Partial<AppSettings>) => {
    setSettings((prev) => ({ ...prev, ...patch }));
  }, []);

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

  const value: AppContextValue = {
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
    streamingState,
    sendPrompt,
    cancelGen,
  };

  return (
    <AppContext.Provider value={value}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used within AppProvider');
  return ctx;
}
