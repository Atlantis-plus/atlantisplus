import { useEffect, useState } from 'react';
import { initTelegram, isTelegramMiniApp, parsePersonDeeplink } from './lib/telegram';
import { useAuth } from './hooks/useAuth';
import { HomePage } from './pages/HomePage';
import { NotesPage } from './pages/NotesPage';
import { PeoplePage } from './pages/PeoplePage';
import { ChatPage } from './pages/ChatPage';
import './App.css';

type Page = 'people' | 'notes' | 'chat' | 'import';

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('people');
  // Person ID from deeplink - when set, PeoplePage will open this person's profile directly
  const [initialPersonId, setInitialPersonId] = useState<string | null>(null);
  const { isAuthenticated, loading } = useAuth();

  useEffect(() => {
    if (isTelegramMiniApp()) {
      initTelegram();

      // Check for person deeplink (e.g., t.me/bot/app?startapp=person_abc123)
      const personId = parsePersonDeeplink();
      if (personId) {
        setInitialPersonId(personId);
        setCurrentPage('people');
      }
    }
  }, []);

  if (loading) {
    return (
      <div className="page">
        <div className="loading">Loading...</div>
      </div>
    );
  }

  // Clear initialPersonId after PeoplePage has used it
  const handlePersonIdConsumed = () => {
    setInitialPersonId(null);
  };

  const renderPage = () => {
    switch (currentPage) {
      case 'notes':
        return <NotesPage />;
      case 'chat':
        return <ChatPage />;
      case 'import':
        return <HomePage onNavigate={setCurrentPage} />;
      case 'people':
      default:
        return (
          <PeoplePage
            initialPersonId={initialPersonId}
            onInitialPersonIdConsumed={handlePersonIdConsumed}
          />
        );
    }
  };

  return (
    <div className="app">
      {renderPage()}

      {/* Bottom navigation */}
      {isAuthenticated && (
        <nav className="bottom-nav">
          <button
            className={`nav-btn ${currentPage === 'people' ? 'active' : ''}`}
            onClick={() => setCurrentPage('people')}
          >
            <span className="nav-icon">👥</span>
            <span className="nav-label">People</span>
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
            className={`nav-btn ${currentPage === 'import' ? 'active' : ''}`}
            onClick={() => setCurrentPage('import')}
          >
            <span className="nav-icon">📥</span>
            <span className="nav-label">Import</span>
          </button>
        </nav>
      )}
    </div>
  );
}

export default App;
