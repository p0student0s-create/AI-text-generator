import React from 'react';

interface Props {
  content: string;
  className?: string;
}

/**
 * Минимальный inline-Markdown рендерер без внешних зависимостей.
 * Поддерживает: **bold**, *italic*, `code`, ссылки [текст](url), заголовки # ## ###, списки - * 1.
 */
function renderInline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  // Паттерны: **bold**, *italic*, `code`, [link](url)
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[([^\]]+)\]\(([^)]+)\))/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    
    if (match[2] !== undefined) {
      parts.push(<strong key={match.index} className="font-semibold">{match[2]}</strong>);
    } else if (match[3] !== undefined) {
      parts.push(<em key={match.index}>{match[3]}</em>);
    } else if (match[4] !== undefined) {
      parts.push(
        <code key={match.index} className="px-1 py-0.5 bg-slate-100 dark:bg-slate-700 rounded text-xs font-mono">
          {match[4]}
        </code>
      );
    } else if (match[5] !== undefined && match[6] !== undefined) {
      parts.push(
        <a key={match.index} href={match[6]} target="_blank" rel="noopener noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline">
          {match[5]}
        </a>
      );
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function MarkdownRenderer({ content, className = '' }: Props) {
  const lines = content.split('\n');
  const nodes: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Заголовки ### ## #
    const heading = line.match(/^(#{1,3})\s+(.+)/);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2];
      const cls =
        level === 1 ? 'text-base font-bold text-slate-900 dark:text-slate-100 mt-4 mb-1' :
        level === 2 ? 'text-sm font-bold text-slate-800 dark:text-slate-200 mt-3 mb-1' :
        'text-sm font-semibold text-slate-700 dark:text-slate-300 mt-2 mb-0.5';
      nodes.push(<p key={i} className={cls}>{renderInline(text)}</p>);
      i++;
      continue;
    }

    // Нумерованный список
    const ordered = line.match(/^(\d+)\.\s+(.+)/);
    if (ordered) {
      const listItems: React.ReactNode[] = [];
      while (i < lines.length && lines[i].match(/^\d+\.\s+/)) {
        const m = lines[i].match(/^\d+\.\s+(.+)/);
        if (m) listItems.push(<li key={i} className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed ml-1">{renderInline(m[1])}</li>);
        i++;
      }
      nodes.push(<ol key={`ol-${i}`} className="list-decimal list-outside pl-5 flex flex-col gap-0.5 my-1">{listItems}</ol>);
      continue;
    }

    // Маркированный список (- или *)
    const unordered = line.match(/^[-*]\s+(.+)/);
    if (unordered) {
      const listItems: React.ReactNode[] = [];
      while (i < lines.length && lines[i].match(/^[-*]\s+/)) {
        const m = lines[i].match(/^[-*]\s+(.+)/);
        if (m) listItems.push(<li key={i} className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed ml-1">{renderInline(m[1])}</li>);
        i++;
      }
      nodes.push(<ul key={`ul-${i}`} className="list-disc list-outside pl-5 flex flex-col gap-0.5 my-1">{listItems}</ul>);
      continue;
    }

    // Горизонтальный разделитель
    if (line.match(/^(-{3,}|\*{3,}|_{3,})$/)) {
      nodes.push(<hr key={i} className="border-slate-200 dark:border-slate-600 my-2" />);
      i++;
      continue;
    }

    // Пустая строка
    if (line.trim() === '') { i++; continue; }

    // Обычный параграф
    nodes.push(<p key={i} className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{renderInline(line)}</p>);
    i++;
  }

  return <div className={`flex flex-col gap-1 ${className}`}>{nodes}</div>;
}
