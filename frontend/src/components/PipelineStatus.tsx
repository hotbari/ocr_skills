import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle, XCircle, Clock, Loader2, PlayCircle } from 'lucide-react'
import clsx from 'clsx'
import { pipelineApi } from '../api/client'
import type { StageStatus } from '../api/types'

interface PipelineStatusProps {
  documentId: string
  onComplete?: () => void
}

const STAGE_LABELS: Record<string, string> = {
  extraction: 'PDF Extraction',
  segmentation: 'Segmentation',
  headings: 'Heading Generation',
  toc_alignment: 'TOC Alignment',
  toc_normalization: 'TOC Normalization',
  chunking: 'Dual Chunking',
  entities: 'Entity Extraction',
  vision: 'Vision Processing',
  embedding: 'Embedding Generation',
}

function StageIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return <CheckCircle className="h-5 w-5 text-green-500" />
    case 'failed':
      return <XCircle className="h-5 w-5 text-red-500" />
    case 'running':
      return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
    case 'skipped':
      return <Clock className="h-5 w-5 text-gray-400" />
    default:
      return <Clock className="h-5 w-5 text-gray-300" />
  }
}

function StageItem({ stage }: { stage: StageStatus }) {
  return (
    <div
      className={clsx(
        'flex items-center gap-3 p-3 rounded-lg',
        stage.status === 'running' && 'bg-blue-50',
        stage.status === 'failed' && 'bg-red-50'
      )}
    >
      <StageIcon status={stage.status} />
      <div className="flex-1">
        <p className="font-medium text-sm text-gray-900">
          {STAGE_LABELS[stage.stage] || stage.stage}
        </p>
        {stage.error && (
          <p className="text-xs text-red-600 mt-1">{stage.error}</p>
        )}
        {stage.duration_seconds && (
          <p className="text-xs text-gray-500 mt-1">
            {stage.duration_seconds.toFixed(1)}s
          </p>
        )}
      </div>
    </div>
  )
}

export default function PipelineStatus({ documentId, onComplete }: PipelineStatusProps) {
  const { data: status, isLoading } = useQuery({
    queryKey: ['pipeline-status', documentId],
    queryFn: () => pipelineApi.getStatus(documentId),
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.overall_status === 'processing') return 2000
      return false
    },
  })

  useEffect(() => {
    if (status?.overall_status === 'completed' && onComplete) {
      onComplete()
    }
  }, [status?.overall_status, onComplete])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  if (!status) {
    return (
      <div className="text-center p-8 text-gray-500">
        Pipeline not started
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">Pipeline Status</h3>
        <span
          className={clsx(
            'px-2 py-1 text-xs font-medium rounded-full',
            status.overall_status === 'completed' && 'bg-green-100 text-green-700',
            status.overall_status === 'processing' && 'bg-blue-100 text-blue-700',
            status.overall_status === 'failed' && 'bg-red-100 text-red-700',
            status.overall_status === 'uploaded' && 'bg-gray-100 text-gray-700'
          )}
        >
          {status.overall_status}
        </span>
      </div>

      <div className="mb-4">
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="text-gray-600">Progress</span>
          <span className="font-medium">{status.progress_percent}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className={clsx(
              'h-2 rounded-full transition-all',
              status.overall_status === 'failed' ? 'bg-red-500' : 'bg-blue-500'
            )}
            style={{ width: `${status.progress_percent}%` }}
          />
        </div>
      </div>

      <div className="space-y-2">
        {status.stages.map((stage) => (
          <StageItem key={stage.stage} stage={stage} />
        ))}
      </div>

      {status.error_message && (
        <div className="mt-4 p-3 bg-red-50 rounded-lg">
          <p className="text-sm text-red-700">{status.error_message}</p>
        </div>
      )}

      {status.total_duration_seconds && (
        <p className="mt-4 text-sm text-gray-500 text-center">
          Total time: {status.total_duration_seconds.toFixed(1)}s
        </p>
      )}
    </div>
  )
}
