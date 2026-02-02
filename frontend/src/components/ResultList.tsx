import { ChevronDown, ChevronUp, FileText, Table, Image } from 'lucide-react'
import { useState } from 'react'
import clsx from 'clsx'
import type { SearchResult } from '../api/types'

interface ResultListProps {
  results: SearchResult[]
  query: string
}

function ResultCard({ result, index }: { result: SearchResult; index: number }) {
  const [expanded, setExpanded] = useState(false)

  const scorePercent = Math.round(result.score * 100)
  const scoreColor =
    scorePercent >= 80
      ? 'text-green-600'
      : scorePercent >= 60
        ? 'text-yellow-600'
        : 'text-red-600'

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div
        className="p-4 cursor-pointer hover:bg-gray-50"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-medium text-gray-500">#{index + 1}</span>
              {result.toc_node && (
                <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
                  L{result.toc_node.level}: {result.toc_node.title}
                </span>
              )}
              <span className={clsx('text-sm font-bold', scoreColor)}>
                {scorePercent}%
              </span>
            </div>
            {result.context_path && (
              <p className="text-xs text-gray-500 mb-2">{result.context_path}</p>
            )}
            <p className="text-sm text-gray-900 line-clamp-3">
              {result.retrieval_chunk.content}
            </p>
            {result.retrieval_chunk.key_concepts.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {result.retrieval_chunk.key_concepts.slice(0, 5).map((concept, i) => (
                  <span
                    key={i}
                    className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded"
                  >
                    {concept}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {result.retrieval_chunk.page_numbers.length > 0 && (
              <span className="text-xs text-gray-500">
                p. {result.retrieval_chunk.page_numbers.join(', ')}
              </span>
            )}
            {expanded ? (
              <ChevronUp className="h-5 w-5 text-gray-400" />
            ) : (
              <ChevronDown className="h-5 w-5 text-gray-400" />
            )}
          </div>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-200 p-4 bg-gray-50">
          {result.generation_chunk && (
            <div className="mb-4">
              <h4 className="text-sm font-semibold text-gray-700 mb-2">
                Generation Context
              </h4>
              <p className="text-sm text-gray-800 whitespace-pre-wrap">
                {result.generation_chunk.content}
              </p>
              {result.generation_chunk.summary && (
                <p className="text-xs text-gray-600 mt-2 italic">
                  Summary: {result.generation_chunk.summary}
                </p>
              )}
            </div>
          )}

          {result.entities && result.entities.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">
                Related Entities
              </h4>
              <div className="space-y-2">
                {result.entities.map((entity) => (
                  <div
                    key={entity.id}
                    className="flex items-start gap-2 p-2 bg-white rounded border border-gray-200"
                  >
                    {entity.type === 'table' && (
                      <Table className="h-4 w-4 text-purple-500 mt-0.5" />
                    )}
                    {entity.type === 'figure' && (
                      <Image className="h-4 w-4 text-green-500 mt-0.5" />
                    )}
                    {entity.type === 'chart' && (
                      <FileText className="h-4 w-4 text-orange-500 mt-0.5" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-gray-700">
                        {entity.type.charAt(0).toUpperCase() + entity.type.slice(1)} (p. {entity.page_number})
                      </p>
                      {entity.caption && (
                        <p className="text-xs text-gray-600 truncate">
                          {entity.caption}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ResultList({ results, query }: ResultListProps) {
  if (results.length === 0) {
    return (
      <div className="text-center py-12">
        <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
        <p className="text-gray-500">No results found for "{query}"</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">
        Found {results.length} result{results.length !== 1 ? 's' : ''}
      </p>
      {results.map((result, index) => (
        <ResultCard key={result.retrieval_chunk.id} result={result} index={index} />
      ))}
    </div>
  )
}
