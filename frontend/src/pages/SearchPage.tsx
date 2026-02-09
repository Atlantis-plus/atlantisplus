import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { api } from '../lib/api';

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
      <div className="page">
        <div className="error">Please authenticate first</div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="header">
        <h1>Search</h1>
        <p className="subtitle">Find the right person in your network</p>
      </header>

      <main className="main">
        <div className="search-input-container">
          <input
            type="text"
            placeholder="Who can help with...?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            className="search-input"
          />
          <button
            onClick={handleSearch}
            disabled={searching || !query.trim()}
            className="search-btn"
          >
            {searching ? '...' : '🔍'}
          </button>
        </div>

        {!results && !searching && !error && (
          <div className="example-queries">
            <p className="examples-label">Example queries:</p>
            {exampleQueries.map((eq, i) => (
              <button
                key={i}
                className="example-query"
                onClick={() => setQuery(eq)}
              >
                {eq}
              </button>
            ))}
          </div>
        )}

        {error && (
          <div className="error-banner">
            {error}
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        {searching && (
          <div className="searching">
            <div className="spinner"></div>
            <p>Searching your network...</p>
          </div>
        )}

        {results && (
          <div className="search-results">
            {results.reasoning_summary && (
              <div className="reasoning-summary">
                <p>{results.reasoning_summary}</p>
              </div>
            )}

            {results.results.length === 0 ? (
              <div className="no-results">
                <p>No one found for this query.</p>
                <p className="hint">Try rephrasing or add more notes about people.</p>
              </div>
            ) : (
              <ul className="results-list">
                {results.results.map((result) => (
                  <li key={result.person_id} className="result-card">
                    <div className="result-header">
                      <div className="result-avatar">
                        {result.display_name.charAt(0).toUpperCase()}
                      </div>
                      <div className="result-name-container">
                        <span className="result-name">{result.display_name}</span>
                        <span className="relevance-badge">
                          {Math.round(result.relevance_score * 100)}% relevance
                        </span>
                      </div>
                    </div>

                    <div className="result-reasoning">
                      <p>{result.reasoning}</p>
                    </div>

                    {result.matching_facts.length > 0 && (
                      <div className="matching-facts">
                        {result.matching_facts.map((fact, i) => (
                          <span key={i} className="fact-tag">{fact}</span>
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </main>
    </div>
  );
};
