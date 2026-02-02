import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Play,
  RefreshCw,
  StopCircle,
  Trash2,
  FileText,
  Loader2,
  ChevronRight,
} from 'lucide-react'
import clsx from 'clsx'
import { documentsApi, pipelineApi } from '../api/client'
import PipelineStatus from '../components/PipelineStatus'
import type { TOCNode } from '../api/types'

function TOCTree({ nodes, rootIds }: { nodes: TOCNode[]; rootIds: string[] }) {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]))
  const childrenMap = new Map<string | null, TOCNode[]>()

  nodes.forEach((node) => {
    const parentId = node.parent_id
    if (!childrenMap.has(parentId)) {
      childrenMap.set(parentId, [])
    }
    childrenMap.get(parentId)!.push(node)
  })

  function renderNode(node: TOCNode, depth: number): JSX.Element {
    const children = childrenMap.get(node.id) || []

    return (
      <div key={node.id} style={{ marginLeft: depth * 16 }}>
        <div className="flex items-center gap-2 py-1 text-sm hover:bg-gray-50 rounded px-2">
          {children.length > 0 && (
            <ChevronRight className="h-3 w-3 text-gray-400" />
          )}
          <span
            className={clsx(
              'font-medium',
              node.level === 1 && 'text-gray-900',
              node.level === 2 && 'text-gray-700',
              node.level === 3 && 'text-gray-500'
            )}
          >
            {node.title}
          </span>
          {node.page_start && (
            <span className="text-xs text-gray-400">p.{node.page_start}</span>
          )}
        </div>
        {children.map((child) => renderNode(child, depth + 1))}
      </div>
    )
  }

  const rootNodes = rootIds
    .map((id) => nodeMap.get(id))
    .filter((n): n is TOCNode => n !== undefined)

  if (rootNodes.length === 0) {
    return <p className="text-sm text-gray-500">No TOC available</p>
  }

  return <div className="space-y-1">{rootNodes.map((node) => renderNode(node, 0))}</div>
}

export default function DocumentPage() {
  const { documentId } = useParams<{ documentId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['document', documentId],
    queryFn: () => documentsApi.get(documentId!),
    enabled: !!documentId,
  })

  const { data: tocData } = useQuery({
    queryKey: ['document-toc', documentId],
    queryFn: () => documentsApi.getToc(documentId!),
    enabled: !!documentId && data?.document?.status === 'completed',
  })

  const runPipelineMutation = useMutation({
    mutationFn: () => pipelineApi.run(documentId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: () => pipelineApi.cancel(documentId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
    },
  })

  const retryMutation = useMutation({
    mutationFn: () => pipelineApi.retry(documentId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => documentsApi.delete(documentId!),
    onSuccess: () => {
      navigate('/')
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500">Failed to load document</p>
        <button
          onClick={() => navigate('/')}
          className="mt-4 text-blue-600 hover:underline"
        >
          Back to Documents
        </button>
      </div>
    )
  }

  const { document: doc, chunk_stats, entity_stats, toc_summary } = data

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/')}
          className="p-2 hover:bg-gray-100 rounded-md"
        >
          <ArrowLeft className="h-5 w-5 text-gray-600" />
        </button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-gray-900">{doc.filename}</h1>
          <p className="text-sm text-gray-500">
            {doc.metadata.page_count} pages &bull;{' '}
            {(doc.metadata.file_size_bytes / 1024 / 1024).toFixed(2)} MB
          </p>
        </div>
        <div className="flex items-center gap-2">
          {doc.status === 'uploaded' && (
            <button
              onClick={() => runPipelineMutation.mutate()}
              disabled={runPipelineMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              <Play className="h-4 w-4" />
              Run Pipeline
            </button>
          )}
          {doc.status === 'processing' && (
            <button
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-yellow-600 text-white rounded-md hover:bg-yellow-700 disabled:opacity-50"
            >
              <StopCircle className="h-4 w-4" />
              Cancel
            </button>
          )}
          {doc.status === 'failed' && (
            <button
              onClick={() => retryMutation.mutate()}
              disabled={retryMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 disabled:opacity-50"
            >
              <RefreshCw className="h-4 w-4" />
              Retry
            </button>
          )}
          <button
            onClick={() => {
              if (confirm('Are you sure you want to delete this document?')) {
                deleteMutation.mutate()
              }
            }}
            disabled={deleteMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 border border-red-300 text-red-600 rounded-md hover:bg-red-50 disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {(doc.status === 'processing' || doc.status === 'uploaded' || doc.status === 'failed') && (
            <PipelineStatus
              documentId={documentId!}
              onComplete={() => {
                queryClient.invalidateQueries({ queryKey: ['document', documentId] })
              }}
            />
          )}

          {doc.status === 'completed' && (
            <>
              <div className="bg-white rounded-lg border border-gray-200 p-4">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Statistics</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="text-center p-3 bg-gray-50 rounded-lg">
                    <p className="text-2xl font-bold text-blue-600">
                      {chunk_stats.retrieval || 0}
                    </p>
                    <p className="text-xs text-gray-500">Retrieval Chunks</p>
                  </div>
                  <div className="text-center p-3 bg-gray-50 rounded-lg">
                    <p className="text-2xl font-bold text-green-600">
                      {chunk_stats.generation || 0}
                    </p>
                    <p className="text-xs text-gray-500">Generation Chunks</p>
                  </div>
                  <div className="text-center p-3 bg-gray-50 rounded-lg">
                    <p className="text-2xl font-bold text-purple-600">
                      {Object.values(entity_stats).reduce((a, b) => a + b, 0)}
                    </p>
                    <p className="text-xs text-gray-500">Entities</p>
                  </div>
                  <div className="text-center p-3 bg-gray-50 rounded-lg">
                    <p className="text-2xl font-bold text-orange-600">
                      {toc_summary.total_nodes || 0}
                    </p>
                    <p className="text-xs text-gray-500">TOC Nodes</p>
                  </div>
                </div>
              </div>

              {tocData && (
                <div className="bg-white rounded-lg border border-gray-200 p-4">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">
                    Table of Contents
                  </h3>
                  <TOCTree nodes={tocData.nodes} rootIds={tocData.root_nodes} />
                </div>
              )}
            </>
          )}
        </div>

        <div className="space-y-6">
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Details</h3>
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-gray-500">Document ID</dt>
                <dd className="font-mono text-xs text-gray-900 break-all">
                  {doc.id}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Status</dt>
                <dd className="font-medium text-gray-900">{doc.status}</dd>
              </div>
              <div>
                <dt className="text-gray-500">Language</dt>
                <dd className="text-gray-900">
                  {doc.metadata.language || 'Unknown'}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Created</dt>
                <dd className="text-gray-900">
                  {new Date(doc.created_at).toLocaleString()}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Updated</dt>
                <dd className="text-gray-900">
                  {new Date(doc.updated_at).toLocaleString()}
                </dd>
              </div>
            </dl>
          </div>

          {doc.error_message && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-red-800 mb-2">Error</h3>
              <p className="text-sm text-red-700">{doc.error_message}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
