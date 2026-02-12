import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { api } from '../lib/api';
import { SearchIcon, SpinnerIcon, ChevronRightIcon, XIcon } from '../components/icons';

interface SearchResult {
  person_id: string;
  display_name: string;
  relevance_score: number;
  reasoning: string;
  matching_facts: string[];
}

interface SearchResponse {
  query: string;
  results: SearchResult[];
  reasoning_summary: string;
}

/**
 * Get relevance badge styling based on score
 * - High (>= 0.7): Mint green
 * - Medium (>= 0.4): Yellow
 * - Low (< 0.4): Coral
 */
const getRelevanceBadgeClass = (score: number): string => {
  if (score >= 0.7) return 'badge-neo-success';
  if (score >= 0.4) return 'badge-neo-warning';
  return 'badge-neo-danger';
};

/**
 * Map predicate keywords in facts to badge colors
 */
const getFactBadgeClass = (fact: string): string => {
  const lowerFact = fact.toLowerCase();
  if (lowerFact.includes('works') || lowerFact.includes('company') || lowerFact.includes('role')) {
    return 'badge-neo-primary';
  }
  if (lowerFact.includes('help') || lowerFact.includes('expert') || lowerFact.includes('strong')) {
    return 'badge-neo-success';
  }
  if (lowerFact.includes('located') || lowerFact.includes('city') || lowerFact.includes('country')) {
    return 'badge-neo-lavender';
  }
  if (lowerFact.includes('knows') || lowerFact.includes('connection') || lowerFact.includes('intro')) {
    return 'badge-neo-peach';
  }
  return 'badge-neo';
};

export const SearchPage = () => {
  const { isAuthenticated } = useAuth();
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!query.trim()) return;

    setSearching(true);
    setError(null);
    setResults(null);

    try {
      const response = await api.search(query);
      setResults(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setSearching(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const exampleQueries = [
    'Who can help with AI?',
    'Who works in the Valley?',
    'Who do I know in entrepreneurship?'
  ];

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen p-4 flex items-center justify-center" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div className="card-neo p-6 text-center">
          <p className="font-heading font-bold text-lg" style={{ color: 'var(--text-primary)' }}>
            Please authenticate first
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen p-4" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Header */}
      <header className="mb-6">
        <h1 className="font-heading font-bold text-2xl mb-1" style={{ color: 'var(--text-primary)' }}>
          Search
        </h1>
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          Find the right person in your network
        </p>
      </header>

      {/* Search Input */}
      <div className="flex gap-2 mb-6">
        <input
          type="text"
          placeholder="Who can help with...?"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyPress={handleKeyPress}
          className="input-neo flex-1"
          style={{ minWidth: 0 }}
        />
        <button
          onClick={handleSearch}
          disabled={searching || !query.trim()}
          className="btn-neo btn-neo-primary"
          style={{ flexShrink: 0, padding: '0.75rem 1rem' }}
        >
          {searching ? <SpinnerIcon size={20} /> : <SearchIcon size={20} />}
        </button>
      </div>

      {/* Example Queries - Show when no results and not searching */}
      {!results && !searching && !error && (
        <div className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: 'var(--text-muted)' }}>
            Example queries
          </p>
          <div className="flex flex-wrap gap-2">
            {exampleQueries.map((eq, i) => (
              <button
                key={i}
                className="badge-neo hover:translate-x-[-1px] hover:translate-y-[-1px] hover:shadow-[3px_3px_0_var(--shadow-color)] transition-all cursor-pointer"
                onClick={() => setQuery(eq)}
              >
                {eq}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div
          className="card-neo flex items-center justify-between gap-3 mb-6"
          style={{ backgroundColor: 'var(--accent-danger)', borderColor: 'var(--border-color)' }}
        >
          <span className="font-medium text-white">{error}</span>
          <button
            onClick={() => setError(null)}
            className="text-white hover:opacity-70 transition-opacity"
          >
            <XIcon size={20} />
          </button>
        </div>
      )}

      {/* Searching State */}
      {searching && (
        <div className="card-neo flex flex-col items-center justify-center py-12">
          <SpinnerIcon size={32} className="mb-3" style={{ color: 'var(--accent-primary)' }} />
          <p className="font-medium" style={{ color: 'var(--text-secondary)' }}>
            Searching your network...
          </p>
        </div>
      )}

      {/* Search Results */}
      {results && (
        <div>
          {/* Reasoning Summary */}
          {results.reasoning_summary && (
            <div
              className="card-neo mb-6"
              style={{
                borderLeftWidth: '6px',
                borderLeftColor: 'var(--accent-primary)',
                backgroundColor: 'var(--bg-card)'
              }}
            >
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                {results.reasoning_summary}
              </p>
            </div>
          )}

          {/* No Results */}
          {results.results.length === 0 ? (
            <div className="card-neo text-center py-12">
              <SearchIcon size={48} className="mx-auto mb-4" style={{ color: 'var(--text-muted)' }} />
              <p className="font-heading font-bold text-lg mb-2" style={{ color: 'var(--text-primary)' }}>
                No one found for this query
              </p>
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                Try rephrasing your question or add more notes about people in your network.
              </p>
            </div>
          ) : (
            /* Results List */
            <ul className="space-y-4">
              {results.results.map((result) => (
                <li
                  key={result.person_id}
                  className="card-neo-interactive"
                  style={{
                    borderLeftWidth: '5px',
                    borderLeftColor: result.relevance_score >= 0.7
                      ? 'var(--accent-success)'
                      : result.relevance_score >= 0.4
                        ? 'var(--accent-warning)'
                        : 'var(--accent-danger)'
                  }}
                >
                  {/* Result Header */}
                  <div className="flex items-center gap-3 mb-3">
                    {/* Avatar */}
                    <div
                      className="w-12 h-12 flex items-center justify-center border-3 border-black font-heading font-bold text-lg"
                      style={{
                        backgroundColor: 'var(--accent-primary)',
                        color: '#FFFFFF',
                        borderWidth: '3px',
                        borderColor: 'var(--border-color)'
                      }}
                    >
                      {result.display_name.charAt(0).toUpperCase()}
                    </div>

                    {/* Name and Relevance */}
                    <div className="flex-1 min-w-0">
                      <h3 className="font-heading font-bold text-lg truncate" style={{ color: 'var(--text-primary)' }}>
                        {result.display_name}
                      </h3>
                      <span className={`${getRelevanceBadgeClass(result.relevance_score)}`}>
                        {Math.round(result.relevance_score * 100)}% match
                      </span>
                    </div>

                    {/* Navigation Arrow */}
                    <ChevronRightIcon size={24} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                  </div>

                  {/* Reasoning */}
                  <div className="mb-3">
                    <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                      {result.reasoning}
                    </p>
                  </div>

                  {/* Matching Facts */}
                  {result.matching_facts.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {result.matching_facts.map((fact, i) => (
                        <span
                          key={i}
                          className={`${getFactBadgeClass(fact)}`}
                          style={{ fontSize: '0.7rem' }}
                        >
                          {fact}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};
