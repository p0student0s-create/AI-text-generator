export type PageId = 'dashboard' | 'generator' | 'history' | 'settings' | 'actualize';

export type StandardId =
  | 'FZ152' | 'FZ187' | 'FSTEC239' | 'FSTEC17' | 'FSTEC21' | 'FSTEC_MD'
  | 'GOST57580' | 'ISO27001' | 'NIST' | 'GDPR' | 'PCI-DSS' | 'CIS';

export interface SecurityStandard {
  id: StandardId;
  label: string;
  description: string;
}

export type DocumentTypeId =
  | 'policy' | 'regulation' | 'instruction' | 'threat_model'
  | 'risk_assessment' | 'incident_response' | 'access_control';

export interface DocumentType {
  id: DocumentTypeId;
  label: string;
  description: string;
  estimatedPages: string;
  icon: string;
  color: string;
}

export interface WizardFormData {
  documentType: DocumentTypeId | null;
  standards: StandardId[];
  title: string;
  organizationName: string;
  industry?: string;
  protectionObject?: string;
  dataCategory?: string;
  regulationTopic?: string;
  instructionRole?: string;
  instructionTopic?: string;
  infrastructureType?: string;
  additionalContext?: string;
  systemType?: string;
}

export type IndustryType = 'medical' | 'education' | 'energy' | 'finance' | 'government' | 'transport' | 'industrial' | 'other';

export interface Source {
  id: string;
  standard: string;
  clause: string;
  text: string;
  url?: string;
}

export interface GeneratedSection {
  id: string;
  title: string;
  content: string;
  wordCount: number;
}

export interface GenerationResult {
  id: string;
  documentType: DocumentTypeId;
  title: string;
  sections: GeneratedSection[];
  sources: Source[];
  standards: StandardId[];
  organizationName: string;
  generatedAt: Date;
  wordCount: number;
  pageEstimate: number;
  document_id?: string;
  download_url?: string;
  file_path?: string;
  sections_count?: number;
  compliance_score?: number;
}

// Убедитесь, что HistoryEntry определён ОДИН РАЗ
export interface HistoryEntry {
  id: string;
  title: string;
  documentType: DocumentTypeId;
  standards: StandardId[];
  organizationName: string;
  generatedAt: Date;
  wordCount: number;
  status: 'completed' | 'error';
  formSnapshot?: Partial<WizardFormData>;
}

export type AutoActualizePeriod = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'biannual' | 'yearly';

export interface KGNode {
  id: string;
  label: string;
  type: 'standard' | 'control' | 'threat' | 'asset';
  x: number;
  y: number;
  size: number;
  color: string;
}

export interface KGEdge {
  from: string;
  to: string;
  strength: number;
}

export interface KnowledgeGraphData {
  nodes: KGNode[];
  edges: KGEdge[];
}

export interface AppSettings {
  defaultStandards: StandardId[];
  organizationName: string;
  autoSaveHistory: boolean;
  language: 'ru' | 'en';
  autoActualize: boolean;
  autoActualizePeriod: AutoActualizePeriod;
}

// === Streaming types ===
export type GenerationStatus = 'idle' | 'generating' | 'success' | 'error';

export interface StreamEvent {
  type: string;
  [key: string]: any;
}

export interface StreamingState {
  generationId: string | null;
  currentStage: string;
  currentSection: string | null;
  currentSectionIndex: number;
  totalSections: number;
  progress: number;
  sections: GeneratedSection[];
  additionalPrompts: string[];
  error: string | null;
}