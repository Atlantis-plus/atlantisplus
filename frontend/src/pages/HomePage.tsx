import { useAuth } from '../hooks/useAuth';

type Page = 'home' | 'notes' | 'search' | 'people';

interface HomePageProps {
  onNavigate?: (page: Page) => void;
}

export const HomePage = ({ onNavigate }: HomePageProps) => {
  const { displayName, isAuthenticated, loading, error, telegramId } = useAuth();

  if (loading) {
    return (
      <div className="page">
        <div className="loading">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <div className="error">
          <h2>Error</h2>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="header">
        <h1>Atlantis Plus</h1>
        <p className="subtitle">Personal Network Memory</p>
      </header>

      <main className="main">
        {isAuthenticated ? (
          <div className="welcome">
            <p>Welcome, <strong>{displayName}</strong>!</p>
            <p className="hint">Telegram ID: {telegramId}</p>
          </div>
        ) : (
          <div className="dev-mode">
            <p>Development mode</p>
            <p className="hint">Open in Telegram Mini App for full functionality</p>
          </div>
        )}

        <nav className="actions">
          <button
            className="action-btn"
            onClick={() => onNavigate?.('notes')}
            disabled={!isAuthenticated}
          >
            <span className="icon">🎤</span>
            <span>Voice Note</span>
          </button>
          <button
            className="action-btn"
            onClick={() => onNavigate?.('notes')}
            disabled={!isAuthenticated}
          >
            <span className="icon">✏️</span>
            <span>Text Note</span>
          </button>
          <button className="action-btn" disabled>
            <span className="icon">🔍</span>
            <span>Search</span>
          </button>
          <button className="action-btn" disabled>
            <span className="icon">👥</span>
            <span>People</span>
          </button>
        </nav>

        {!isAuthenticated && (
          <p className="coming-soon">Open in Telegram to get started</p>
        )}
      </main>
    </div>
  );
};
