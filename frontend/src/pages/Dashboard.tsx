import React from 'react';
import { FileText, ShieldCheck, BookOpen, ArrowRight, Zap, Clock } from 'lucide-react';
import { KnowledgeGraphWidget } from '../components/KnowledgeGraphWidget';
import { useAppContext } from '../context/AppContext';

interface StatCardProps {
  label: string;
  value: string | number;
  sub: string;
  Icon: React.ElementType;
  colorClass: string;
}

function StatCard({ label, value, sub, Icon, colorClass }: StatCardProps) {
  return (
    <div className="card p-4 flex items-center gap-4">
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${colorClass}`}>
        <Icon size={18} className="text-white" />
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 leading-none">{value}</p>
        <p className="text-xs font-medium text-slate-700 dark:text-slate-300 mt-0.5">{label}</p>
        <p className="text-xs text-slate-400 dark:text-slate-500">{sub}</p>
      </div>
    </div>
  );
}

const KNOWLEDGE_BASE_ENTRIES = [
  {
    standard: 'ГОСТ Р 57580.1-2017',
    description: 'Безопасность финансовых (банковских) операций. Управление документами.',
    tag: 'РФ',
    tagColor: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
  },
  {
    standard: 'Приказ ФСТЭК №239',
    description: 'Требования по обеспечению безопасности значимых объектов КИИ.',
    tag: 'РФ',
    tagColor: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
  },
  {
    standard: 'ISO/IEC 27001:2022',
    description: 'Системы менеджмента информационной безопасности. Требования.',
    tag: 'ISO',
    tagColor: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  },
  {
    standard: 'NIST SP 800-53 Rev. 5',
    description: 'Меры безопасности и конфиденциальности для систем и организаций.',
    tag: 'NIST',
    tagColor: 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300',
  },
  {
    standard: 'GDPR (Регламент ЕС 2016/679)',
    description: 'Общий регламент о защите персональных данных граждан ЕС.',
    tag: 'EU',
    tagColor: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300',
  },
  {
    standard: 'PCI DSS v4.0',
    description: 'Стандарт безопасности данных индустрии платёжных карт.',
    tag: 'PCI',
    tagColor: 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300',
  },
  {
    standard: 'CIS Controls v8',
    description: 'Приоритизированный набор мер кибербезопасности для снижения рисков.',
    tag: 'CIS',
    tagColor: 'bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300',
  },
];

export function Dashboard() {
  const { history, setActivePage } = useAppContext();

  return (
    <div className="flex flex-col gap-5 p-5 max-w-4xl mx-auto w-full">
      <div>
        <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">База знаний</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
          Нормативная база и визуализация связей требований ИБ
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <StatCard
          label="Документов создано"
          value={history.length}
          sub="за текущую сессию"
          Icon={FileText}
          colorClass="bg-blue-500"
        />
        <StatCard
          label="Стандартов в базе"
          value={7}
          sub="нормативных документов"
          Icon={ShieldCheck}
          colorClass="bg-emerald-500"
        />
        <StatCard
          label="Время генерации"
          value="~1.5с"
          sub="на документ"
          Icon={Clock}
          colorClass="bg-amber-500"
        />
      </div>

      <KnowledgeGraphWidget />

      <div className="card p-4 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <BookOpen size={15} className="text-blue-500" />
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            Подключённые стандарты
          </h2>
        </div>
        <div className="flex flex-col gap-2">
          {KNOWLEDGE_BASE_ENTRIES.map(({ standard, description, tag, tagColor }) => (
            <div
              key={standard}
              className="flex items-start gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/50
                         border border-slate-100 dark:border-slate-700"
            >
              <span className={`badge shrink-0 mt-0.5 ${tagColor}`}>{tag}</span>
              <div>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{standard}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">{description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card p-4 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Zap size={15} className="text-blue-500" />
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            Быстрые действия
          </h2>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {[
            { label: 'Создать политику ИБ', page: 'generator' as const },
            { label: 'Сформировать модель угроз', page: 'generator' as const },
            { label: 'История генераций', page: 'history' as const },
            { label: 'Настройки системы', page: 'settings' as const },
          ].map(({ label, page }) => (
            <button
              key={label}
              onClick={() => setActivePage(page)}
              className="flex items-center justify-between p-3 rounded-xl border
                         border-slate-100 dark:border-slate-700 text-left
                         hover:border-blue-300 dark:hover:border-blue-700
                         hover:bg-blue-50 dark:hover:bg-blue-950/30
                         transition-all duration-150 group"
            >
              <span className="text-sm text-slate-700 dark:text-slate-300">{label}</span>
              <ArrowRight
                size={14}
                className="text-slate-400 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors"
              />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
