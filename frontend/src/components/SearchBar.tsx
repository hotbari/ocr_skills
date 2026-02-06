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
            <Loader2 className="h-5 w-5 text-[var(--cp-neon-green)] animate-spin" style={{
              filter: 'drop-shadow(0 0 4px var(--cp-neon-green))'
            }} />
          ) : (
            <Search className="h-5 w-5 text-[var(--cp-text-muted)]" />
          )}
        </div>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          disabled={isSearching}
          className={clsx(
            'block w-full pl-10 pr-24 py-3 border rounded-lg transition-all duration-300',
            'bg-[var(--cp-bg-card)] border-[var(--cp-text-muted)]/30',
            'focus:outline-none focus:border-[var(--cp-neon-blue)]',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'placeholder-[var(--cp-text-muted)] text-[var(--cp-text-main)]'
          )}
          style={{
            boxShadow: query.trim() ? '0 0 15px var(--cp-neon-blue)/30' : 'none'
          }}
        />
        <div className="absolute inset-y-0 right-0 flex items-center pr-2">
          <button
            type="submit"
            disabled={!query.trim() || isSearching}
            className={clsx(
              'px-4 py-1.5 rounded-md text-sm font-medium transition-all duration-300',
              query.trim() && !isSearching
                ? 'bg-[var(--cp-neon-green)]/20 text-[var(--cp-neon-green)] border border-[var(--cp-neon-green)] hover:bg-[var(--cp-neon-green)]/30'
                : 'bg-[var(--cp-bg-dark)] text-[var(--cp-text-muted)]/50 border border-[var(--cp-text-muted)]/20 cursor-not-allowed'
            )}
            style={query.trim() && !isSearching ? {
              boxShadow: '0 0 10px var(--cp-neon-green), 0 0 20px var(--cp-neon-green)'
            } : {}}
          >
            Search
          </button>
        </div>
      </div>
    </form>
  )
}
