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
const USE_MOCK_API = false;

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

function mapBackendResponseToFrontend(
  backend: any,
  form: WizardFormData
): GenerationResult {
  const sections: GeneratedSection[] = (backend.sections || []).map((s: any) => ({
    id: uid(),
    title: s.title || s.section_number || 'Раздел',
    content: s.content || '',
    wordCount: s.word_count || s.content?.split(/\s+/).length || 0,
  }));

  const sources: Source[] = (backend.normative_links || []).map((ref: string) => ({
    id: uid(),
    standard: ref,
    clause: '',
    text: `Требование из ${ref}`,
  }));

  if (sources.length === 0 && form.standards.length > 0) {
    form.standards.forEach((std) => {
      sources.push({
        id: uid(),
        standard: std,
        clause: '',
        text: `Требование стандарта ${std}`,
      });
    });
  }

  const totalWords = sections.reduce((acc, s) => acc + s.wordCount, 0);

  return {
    id: backend.document_id || uid(),
    documentType: form.documentType!,
    title: backend.title || form.title || 'Документ',
    sections,
    sources,
    standards: form.standards,
    organizationName: form.organizationName,
    generatedAt: new Date(),
    wordCount: totalWords,
    pageEstimate: Math.max(1, Math.ceil(totalWords / 300)),
  };
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

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), API_TIMEOUT_MS);

    try {
      const requestBody = {
        doc_type: mapDocumentTypeToBackend(form.documentType!),
        standards: form.standards.map(mapStandardIdToBackend),
        title: form.title || 'Документ',
        organization: form.organizationName || 'Организация',
        object_type: form.protectionObject || 'Информационная система',
        data_category: form.dataCategory || 'Конфиденциальная информация',
        output_format: outputFormat,
      };

      const response = await fetch(`${API_BASE}/api/documents/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      const backendResult = await response.json();
      return mapBackendResponseToFrontend(backendResult, form);

    } catch (error) {
      clearTimeout(timeout);
      
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new Error('Таймаут генерации. Документ слишком сложный или сервер перегружен.');
      }
      
      if (error instanceof Error) {
        throw error;
      }
      
      throw new Error('Неизвестная ошибка при генерации документа.');
    }
  },

  async downloadDocument(documentId: string, filename?: string, format: 'docx' | 'pdf' = 'docx'): Promise<void> {

    await downloadGeneratedDocument(
      `/api/documents/${documentId}/download`,
      filename || `${documentId}.${format}`,
      format
    );
  },

  async getAvailableStandards(): Promise<Array<{
    id: StandardId;
    name: string;
    description: string;
    available: boolean;
  }>> {

    try {
      const response = await fetch(`${API_BASE}/api/standards`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
      });

      if (!response.ok) {
        console.warn('Не удалось загрузить стандарты с бэкенда, используем заглушку');
        return [];
      }

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
      
      return {
        ok: data.status === 'healthy',
        services: data.services || {},
      };
    } catch (error) {
      console.error('Ошибка health check:', error);
      return { ok: false, services: {} };
    }
  },
};