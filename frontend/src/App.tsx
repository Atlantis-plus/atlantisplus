import { useEffect, useState } from 'react';
import { initTelegram, isTelegramMiniApp } from './lib/telegram';
import { useAuth } from './hooks/useAuth';
import { HomePage } from './pages/HomePage';
import { NotesPage } from './pages/NotesPage';
import './App.css';

type Page = 'home' | 'notes' | 'search' | 'people';

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('home');
  const { isAuthenticated, loading } = useAuth();

  useEffect(() => {
    if (isTelegramMiniApp()) {
      initTelegram();
    }
  }, []);

  if (loading) {
    return (
      <div className="page">
        <div className="loading">Loading...</div>
      </div>
    );
  }

  const renderPage = () => {
    switch (currentPage) {
      case 'notes':
        return <NotesPage />;
      case 'home':
      default:
        return <HomePage onNavigate={setCurrentPage} />;
    }
  };

  return (
    <div className="app">
      {renderPage()}

      {/* Bottom navigation */}
      {isAuthenticated && (
        <nav className="bottom-nav">
          <button
            className={`nav-btn ${currentPage === 'home' ? 'active' : ''}`}
            onClick={() => setCurrentPage('home')}
          >
            <span className="nav-icon">🏠</span>
            <span className="nav-label">Home</span>
          </button>
          <button
            className={`nav-btn ${currentPage === 'notes' ? 'active' : ''}`}
            onClick={() => setCurrentPage('notes')}
          >
            <span className="nav-icon">📝</span>
            <span className="nav-label">Notes</span>
          </button>
          <button
            className={`nav-btn ${currentPage === 'search' ? 'active' : ''}`}
            onClick={() => setCurrentPage('search')}
            disabled
          >
            <span className="nav-icon">🔍</span>
            <span className="nav-label">Search</span>
          </button>
          <button
            className={`nav-btn ${currentPage === 'people' ? 'active' : ''}`}
            onClick={() => setCurrentPage('people')}
            disabled
          >
            <span className="nav-icon">👥</span>
            <span className="nav-label">People</span>
          </button>
        </nav>
      )}
    </div>
  );
}

export default App;
