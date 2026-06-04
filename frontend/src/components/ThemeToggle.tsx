import React from 'react';
import { Sun, Moon } from 'lucide-react';
import { useTheme } from '../hooks/useTheme';

export function ThemeToggle() {
  const { isDark, toggleTheme } = useTheme();
  return (
    <button
      onClick={toggleTheme}
      aria-label={isDark ? 'Переключить на светлую тему' : 'Переключить на тёмную тему'}
      className="p-2 rounded-lg text-slate-500 dark:text-slate-400
                 hover:bg-slate-100 dark:hover:bg-slate-800
                 transition-colors duration-150"
    >
      {isDark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
