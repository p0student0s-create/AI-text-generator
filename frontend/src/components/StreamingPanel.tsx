import React, { useState, useRef, useEffect } from 'react';
import {
  Sparkles,
  Send,
  X,
  Loader2,
  CheckCircle2,
  AlertCircle,
  FileText,
  Zap,
  MessageSquare,
} from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { MarkdownRenderer } from './MarkdownRenderer';

export function StreamingPanel() {
  const {
    streamingState,
    sendPrompt,
    cancelGen,
    generationStatus,
  } = useAppContext();
  
  const [promptInput, setPromptInput] = useState('');
  const [sentPrompts, setSentPrompts] = useState<string[]>([]);
  const [isSending, setIsSending] = useState(false);
  const contentEndRef = useRef<HTMLDivElement>(null);
  const promptInputRef = useRef<HTMLTextAreaElement>(null);

  // Автоскролл к последнему контенту
  useEffect(() => {
    contentEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [streamingState.sections]);

  const handleSendPrompt = async () => {
    if (!promptInput.trim() || isSending) return;
    
    setIsSending(true);
    try {
      await sendPrompt(promptInput.trim());
      setSentPrompts((prev) => [...prev, promptInput.trim()]);
      setPromptInput('');
    } catch (err) {
      console.error('Ошибка отправки промпта:', err);
    } finally {
      setIsSending(false);
      promptInputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendPrompt();
    }
  };

  const {
    currentStage,
    currentSection,
    currentSectionIndex,
    totalSections,
    progress,
    sections,
    generationId,
    error,
  } = streamingState;

  return (
    <div className="card p-5 flex flex-col gap-4 h-full">
      {/* Заголовок */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap size={18} className="text-blue-500 animate-pulse" />
          <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">
            Генерация в реальном времени
          </h2>
        </div>
        <button
          onClick={cancelGen}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg
            bg-red-50 dark:bg-red-950/40 text-red-600 dark:text-red-400
            hover:bg-red-100 dark:hover:bg-red-950/60 transition-colors"
        >
          <X size={13} /> Отменить
        </button>
      </div>

      {/* Прогресс-бар */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-600 dark:text-slate-400 font-medium">
            {currentStage || 'Инициализация...'}
          </span>
          <span className="text-slate-500 dark:text-slate-500">
            {Math.round(progress)}%
          </span>
        </div>
        <div className="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-blue-500 to-blue-600 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Информация о текущем разделе */}
      {currentSection && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800">
          <Loader2 size={14} className="text-blue-500 animate-spin" />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-blue-700 dark:text-blue-300">
              Генерация раздела {currentSectionIndex}/{totalSections}
            </p>
            <p className="text-xs text-blue-600 dark:text-blue-400 truncate">
              {currentSection}
            </p>
          </div>
        </div>
      )}

      {/* Сгенерированные разделы */}
      <div className="flex-1 overflow-y-auto min-h-0 border border-slate-200 dark:border-slate-700 rounded-xl p-3 bg-slate-50 dark:bg-slate-800/50">
        {sections.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center gap-2">
            <FileText size={32} className="text-slate-300 dark:text-slate-600" />
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Ожидание начала генерации...
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {sections.map((section) => (
              <div
                key={section.id}
                className="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden bg-white dark:bg-slate-800"
              >
                <div className="px-3 py-2 bg-slate-100 dark:bg-slate-700/50 border-b border-slate-200 dark:border-slate-700">
                  <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                    {section.title}
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {section.wordCount} слов
                  </p>
                </div>
                <div className="px-3 py-3">
                  <MarkdownRenderer content={section.content} />
                </div>
              </div>
            ))}
            <div ref={contentEndRef} />
          </div>
        )}
      </div>

      {/* Ввод дополнительного промпта */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <MessageSquare size={14} className="text-slate-500" />
          <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
            Добавить контекст во время генерации
          </span>
        </div>
        <div className="flex gap-2">
          <textarea
            ref={promptInputRef}
            value={promptInput}
            onChange={(e) => setPromptInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Например: 'Добавь требования к шифрованию данных', 'Упомяни конкретные системы организации'..."
            rows={2}
            className="input-field resize-none text-sm"
            disabled={generationStatus !== 'generating'}
          />
          <button
            onClick={handleSendPrompt}
            disabled={!promptInput.trim() || isSending || generationStatus !== 'generating'}
            className="btn-primary self-end h-10 px-3"
          >
            {isSending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
          </button>
        </div>
        {sentPrompts.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {sentPrompts.map((p, i) => (
              <span
                key={i}
                className="text-xs px-2 py-1 rounded-lg bg-emerald-50 dark:bg-emerald-950/40
                  text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800"
              >
                ✓ {p.slice(0, 50)}{p.length > 50 ? '...' : ''}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Ошибка */}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800">
          <AlertCircle size={14} className="text-red-500" />
          <p className="text-xs text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}
    </div>
  );
}