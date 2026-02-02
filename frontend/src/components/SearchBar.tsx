import { useState } from 'react'
import { Search, Loader2 } from 'lucide-react'
import clsx from 'clsx'

interface SearchBarProps {
  onSearch: (query: string) => void
  isSearching: boolean
  placeholder?: string
}

export default function SearchBar({
  onSearch,
  isSearching,
  placeholder = 'Search documents...',
}: SearchBarProps) {
  const [query, setQuery] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim()) {
      onSearch(query.trim())
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="relative">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          {isSearching ? (
            <Loader2 className="h-5 w-5 text-gray-400 animate-spin" />
          ) : (
            <Search className="h-5 w-5 text-gray-400" />
          )}
        </div>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          disabled={isSearching}
          className={clsx(
            'block w-full pl-10 pr-24 py-3 border border-gray-300 rounded-lg',
            'focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            'disabled:bg-gray-100 disabled:cursor-not-allowed',
            'placeholder-gray-400 text-gray-900'
          )}
        />
        <div className="absolute inset-y-0 right-0 flex items-center pr-2">
          <button
            type="submit"
            disabled={!query.trim() || isSearching}
            className={clsx(
              'px-4 py-1.5 rounded-md text-sm font-medium',
              query.trim() && !isSearching
                ? 'bg-blue-600 text-white hover:bg-blue-700'
                : 'bg-gray-100 text-gray-400 cursor-not-allowed'
            )}
          >
            Search
          </button>
        </div>
      </div>
    </form>
  )
}
