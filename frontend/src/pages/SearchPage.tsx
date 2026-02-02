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
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Search</h1>
        <p className="text-gray-600">
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
              'flex items-center gap-2 px-3 py-1.5 rounded-md text-sm',
              showFilters
                ? 'bg-blue-100 text-blue-700'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            )}
          >
            <Filter className="h-4 w-4" />
            Filters
            {(selectedDocuments.length > 0 || topK !== 10 || minScore !== 0.5) && (
              <span className="ml-1 px-1.5 py-0.5 bg-blue-600 text-white text-xs rounded-full">
                {selectedDocuments.length + (topK !== 10 ? 1 : 0) + (minScore !== 0.5 ? 1 : 0)}
              </span>
            )}
          </button>

          {searchStats && (
            <p className="text-sm text-gray-500">
              Embed: {searchStats.embedding_time.toFixed(0)}ms &bull; Search:{' '}
              {searchStats.search_time.toFixed(0)}ms &bull; Total:{' '}
              {searchStats.total_time.toFixed(0)}ms
            </p>
          )}
        </div>

        {showFilters && (
          <div className="bg-gray-50 rounded-lg p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium text-gray-900">Search Filters</h3>
              <button
                onClick={clearFilters}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Clear all
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Top K Results
                </label>
                <input
                  type="range"
                  min={1}
                  max={50}
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                  className="w-full"
                />
                <p className="text-sm text-gray-500 mt-1">{topK} results</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Minimum Score
                </label>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={minScore * 100}
                  onChange={(e) => setMinScore(Number(e.target.value) / 100)}
                  className="w-full"
                />
                <p className="text-sm text-gray-500 mt-1">
                  {(minScore * 100).toFixed(0)}%
                </p>
              </div>
            </div>

            {documentsData && documentsData.documents.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Filter by Documents
                </label>
                <div className="flex flex-wrap gap-2">
                  {documentsData.documents.map((doc) => (
                    <button
                      key={doc.id}
                      onClick={() => toggleDocument(doc.id)}
                      className={clsx(
                        'flex items-center gap-1 px-2 py-1 rounded-full text-sm',
                        selectedDocuments.includes(doc.id)
                          ? 'bg-blue-100 text-blue-700'
                          : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'
                      )}
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
          <p className="text-gray-500">
            Enter a query to search across your processed documents
          </p>
        </div>
      )}
    </div>
  )
}
