// frontend/src/services/api.ts
import type {
  WizardFormData,
  GenerationResult,
  GeneratedSection,
  Source,
  StandardId,
  DocumentTypeId,
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const API_TIMEOUT_MS = 3600_000;

function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}

function mapStandardIdToBackend(std: StandardId): string {
  const map: Record<StandardId, string> = {
    FZ152: '152_fz',
    FZ187: '187_fz',
    FSTEC17: 'fstek_17',
    FSTEC21: 'fstek_21',
    FSTEC_MD: 'fstek_md',
    FSTEC239: 'fstek_239',
    GOST57580: 'gost_57580',
    ISO27001: 'iso_27001',
    NIST: 'nist_800_53',
    GDPR: 'gdpr',
    'PCI-DSS': 'pci_dss',
    CIS: 'cis_controls',
  };
  return map[std] || std.toLowerCase();
}

function mapDocumentTypeToBackend(type: DocumentTypeId): string {
  return type;
}

// === SSE Event Types ===
export interface StreamEvent {
  type: string;
  [key: string]: any;
}

export type StreamEventHandler = (event: StreamEvent) => void;

/**
 * Streaming генерация документа через SSE
 */
export async function generateDocumentStream(
  form: WizardFormData,
  onEvent: StreamEventHandler,
  signal?: AbortSignal
): Promise<GenerationResult> {
  const requestBody = {
    doc_type: mapDocumentTypeToBackend(form.documentType!),
    standards: form.standards.map(mapStandardIdToBackend),
    title: form.title || 'Документ',
    organization: form.organizationName || 'Организация',
    object_type: form.protectionObject || 'Информационная система',
    data_category: form.dataCategory || 'Конфиденциальная информация',
  };

  const response = await fetch(`${API_BASE}/api/documents/generate-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
    signal,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';
  let generationId = '';
  let sections: GeneratedSection[] = [];
  let currentSection: GeneratedSection | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (!data) continue;
        
        try {
          const event: StreamEvent = JSON.parse(data);
          onEvent(event);

          // Обработка событий
          if (event.type === 'generation_id') {
            generationId = event.generation_id;
          } else if (event.type === 'section_start') {
            currentSection = {
              id: uid(),
              title: `${event.section_number}. ${event.section_title}`,
              content: '',
              wordCount: 0,
            };
          } else if (event.type === 'text_chunk' && currentSection) {
            currentSection.content += event.chunk;
            currentSection.wordCount = currentSection.content.split(/\s+/).length;
            // Обновляем последний раздел в массиве
            const idx = sections.findIndex(s => s.id === currentSection!.id);
            if (idx >= 0) {
              sections[idx] = { ...currentSection };
            } else {
              sections.push({ ...currentSection });
            }
          } else if (event.type === 'section_complete' && currentSection) {
            currentSection.wordCount = event.word_count || currentSection.wordCount;
            const idx = sections.findIndex(s => s.id === currentSection!.id);
            if (idx >= 0) {
              sections[idx] = { ...currentSection };
            }
            currentSection = null;
          } else if (event.type === 'completed') {
            const result = event.result;
            return {
              id: result.document_id || uid(),
              documentType: form.documentType!,
              title: result.context?.title || form.title || 'Документ',
              sections,
              sources: [],
              standards: form.standards,
              organizationName: form.organizationName,
              generatedAt: new Date(),
              wordCount: sections.reduce((acc, s) => acc + s.wordCount, 0),
              pageEstimate: Math.max(1, Math.ceil(sections.reduce((acc, s) => acc + s.wordCount, 0) / 300)),
              document_id: result.document_id,
              download_url: result.download_url,
              file_path: result.file_path,
              compliance_score: result.compliance?.score,
            };
          } else if (event.type === 'error') {
            throw new Error(event.error || 'Ошибка генерации');
          }
        } catch (e) {
          console.warn('Failed to parse SSE event:', data);
        }
      }
    }
  }

  throw new Error('Stream ended without completion');
}

/**
 * Отправка дополнительного промпта во время генерации
 */
export async function sendAdditionalPrompt(
  generationId: string,
  prompt: string
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/documents/prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      generation_id: generationId,
      prompt,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Не удалось отправить промпт');
  }
}

/**
 * Отмена генерации
 */
export async function cancelGeneration(generationId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/documents/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ generation_id: generationId }),
  });

  if (!response.ok) {
    throw new Error('Не удалось отменить генерацию');
  }
}

export async function downloadGeneratedDocument(
  downloadUrl: string,
  filename?: string,
  format: 'docx' | 'pdf' = 'docx'
): Promise<void> {
  try {
    const fullUrl = downloadUrl.startsWith('http')
      ? `${downloadUrl}${downloadUrl.includes('?') ? '&' : '?'}format=${format}`
      : `${API_BASE}${downloadUrl}?format=${format}`;
    
    const response = await fetch(fullUrl, {
      method: 'GET',
      headers: {
        'Accept': format === 'pdf'
          ? 'application/pdf'
          : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      }
    });

    if (!response.ok) {
      throw new Error(`Ошибка скачивания: ${response.status} ${response.statusText}`);
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `document_${Date.now()}.${format}`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (error) {
    console.error('Ошибка при скачивании документа:', error);
    throw error;
  }
}

export const api = {
  async generateDocument(form: WizardFormData, outputFormat: 'docx' | 'pdf' = 'docx'): Promise<GenerationResult> {
    // Legacy method — используем streaming internally
    let finalResult: GenerationResult | null = null;
    await generateDocumentStream(form, () => {}, undefined);
    return finalResult!;
  },

  generateDocumentStream,
  sendAdditionalPrompt,
  cancelGeneration,

  async downloadDocument(documentId: string, filename?: string, format: 'docx' | 'pdf' = 'docx'): Promise<void> {
    await downloadGeneratedDocument(
      `/api/documents/${documentId}/download`,
      filename || `${documentId}.${format}`,
      format
    );
  },

  async getAvailableStandards(): Promise<Array<{ id: StandardId; name: string; description: string; available: boolean }>> {
    try {
      const response = await fetch(`${API_BASE}/api/standards`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
      });
      if (!response.ok) return [];
      const data: any[] = await response.json();
      return data.map((item: any) => ({
        id: item.id.toUpperCase().replace(/[^A-Z0-9]/g, '') as StandardId,
        name: item.name,
        description: item.description,
        available: item.available,
      }));
    } catch (error) {
      console.error('Ошибка загрузки стандартов:', error);
      return [];
    }
  },

  async healthCheck(): Promise<{ ok: boolean; services: Record<string, string> }> {
    try {
      const response = await fetch(`${API_BASE}/health`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
      });
      if (!response.ok) return { ok: false, services: {} };
      const data: any = await response.json();
      return { ok: data.status === 'healthy', services: data.services || {} };
    } catch (error) {
      console.error('Ошибка health check:', error);
      return { ok: false, services: {} };
    }
  },
};