import { downloadGeneratedDocument } from './api';
import type { GenerationResult } from '../types';

export async function downloadAsDocx(result: GenerationResult): Promise<void> {
  if (!result.download_url) {
    throw new Error('URL для скачивания не предоставлен');
  }
  
  const filename = `${result.document_id || result.id || 'document'}.docx`;
  await downloadGeneratedDocument(result.download_url, filename);
}

export function downloadAsPdf(result: GenerationResult): void {
  console.warn('Скачивание PDF пока не реализовано. Используется DOCX.');
  // Опционально: перенаправить на DOCX
  // downloadAsDocx(result);
}

export function exportToMarkdown(content: { sections: Array<{ title: string; content: string }> }): string {
  let md = `# Сгенерированный документ\n\n`;
  
  for (const section of content.sections) {
    md += `## ${section.title}\n\n${section.content}\n\n`;
  }
  
  return md;
}

export function downloadMarkdown(content: string, filename: string = 'document.md'): void {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}
