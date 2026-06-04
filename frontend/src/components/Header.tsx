import React from 'react';
import { ShieldCheck } from 'lucide-react';
import { ThemeToggle } from './ThemeToggle';

export function Header() {
  return (
    <header
      className="h-14 border-b border-slate-200 dark:border-slate-700
                 bg-white dark:bg-slate-900 flex items-center px-5 gap-3
                 sticky top-0 z-30 shrink-0"
    >
      <ShieldCheck size={22} className="text-blue-600 dark:text-blue-400" />
      <span className="font-bold text-slate-900 dark:text-slate-100 tracking-tight text-base">
        SecDocs<span className="text-blue-600 dark:text-blue-400">.AI</span>
      </span>
      <span className="text-xs text-slate-400 dark:text-slate-500 ml-1 hidden sm:block">
        Генератор документации ИБ
      </span>
      <div className="ml-auto flex items-center gap-1">
        <ThemeToggle />
      </div>
    </header>
  );
}
