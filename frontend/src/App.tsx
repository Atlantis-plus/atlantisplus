import { useEffect, useState } from 'react';
import { initTelegram, isTelegramMiniApp, parsePersonDeeplink } from './lib/telegram';
import { useAuth } from './hooks/useAuth';
import { supabase } from './lib/supabase';
import { HomePage } from './pages/HomePage';
import { NotesPage } from './pages/NotesPage';
import { PeoplePage } from './pages/PeoplePage';
import { SearchPage } from './pages/SearchPage';
import { ChatPage } from './pages/ChatPage';
import './App.css';

type Page = 'home' | 'notes' | 'search' | 'people' | 'chat';

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('home');
  // Person ID from deeplink - when set, PeoplePage will open this person's profile directly
  const [initialPersonId, setInitialPersonId] = useState<string | null>(null);
  const { isAuthenticated, loading, telegramId } = useAuth();

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

  // Subscribe to Realtime navigation events from bot
  useEffect(() => {
    if (!telegramId) return;

    console.log('[Nav] Subscribing to navigation events for telegram_id:', telegramId);

    // Subscribe to INSERT events on navigation_events table filtered by telegram_id
    const channel = supabase
      .channel(`navigation:${telegramId}`)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'navigation_events',
          filter: `telegram_id=eq.${telegramId}`
        },
        (payload) => {
          console.log('[Nav] Received navigation event:', payload);
          const personId = payload.new?.person_id;
          if (personId) {
            setInitialPersonId(personId);
            setCurrentPage('people');
          }
        }
      )
      .subscribe((status) => {
        console.log('[Nav] Subscription status:', status);
      });

    return () => {
      console.log('[Nav] Unsubscribing from navigation events');
      supabase.removeChannel(channel);
    };
  }, [telegramId]);

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
      case 'people':
        return (
          <PeoplePage
            initialPersonId={initialPersonId}
            onInitialPersonIdConsumed={handlePersonIdConsumed}
          />
        );
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
