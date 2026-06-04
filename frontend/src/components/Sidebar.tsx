import React from 'react';
import { FilePlus, History, Database, Settings, ChevronRight, RefreshCw } from 'lucide-react';
import type { PageId } from '../types';
import { useAppContext } from '../context/AppContext';

interface NavEntry {
  id: PageId;
  label: string;
  Icon: React.ElementType;
}

const NAV_ITEMS: NavEntry[] = [
  { id: 'generator', label: 'Новый документ', Icon: FilePlus },
  { id: 'history', label: 'История', Icon: History },
  { id: 'actualize', label: 'Актуализация', Icon: RefreshCw },
  { id: 'dashboard', label: 'База знаний', Icon: Database },
  { id: 'settings', label: 'Настройки', Icon: Settings },
];

export function Sidebar() {
  const { activePage, setActivePage, history } = useAppContext();

  return (
    <aside
      className="w-56 shrink-0 bg-white dark:bg-slate-900
                 border-r border-slate-200 dark:border-slate-700
                 flex flex-col py-4 px-3 gap-1 overflow-y-auto"
    >
      <p className="section-heading px-3 mb-2">Навигация</p>

      {NAV_ITEMS.map(({ id, label, Icon }) => {
        const isActive = activePage === id;
        const showBadge = id === 'history' && history.length > 0;
        return (
          <button
            key={id}
            onClick={() => setActivePage(id)}
            className={`nav-item ${isActive ? 'nav-item-active' : ''}`}
          >
            <Icon size={16} className="shrink-0" />
            <span className="flex-1">{label}</span>
            {showBadge && (
              <span className="badge bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300">
                {history.length}
              </span>
            )}
            {isActive && !showBadge && (
              <ChevronRight size={13} className="opacity-40" />
            )}
          </button>
        );
      })}

      <div className="mt-auto pt-4 border-t border-slate-100 dark:border-slate-800">
        <div className="px-3 py-2 space-y-0.5">
          <p className="text-xs text-slate-400 dark:text-slate-500 font-medium">SecDocs AI v1.0</p>
          <p className="text-xs text-slate-400 dark:text-slate-500">ГОСТ · ФСТЭК · ISO 27001</p>
        </div>
      </div>
    </aside>
  );
}
