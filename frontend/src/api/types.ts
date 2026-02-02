export interface Document {
  id: string
  filename: string
  original_filename: string
  file_path: string
  status: DocumentStatus
  raw_text: string | null
  raw_text_by_page: string[]
  metadata: DocumentMetadata
  error_message: string | null
  created_at: string
  updated_at: string
}

export type DocumentStatus =
  | 'uploaded'
  | 'processing'
  | 'completed'
  | 'failed'

export interface DocumentMetadata {
  page_count: number
  file_size_bytes: number
  language: string | null
  title: string | null
  author: string | null
}

export interface DocumentUploadResponse {
  document_id: string
  filename: string
  status: DocumentStatus
  message: string
  page_count: number
  file_size_bytes: number
}

export interface DocumentListResponse {
  documents: Document[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface PipelineStatus {
  document_id: string
  overall_status: string
  current_stage: string | null
  last_completed_stage: string | null
  stages: StageStatus[]
  progress_percent: number
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  total_duration_seconds: number | null
}

export interface StageStatus {
  stage: string
  status: string
  duration_seconds: number | null
  error: string | null
  summary: Record<string, unknown> | null
}

export interface SemanticSearchRequest {
  query: string
  document_ids?: string[]
  top_k?: number
  min_score?: number
  include_entities?: boolean
  include_generation_chunks?: boolean
}

export interface SearchResult {
  score: number
  context_path: string
  retrieval_chunk: {
    id: string
    content: string
    key_concepts: string[]
    page_numbers: number[]
    document_id: string
  }
  generation_chunk?: {
    id: string
    content: string
    summary: string
    key_concepts: string[]
    context_path: string
  }
  toc_node?: {
    id: string
    title: string
    level: number
  }
  entities?: EntitySummary[]
}

export interface EntitySummary {
  id: string
  type: string
  page_number: number
  caption: string | null
  markdown: string | null
}

export interface SemanticSearchResponse {
  query: string
  query_embedding_time_ms: number
  search_time_ms: number
  total_time_ms: number
  results: SearchResult[]
  total_found: number
}

export interface TOCNode {
  id: string
  document_id: string
  title: string
  level: number
  parent_id: string | null
  page_start: number | null
  page_end: number | null
  order_index: number
}

export interface TOCResponse {
  document_id: string
  root_nodes: string[]
  nodes: TOCNode[]
  summary: {
    total: number
    l1: number
    l2: number
    l3: number
  }
}
