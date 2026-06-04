import React from 'react';
import { DocumentWizard } from '../components/DocumentWizard';
import { ResultPanel } from '../components/ResultPanel';
import { useAppContext } from '../context/AppContext';

export function DocumentGenerator() {
  const { generationStatus } = useAppContext();
  const hasResult = generationStatus !== 'idle';

  return (
    <div className={`p-5 flex gap-5 w-full h-full overflow-auto ${hasResult ? 'items-start' : 'items-start justify-center'}`}>
      <div className={`flex flex-col gap-4 ${hasResult ? 'w-72 shrink-0' : 'w-full max-w-lg'}`}>
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Новый документ
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Выберите тип, укажите параметры и нажмите «Сгенерировать»
          </p>
        </div>
        <DocumentWizard />
      </div>

      {hasResult && (
        <div className="flex-1 min-w-0 flex flex-col gap-4">
          <div className="h-[60px]" />
          <ResultPanel />
        </div>
      )}
    </div>
  );
}
