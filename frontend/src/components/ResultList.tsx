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
      ? 'text-[var(--cp-neon-green)]'
      : scorePercent >= 60
        ? 'text-[var(--cp-neon-blue)]'
        : 'text-[var(--cp-neon-purple)]'

  const scoreGlow =
    scorePercent >= 80
      ? '0 0 8px var(--cp-neon-green)'
      : scorePercent >= 60
        ? '0 0 8px var(--cp-neon-blue)'
        : '0 0 8px var(--cp-neon-purple)'

  return (
    <div className="bg-[var(--cp-bg-card)] rounded-lg border border-[var(--cp-text-muted)]/30 overflow-hidden transition-all duration-300 hover:border-[var(--cp-neon-blue)]" style={{
      boxShadow: expanded ? '0 0 20px var(--cp-neon-blue)/30' : 'none'
    }}>
      <div
        className="p-4 cursor-pointer hover:bg-[var(--cp-bg-dark)]/50 transition-colors duration-300"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-medium text-[var(--cp-text-muted)] font-mono">#{index + 1}</span>
              {result.toc_node && (
                <span className="px-2 py-0.5 bg-[var(--cp-neon-purple)]/20 text-[var(--cp-neon-purple)] text-xs rounded-full border border-[var(--cp-neon-purple)]">
                  L{result.toc_node.level}: {result.toc_node.title}
                </span>
              )}
              <span className={clsx('text-sm font-bold font-mono', scoreColor)} style={{
                textShadow: scoreGlow
              }}>
                {scorePercent}%
              </span>
            </div>
            {result.context_path && (
              <p className="text-xs text-[var(--cp-text-muted)] mb-2 font-mono">{result.context_path}</p>
            )}
            <p className="text-sm text-[var(--cp-text-main)] line-clamp-3">
              {result.retrieval_chunk.content}
            </p>
            {result.retrieval_chunk.key_concepts.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {result.retrieval_chunk.key_concepts.slice(0, 5).map((concept, i) => (
                  <span
                    key={i}
                    className="px-2 py-0.5 bg-[var(--cp-bg-dark)] text-[var(--cp-neon-green)] text-xs rounded border border-[var(--cp-neon-green)]/30"
                  >
                    {concept}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {result.retrieval_chunk.page_numbers.length > 0 && (
              <span className="text-xs text-[var(--cp-text-muted)] font-mono">
                p. {result.retrieval_chunk.page_numbers.join(', ')}
              </span>
            )}
            {expanded ? (
              <ChevronUp className="h-5 w-5 text-[var(--cp-neon-blue)]" style={{
                filter: 'drop-shadow(0 0 4px var(--cp-neon-blue))'
              }} />
            ) : (
              <ChevronDown className="h-5 w-5 text-[var(--cp-text-muted)]" />
            )}
          </div>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-[var(--cp-text-muted)]/30 p-4 bg-[var(--cp-bg-dark)]/30">
          {result.generation_chunk && (
            <div className="mb-4">
              <h4 className="text-sm font-semibold text-[var(--cp-neon-blue)] mb-2" style={{
                textShadow: '0 0 8px var(--cp-neon-blue)'
              }}>
                Generation Context
              </h4>
              <p className="text-sm text-[var(--cp-text-main)] whitespace-pre-wrap">
                {result.generation_chunk.content}
              </p>
              {result.generation_chunk.summary && (
                <p className="text-xs text-[var(--cp-text-muted)] mt-2 italic">
                  Summary: {result.generation_chunk.summary}
                </p>
              )}
            </div>
          )}

          {result.entities && result.entities.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-[var(--cp-neon-purple)] mb-2" style={{
                textShadow: '0 0 8px var(--cp-neon-purple)'
              }}>
                Related Entities
              </h4>
              <div className="space-y-2">
                {result.entities.map((entity) => (
                  <div
                    key={entity.id}
                    className="flex items-start gap-2 p-2 bg-[var(--cp-bg-card)] rounded border border-[var(--cp-neon-purple)]/30"
                  >
                    {entity.type === 'table' && (
                      <Table className="h-4 w-4 text-[var(--cp-neon-purple)] mt-0.5" style={{
                        filter: 'drop-shadow(0 0 4px var(--cp-neon-purple))'
                      }} />
                    )}
                    {entity.type === 'figure' && (
                      <Image className="h-4 w-4 text-[var(--cp-neon-green)] mt-0.5" style={{
                        filter: 'drop-shadow(0 0 4px var(--cp-neon-green))'
                      }} />
                    )}
                    {entity.type === 'chart' && (
                      <FileText className="h-4 w-4 text-[var(--cp-neon-blue)] mt-0.5" style={{
                        filter: 'drop-shadow(0 0 4px var(--cp-neon-blue))'
                      }} />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-[var(--cp-text-main)]">
                        {entity.type.charAt(0).toUpperCase() + entity.type.slice(1)} (p. {entity.page_number})
                      </p>
                      {entity.caption && (
                        <p className="text-xs text-[var(--cp-text-muted)] truncate">
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
        <FileText className="h-12 w-12 text-[var(--cp-text-muted)]/30 mx-auto mb-4" />
        <p className="text-[var(--cp-text-muted)]">No results found for "<span className="text-[var(--cp-neon-purple)]">{query}</span>"</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--cp-text-muted)] font-mono">
        Found <span className="text-[var(--cp-neon-green)] font-bold">{results.length}</span> result{results.length !== 1 ? 's' : ''}
      </p>
      {results.map((result, index) => (
        <ResultCard key={result.retrieval_chunk.id} result={result} index={index} />
      ))}
    </div>
  )
}
