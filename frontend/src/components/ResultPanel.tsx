import React, { useState, useRef, useEffect } from 'react';
import { Copy, Download, RefreshCw, CircleAlert as AlertCircle, ChevronDown, ChevronUp, CircleCheck as CheckCircle2 } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { SourcesList } from './SourcesList';
import { MarkdownRenderer } from './MarkdownRenderer';
import { downloadAsDocx, downloadAsPdf } from '../services/documentExport';

const DOC_TYPE_LABELS: Record<string, string> = {
  policy: 'Политика ИБ', regulation: 'Регламент', instruction: 'Инструкция',
  threat_model: 'Модель угроз', risk_assessment: 'Оценка рисков',
  incident_response: 'Реагирование на инциденты', access_control: 'Управление доступом',
};

export function ResultPanel() {
  const { generationStatus, generationResult, generationError, generateDocument } = useAppContext();
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState(false);
  const [downloadMenuOpen, setDownloadMenuOpen] = useState(false);
  const downloadMenuRef = useRef<HTMLDivElement>(null);

  // Закрытие меню при клике вне
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (downloadMenuRef.current && !downloadMenuRef.current.contains(e.target as Node)) {
        setDownloadMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const toggleSection = (id: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const expandAll = () => {
    if (!generationResult) return;
    setExpandedSections(new Set(generationResult.sections.map((s) => s.id)));
  };

  const collapseAll = () => setExpandedSections(new Set());

  const handleCopy = () => {
    if (!generationResult) return;
    const text = [
      `# ${generationResult.title}`, '',
      ...generationResult.sections.map((s) => `## ${s.title}\n\n${s.content}`),
    ].join('\n\n');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadDocx = async () => {
    if (!generationResult) return;
    setDownloadMenuOpen(false);
    await downloadAsDocx(generationResult);
  };

  const handleDownloadPdf = () => {
    if (!generationResult) return;
    setDownloadMenuOpen(false);
    downloadAsPdf(generationResult);
  };

  // === Состояния загрузки / ошибки ===
  if (generationStatus === 'generating') {
    return (
      <div className="card p-5 flex flex-col gap-4 animate-pulse">
        <div className="h-5 bg-slate-200 dark:bg-slate-700 rounded-lg w-2/3" />
        <div className="h-3 bg-slate-100 dark:bg-slate-700/60 rounded w-1/3" />
        <div className="flex gap-2">
          <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded-full w-20" />
          <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded-full w-24" />
        </div>
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-12 bg-slate-100 dark:bg-slate-700/60 rounded-xl" />
        ))}
      </div>
    );
  }

  if (generationStatus === 'error') {
    return (
      <div className="card p-5 flex flex-col gap-3">
        <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
          <AlertCircle size={18} />
          <span className="font-semibold text-sm">Ошибка генерации</span>
        </div>
        <p className="text-sm text-slate-600 dark:text-slate-400">{generationError}</p>
        <button className="btn-secondary self-start" onClick={() => generateDocument()}>
          <RefreshCw size={14} /> Повторить
        </button>
      </div>
    );
  }

  if (!generationResult) return null;

  const { title, sections, sources, wordCount, pageEstimate, generatedAt, standards, documentType } = generationResult;
  const allExpanded = expandedSections.size === sections.length;

  return (
    <div className="card p-5 flex flex-col gap-5">
      {/* Заголовок результата */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle2 size={16} className="text-emerald-500 shrink-0" />
            <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">Сгенерировано успешно</span>
          </div>
          <h2 className="text-base font-bold text-slate-900 dark:text-slate-100 leading-tight">{title}</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            {DOC_TYPE_LABELS[documentType]} · {generatedAt.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })} · {wordCount.toLocaleString('ru-RU')} слов · ≈{pageEstimate} стр.
          </p>
          {standards.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {standards.map((s) => {
                const labels: Record<string, string> = {
                  GOST57580: 'ГОСТ 57580', FSTEC239: 'ФСТЭК №239', ISO27001: 'ISO 27001',
                  NIST: 'NIST', GDPR: 'GDPR', 'PCI-DSS': 'PCI DSS', CIS: 'CIS v8',
                };
                return <span key={s} className="badge bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">{labels[s] || s}</span>;
              })}
            </div>
          )}
        </div>
        {/* Кнопки действий */}
        <div className="flex flex-col gap-2 shrink-0">
          <button onClick={handleCopy} className="btn-secondary text-xs px-3 py-1.5">
            <Copy size={13} /> {copied ? 'Скопировано!' : 'Копировать'}
          </button>
          <div className="relative" ref={downloadMenuRef}>
            <button onClick={() => setDownloadMenuOpen(!downloadMenuOpen)} className="btn-primary text-xs px-3 py-1.5">
              <Download size={13} /> Скачать
            </button>
            {downloadMenuOpen && (
              <div className="absolute right-0 mt-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-lg shadow-lg z-10">
                <button onClick={handleDownloadDocx} className="block w-full text-left px-4 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700">
                  Скачать .docx
                </button>
                <button onClick={handleDownloadPdf} className="block w-full text-left px-4 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700">
                  Скачать .pdf
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Разделы документа с Markdown-рендерингом */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h3 className="section-heading">Содержание ({sections.length} разделов)</h3>
          <button onClick={allExpanded ? collapseAll : expandAll} className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
            {allExpanded ? 'Свернуть все' : 'Развернуть все'}
          </button>
        </div>
        {sections.map((section) => {
          const open = expandedSections.has(section.id);
          return (
            <div key={section.id} className="border border-slate-100 dark:border-slate-700 rounded-xl overflow-hidden">
              <button
                onClick={() => toggleSection(section.id)}
                className="w-full flex items-center justify-between px-4 py-3 text-left bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-700/60 transition-colors duration-150"
              >
                <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{section.title}</span>
                <div className="flex items-center gap-2 text-slate-400 shrink-0">
                  <span className="text-xs">{section.wordCount} сл.</span>
                  {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </div>
              </button>
              {open && (
                <div className="px-4 py-4 bg-white dark:bg-slate-800 border-t border-slate-100 dark:border-slate-700">
                  <MarkdownRenderer content={section.content} />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Источники */}
      <SourcesList sources={sources} />
    </div>
  );
}
