import { useEffect, useState } from 'react';
import { initTelegram, isTelegramMiniApp } from './lib/telegram';
import { useAuth } from './hooks/useAuth';
import { HomePage } from './pages/HomePage';
import { NotesPage } from './pages/NotesPage';
import { PeoplePage } from './pages/PeoplePage';
import { SearchPage } from './pages/SearchPage';
import { ChatPage } from './pages/ChatPage';
import './App.css';

type Page = 'home' | 'notes' | 'search' | 'people' | 'chat';

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
      case 'people':
        return <PeoplePage />;
      case 'search':
        return <SearchPage />;
      case 'chat':
        return <ChatPage />;
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
            className={`nav-btn ${currentPage === 'chat' ? 'active' : ''}`}
            onClick={() => setCurrentPage('chat')}
          >
            <span className="nav-icon">💬</span>
            <span className="nav-label">Chat</span>
          </button>
          <button
            className={`nav-btn ${currentPage === 'people' ? 'active' : ''}`}
            onClick={() => setCurrentPage('people')}
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
