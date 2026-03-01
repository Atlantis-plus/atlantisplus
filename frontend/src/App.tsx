import { useEffect, useState } from 'react';
import { initTelegram, isTelegramMiniApp, parsePersonDeeplink } from './lib/telegram';
import { useAuth } from './hooks/useAuth';
import { useUserType } from './hooks/useUserType';
import { HomePage } from './pages/HomePage';
import { NotesPage } from './pages/NotesPage';
import { PeoplePage } from './pages/PeoplePage';
import { ChatPage } from './pages/ChatPage';
import { SelfProfilePage } from './pages/SelfProfilePage';
import { CommunitiesPage } from './pages/CommunitiesPage';
import { CommunityDetailPage } from './pages/CommunityDetailPage';
import { PeopleIcon, NotesIcon, ChatIcon, ImportIcon, SpinnerIcon, CommunityIcon } from './components/icons';
import './App.css';

type Page = 'people' | 'notes' | 'chat' | 'import' | 'self-profile' | 'communities' | 'community-detail';

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('people');
  // Person ID from deeplink - when set, PeoplePage will open this person's profile directly
  const [initialPersonId, setInitialPersonId] = useState<string | null>(null);
  // Community ID for self-profile page (community members)
  const [selfProfileCommunityId, setSelfProfileCommunityId] = useState<string | null>(null);
  // Selected community for detail view
  const [selectedCommunityId, setSelectedCommunityId] = useState<string | null>(null);

  const { isAuthenticated, loading: authLoading } = useAuth();
  const { userType, userInfo, loading: userTypeLoading } = useUserType();

  useEffect(() => {
    if (isTelegramMiniApp()) {
      initTelegram();

      // Check for person deeplink (e.g., t.me/bot/app?startapp=person_abc123)
      const personId = parsePersonDeeplink();
      if (personId) {
        setInitialPersonId(personId);
        setCurrentPage('people');
        return;
      }

      // Check for community join deeplink - but this should be handled by bot, not Mini App
      // Mini App just shows the appropriate UI based on user type
    }
  }, []);

  // Set appropriate page based on user type
  useEffect(() => {
    if (!userTypeLoading && userType) {
      if (userType === 'community_member') {
        // Community members see only their profile
        setCurrentPage('self-profile');

        // Get first community they're a member of
        if (userInfo?.communities_member && userInfo.communities_member.length > 0) {
          setSelfProfileCommunityId(userInfo.communities_member[0].community_id);
        }
      }
    }
  }, [userType, userInfo, userTypeLoading]);

  const loading = authLoading || (isAuthenticated && userTypeLoading);

  if (loading) {
    return (
      <div className="app-loading">
        <SpinnerIcon size={32} className="mx-auto mb-4 text-[var(--accent-primary)]" />
        <p className="text-[var(--text-muted)]">Loading...</p>
      </div>
    );
  }

  // Clear initialPersonId after PeoplePage has used it
  const handlePersonIdConsumed = () => {
    setInitialPersonId(null);
  };

  // For community members, show only SelfProfilePage
  if (userType === 'community_member') {
    return (
      <div className="app">
        <SelfProfilePage
          communityId={selfProfileCommunityId || undefined}
          communities={userInfo?.communities_member || []}
          onCommunityChange={(id) => setSelfProfileCommunityId(id)}
        />
      </div>
    );
  }

  const renderPage = () => {
    switch (currentPage) {
      case 'notes':
        return <NotesPage />;
      case 'chat':
        return <ChatPage />;
      case 'import':
        return <HomePage onNavigate={setCurrentPage} />;
      case 'self-profile':
        return (
          <SelfProfilePage
            communityId={selfProfileCommunityId || undefined}
            communities={userInfo?.communities_member || []}
            onCommunityChange={(id) => setSelfProfileCommunityId(id)}
            onBack={() => setCurrentPage('people')}
          />
        );
      case 'communities':
        return (
          <CommunitiesPage
            onSelectCommunity={(id) => {
              setSelectedCommunityId(id);
              setCurrentPage('community-detail');
            }}
            communities={userInfo?.communities_owned || []}
            loading={userTypeLoading}
          />
        );
      case 'community-detail':
        return selectedCommunityId ? (
          <CommunityDetailPage
            communityId={selectedCommunityId}
            onBack={() => setCurrentPage('communities')}
          />
        ) : (
          <CommunitiesPage
            onSelectCommunity={(id) => {
              setSelectedCommunityId(id);
              setCurrentPage('community-detail');
            }}
            communities={userInfo?.communities_owned || []}
            loading={userTypeLoading}
          />
        );
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

      {/* Bottom navigation - community members never reach here due to early return above */}
      {isAuthenticated && (
        <nav className="bottom-nav">
          <button
            className={`nav-btn ${currentPage === 'people' ? 'active' : ''}`}
            onClick={() => setCurrentPage('people')}
          >
            <PeopleIcon size={22} />
            <span className="nav-label">People</span>
          </button>
          <button
            className={`nav-btn ${currentPage === 'notes' ? 'active' : ''}`}
            onClick={() => setCurrentPage('notes')}
          >
            <NotesIcon size={22} />
            <span className="nav-label">Notes</span>
          </button>
          <button
            className={`nav-btn ${currentPage === 'chat' ? 'active' : ''}`}
            onClick={() => setCurrentPage('chat')}
          >
            <ChatIcon size={22} />
            <span className="nav-label">Chat</span>
          </button>
          <button
            className={`nav-btn ${currentPage === 'import' ? 'active' : ''}`}
            onClick={() => setCurrentPage('import')}
          >
            <ImportIcon size={22} />
            <span className="nav-label">Import</span>
          </button>
          {/* Communities tab - only for admins/atlantis+ */}
          {(userType === 'atlantis_plus' || userType === 'community_admin') && (
            <button
              className={`nav-btn ${currentPage === 'communities' || currentPage === 'community-detail' ? 'active' : ''}`}
              onClick={() => setCurrentPage('communities')}
            >
              <CommunityIcon size={22} />
              <span className="nav-label">Groups</span>
            </button>
          )}
        </nav>
      )}
    </div>
  );
}

export default App;
