import axios from 'axios'
import type {
  Document,
  DocumentUploadResponse,
  DocumentListResponse,
  PipelineStatus,
  SemanticSearchRequest,
  SemanticSearchResponse,
  TOCResponse,
} from './types'

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

export const documentsApi = {
  upload: async (file: File): Promise<DocumentUploadResponse> => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await api.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },

  get: async (documentId: string): Promise<{ document: Document; chunk_stats: Record<string, number>; entity_stats: Record<string, number>; toc_summary: Record<string, number> }> => {
    const response = await api.get(`/documents/${documentId}`)
    return response.data
  },

  list: async (page = 1, pageSize = 20, status?: string): Promise<DocumentListResponse> => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (status) params.append('status', status)
    const response = await api.get(`/documents?${params}`)
    return response.data
  },

  delete: async (documentId: string): Promise<{ deleted: boolean }> => {
    const response = await api.delete(`/documents/${documentId}`)
    return response.data
  },

  getToc: async (documentId: string): Promise<TOCResponse> => {
    const response = await api.get(`/documents/${documentId}/toc`)
    return response.data
  },
}

export const pipelineApi = {
  run: async (documentId: string, skipVision = false, forceRestart = false) => {
    const response = await api.post('/pipeline/run', {
      document_id: documentId,
      skip_vision: skipVision,
      force_restart: forceRestart,
    })
    return response.data
  },

  getStatus: async (documentId: string): Promise<PipelineStatus> => {
    const response = await api.get(`/pipeline/status/${documentId}`)
    return response.data
  },

  cancel: async (documentId: string) => {
    const response = await api.post(`/pipeline/cancel/${documentId}`)
    return response.data
  },

  retry: async (documentId: string) => {
    const response = await api.post(`/pipeline/retry/${documentId}`)
    return response.data
  },
}

export const searchApi = {
  semantic: async (request: SemanticSearchRequest): Promise<SemanticSearchResponse> => {
    const response = await api.post('/search/semantic', request)
    return response.data
  },

  toc: async (documentId: string, query: string, levelFilter?: number[]) => {
    const response = await api.post('/search/toc', {
      document_id: documentId,
      query,
      level_filter: levelFilter,
    })
    return response.data
  },
}

export const healthApi = {
  check: async () => {
    const response = await axios.get('/health')
    return response.data
  },
}

export default api
