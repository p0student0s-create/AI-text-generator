import React from 'react';
import { BookOpen, ExternalLink } from 'lucide-react';
import type { Source } from '../types';

interface Props {
  sources: Source[];
}

const STANDARD_COLORS: Record<string, string> = {
  'ГОСТ Р 57580.1-2017': 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
  'ГОСТ Р 57580.2-2018': 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
  'ФСТЭК №239': 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  'ISO/IEC 27001:2022': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300',
  'NIST SP 800-53 Rev.5': 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300',
  'GDPR': 'bg-teal-100 text-teal-700 dark:bg-teal-900/50 dark:text-teal-300',
  'PCI DSS v4.0': 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300',
  'CIS Controls v8': 'bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300',
};

function getStandardColor(standard: string) {
  return STANDARD_COLORS[standard] ?? 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300';
}

export function SourcesList({ sources }: Props) {
  if (!sources.length) return null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <BookOpen size={14} className="text-slate-400" />
        <h3 className="section-heading">Источники ({sources.length})</h3>
      </div>
      <div className="flex flex-col gap-2">
        {sources.map((src) => (
          <div
            key={src.id}
            className="p-3 rounded-xl border border-slate-100 dark:border-slate-700
                       bg-slate-50 dark:bg-slate-800/50 flex flex-col gap-2"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex flex-wrap gap-1.5">
                <span className={`badge ${getStandardColor(src.standard)}`}>
                  {src.standard}
                </span>
                <span className="badge bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400 font-mono text-xs">
                  {src.clause}
                </span>
              </div>
              {src.url && (
                <a
                  href={src.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors shrink-0"
                >
                  <ExternalLink size={13} />
                </a>
              )}
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              {src.text}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
