import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  FileText,
  Trash2,
  Play,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  AlertCircle,
} from 'lucide-react'
import clsx from 'clsx'
import FileUpload from '../components/FileUpload'
import { documentsApi, pipelineApi } from '../api/client'
import type { Document, DocumentStatus } from '../api/types'

function StatusBadge({ status }: { status: DocumentStatus }) {
  const config = {
    uploaded: { icon: Clock, color: 'bg-white/5 text-cp-text-muted border border-white/10', spin: false },
    processing: { icon: Loader2, color: 'bg-cp-neon-blue/10 text-cp-neon-blue border border-cp-neon-blue/30', spin: true },
    completed: { icon: CheckCircle, color: 'bg-cp-neon-green/10 text-cp-neon-green border border-cp-neon-green/30', spin: false },
    failed: { icon: XCircle, color: 'bg-red-500/10 text-red-500 border border-red-500/30', spin: false },
  }

  const { icon: Icon, color, spin } = config[status] || config.uploaded

  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium', color)}>
      <Icon className={clsx('h-3 w-3', spin && 'animate-spin')} />
      {status}
    </span>
  )
}

function DocumentCard({
  document,
  onDelete,
  onRunPipeline,
}: {
  document: Document
  onDelete: (id: string) => void
  onRunPipeline: (id: string) => void
}) {
  return (
    <div className="bg-cp-card rounded-lg border border-cp-neon-purple/20 p-4 hover:shadow-[0_0_15px_rgba(176,38,255,0.2)] hover:border-cp-neon-purple/50 transition-all duration-300 group">
      <div className="flex items-start justify-between gap-4">
        <Link
          to={`/documents/${document.id}`}
          className="flex-1 min-w-0 hover:opacity-80"
        >
          <div className="flex items-center gap-3">
            <FileText className="h-10 w-10 text-cp-neon-blue group-hover:drop-shadow-[0_0_8px_rgba(0,243,255,0.5)] transition-all flex-shrink-0" />
            <div className="min-w-0">
              <h3 className="font-medium text-cp-text truncate group-hover:text-cp-neon-green transition-colors">
                {document.filename}
              </h3>
              <p className="text-sm text-cp-text-muted">
                {document.metadata.page_count} pages &bull;{' '}
                {(document.metadata.file_size_bytes / 1024 / 1024).toFixed(2)} MB
              </p>
            </div>
          </div>
        </Link>
        <StatusBadge status={document.status} />
      </div>

      <div className="mt-4 flex items-center justify-between">
        <p className="text-xs text-cp-text-muted/60">
          {new Date(document.created_at).toLocaleDateString()}
        </p>
        <div className="flex items-center gap-2">
          {document.status === 'uploaded' && (
            <button
              onClick={() => onRunPipeline(document.id)}
              className="p-2 text-cp-neon-blue hover:bg-cp-neon-blue/10 rounded-md transition-colors"
              title="Run Pipeline"
            >
              <Play className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={() => onDelete(document.id)}
            className="p-2 text-red-600 hover:bg-red-50 rounded-md"
            title="Delete"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

export default function HomePage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSuccess, setUploadSuccess] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['documents', page],
    queryFn: () => documentsApi.list(page, 12),
  })

  const uploadMutation = useMutation({
    mutationFn: documentsApi.upload,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: documentsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })

  const pipelineMutation = useMutation({
    mutationFn: (documentId: string) => pipelineApi.run(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })

  const handleUpload = async (file: File) => {
    try {
      setUploadError(null)
      setUploadSuccess(false)
      await uploadMutation.mutateAsync(file)
      setUploadSuccess(true)
      // Clear success message after 3 seconds
      setTimeout(() => setUploadSuccess(false), 3000)
    } catch (error: any) {
      console.error('Upload failed:', error)
      const message = error.response?.data?.detail || error.message || 'Failed to upload file'
      setUploadError(message)
    }
  }

  const handleDelete = (documentId: string) => {
    if (confirm('Are you sure you want to delete this document?')) {
      deleteMutation.mutate(documentId)
    }
  }

  const handleRunPipeline = (documentId: string) => {
    pipelineMutation.mutate(documentId)
  }

  return (
    <div className="space-y-8 animate-fade-in-up">
      <div>
        <h1 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cp-neon-green via-cp-neon-blue to-cp-neon-purple mb-2">Documents</h1>
        <p className="text-cp-text-muted">Upload and process PDF documents</p>
      </div>

      {uploadError && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-500 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="h-5 w-5" />
          <p>{uploadError}</p>
        </div>
      )}

      {uploadSuccess && (
        <div className="bg-cp-neon-green/10 border border-cp-neon-green/20 text-cp-neon-green px-4 py-3 rounded-lg flex items-center gap-2">
          <CheckCircle className="h-5 w-5" />
          <p>Document uploaded successfully</p>
        </div>
      )}

      <FileUpload onUpload={handleUpload} isUploading={uploadMutation.isPending} />

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 text-cp-neon-green animate-spin" />
        </div>
      ) : data?.documents.length === 0 ? (
        <div className="text-center py-12">
          <FileText className="h-12 w-12 text-cp-text-muted/30 mx-auto mb-4" />
          <p className="text-cp-text-muted">No documents yet. Upload a PDF to get started.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data?.documents.map((doc) => (
              <DocumentCard
                key={doc.id}
                document={doc}
                onDelete={handleDelete}
                onRunPipeline={handleRunPipeline}
              />
            ))}
          </div>

          {data && data.total_pages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 border border-cp-neon-purple/30 rounded-md disabled:opacity-50 text-cp-text hover:bg-cp-neon-purple/20 transition-colors"
              >
                Previous
              </button>
              <span className="text-sm text-cp-text-muted">
                Page {page} of {data.total_pages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))}
                disabled={page === data.total_pages}
                className="px-3 py-1 border border-cp-neon-purple/30 rounded-md disabled:opacity-50 text-cp-text hover:bg-cp-neon-purple/20 transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
