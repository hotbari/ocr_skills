import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Filter, X } from 'lucide-react'
import clsx from 'clsx'
import SearchBar from '../components/SearchBar'
import ResultList from '../components/ResultList'
import { documentsApi, searchApi } from '../api/client'
import type { SemanticSearchRequest, SearchResult } from '../api/types'

export default function SearchPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [searchStats, setSearchStats] = useState<{
    embedding_time: number
    search_time: number
    total_time: number
  } | null>(null)
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([])
  const [showFilters, setShowFilters] = useState(false)
  const [topK, setTopK] = useState(10)
  const [minScore, setMinScore] = useState(0.5)

  const { data: documentsData } = useQuery({
    queryKey: ['documents-for-filter'],
    queryFn: () => documentsApi.list(1, 100, 'completed'),
  })

  const searchMutation = useMutation({
    mutationFn: (request: SemanticSearchRequest) => searchApi.semantic(request),
    onSuccess: (data) => {
      setResults(data.results)
      setSearchStats({
        embedding_time: data.query_embedding_time_ms,
        search_time: data.search_time_ms,
        total_time: data.total_time_ms,
      })
    },
  })

  const handleSearch = (query: string) => {
    setSearchQuery(query)
    searchMutation.mutate({
      query,
      document_ids: selectedDocuments.length > 0 ? selectedDocuments : undefined,
      top_k: topK,
      min_score: minScore,
      include_entities: true,
      include_generation_chunks: true,
    })
  }

  const toggleDocument = (docId: string) => {
    setSelectedDocuments((prev) =>
      prev.includes(docId)
        ? prev.filter((id) => id !== docId)
        : [...prev, docId]
    )
  }

  const clearFilters = () => {
    setSelectedDocuments([])
    setTopK(10)
    setMinScore(0.5)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--cp-text-main)] mb-2">Search</h1>
        <p className="text-[var(--cp-text-muted)]">
          Semantic search across processed documents
        </p>
      </div>

      <div className="space-y-4">
        <SearchBar
          onSearch={handleSearch}
          isSearching={searchMutation.isPending}
          placeholder="Enter your search query..."
        />

        <div className="flex items-center justify-between">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={clsx(
              'flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-all duration-300',
              showFilters
                ? 'bg-[var(--cp-neon-purple)]/20 text-[var(--cp-neon-purple)] border border-[var(--cp-neon-purple)]'
                : 'bg-[var(--cp-bg-card)] text-[var(--cp-text-muted)] border border-[var(--cp-text-muted)]/30 hover:border-[var(--cp-neon-purple)] hover:text-[var(--cp-neon-purple)]'
            )}
            style={showFilters ? {
              boxShadow: '0 0 10px var(--cp-neon-purple), 0 0 20px var(--cp-neon-purple)'
            } : {}}
          >
            <Filter className="h-4 w-4" />
            Filters
            {(selectedDocuments.length > 0 || topK !== 10 || minScore !== 0.5) && (
              <span className="ml-1 px-1.5 py-0.5 bg-[var(--cp-neon-green)] text-[var(--cp-bg-dark)] text-xs rounded-full font-bold">
                {selectedDocuments.length + (topK !== 10 ? 1 : 0) + (minScore !== 0.5 ? 1 : 0)}
              </span>
            )}
          </button>

          {searchStats && (
            <p className="text-sm text-[var(--cp-text-muted)] font-mono">
              Embed: <span className="text-[var(--cp-neon-green)]">{searchStats.embedding_time.toFixed(0)}ms</span> &bull; Search:{' '}
              <span className="text-[var(--cp-neon-blue)]">{searchStats.search_time.toFixed(0)}ms</span> &bull; Total:{' '}
              <span className="text-[var(--cp-neon-purple)]">{searchStats.total_time.toFixed(0)}ms</span>
            </p>
          )}
        </div>

        {showFilters && (
          <div className="bg-[var(--cp-bg-card)] rounded-lg p-4 space-y-4 border border-[var(--cp-neon-purple)]/30" style={{
            boxShadow: '0 0 20px var(--cp-neon-purple)/20'
          }}>
            <div className="flex items-center justify-between">
              <h3 className="font-medium text-[var(--cp-text-main)]">Search Filters</h3>
              <button
                onClick={clearFilters}
                className="text-sm text-[var(--cp-text-muted)] hover:text-[var(--cp-neon-blue)] transition-colors duration-300"
              >
                Clear all
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-[var(--cp-text-main)] mb-2">
                  Top K Results
                </label>
                <input
                  type="range"
                  min={1}
                  max={50}
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                  className="w-full accent-[var(--cp-neon-green)]"
                />
                <p className="text-sm text-[var(--cp-neon-green)] mt-1 font-mono">{topK} results</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-[var(--cp-text-main)] mb-2">
                  Minimum Score
                </label>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={minScore * 100}
                  onChange={(e) => setMinScore(Number(e.target.value) / 100)}
                  className="w-full accent-[var(--cp-neon-blue)]"
                />
                <p className="text-sm text-[var(--cp-neon-blue)] mt-1 font-mono">
                  {(minScore * 100).toFixed(0)}%
                </p>
              </div>
            </div>

            {documentsData && documentsData.documents.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-[var(--cp-text-main)] mb-2">
                  Filter by Documents
                </label>
                <div className="flex flex-wrap gap-2">
                  {documentsData.documents.map((doc) => (
                    <button
                      key={doc.id}
                      onClick={() => toggleDocument(doc.id)}
                      className={clsx(
                        'flex items-center gap-1 px-2 py-1 rounded-full text-sm transition-all duration-300',
                        selectedDocuments.includes(doc.id)
                          ? 'bg-[var(--cp-neon-green)]/20 text-[var(--cp-neon-green)] border border-[var(--cp-neon-green)]'
                          : 'bg-[var(--cp-bg-dark)] border border-[var(--cp-text-muted)]/30 text-[var(--cp-text-muted)] hover:border-[var(--cp-neon-green)] hover:text-[var(--cp-neon-green)]'
                      )}
                      style={selectedDocuments.includes(doc.id) ? {
                        boxShadow: '0 0 8px var(--cp-neon-green)'
                      } : {}}
                    >
                      {doc.filename}
                      {selectedDocuments.includes(doc.id) && (
                        <X className="h-3 w-3" />
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {searchQuery && (
        <ResultList results={results} query={searchQuery} />
      )}

      {!searchQuery && (
        <div className="text-center py-12">
          <p className="text-[var(--cp-text-muted)]">
            Enter a query to search across your processed documents
          </p>
        </div>
      )}
    </div>
  )
}
