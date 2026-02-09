import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { supabase } from '../lib/supabase';

interface Person {
  person_id: string;
  display_name: string;
  summary: string | null;
  created_at: string;
  owner_id: string;
}

type TabType = 'own' | 'shared';

interface Assertion {
  assertion_id: string;
  predicate: string;
  object_value: string;
  confidence: number;
}

export const PeoplePage = () => {
  const { isAuthenticated, session } = useAuth();
  const [people, setPeople] = useState<Person[]>([]);
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);
  const [assertions, setAssertions] = useState<Assertion[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<TabType>('own');

  const currentUserId = session?.user?.id;

  useEffect(() => {
    if (isAuthenticated) {
      fetchPeople();
    }
  }, [isAuthenticated]);

  const fetchPeople = async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from('person')
      .select('person_id, display_name, summary, created_at, owner_id')
      .eq('status', 'active')
      .order('created_at', { ascending: false });

    if (!error && data) {
      setPeople(data);
    }
    setLoading(false);
  };

  const fetchAssertions = async (personId: string) => {
    const { data } = await supabase
      .from('assertion')
      .select('assertion_id, predicate, object_value, confidence')
      .eq('subject_person_id', personId)
      .order('confidence', { ascending: false });

    if (data) {
      setAssertions(data);
    }
  };

  const handlePersonClick = async (person: Person) => {
    setSelectedPerson(person);
    await fetchAssertions(person.person_id);
  };

  const handleBack = () => {
    setSelectedPerson(null);
    setAssertions([]);
  };

  // Split people into own and shared
  const ownPeople = people.filter(p => p.owner_id === currentUserId);
  const sharedPeople = people.filter(p => p.owner_id !== currentUserId);

  // Apply search filter and tab selection
  const displayPeople = activeTab === 'own' ? ownPeople : sharedPeople;
  const filteredPeople = displayPeople.filter(p =>
    p.display_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const formatPredicate = (predicate: string): string => {
    const labels: Record<string, string> = {
      'role': 'Role',
      'role_is': 'Role',
      'works_at': 'Works at',
      'expertise': 'Expertise',
      'strong_at': 'Strong at',
      'can_help_with': 'Can help with',
      'worked_on': 'Worked on',
      'location': 'Location',
      'located_in': 'Location',
      'background': 'Background',
      'speaks_language': 'Languages',
      'notable_achievement': 'Achievement',
      'contact_context': 'How we met',
      'relationship_depth': 'Relationship',
      'recommend_for': '✓ Recommended for',
      'not_recommend_for': '✗ Not recommended for',
      'reputation_note': 'Reputation',
      'interested_in': 'Interested in',
      'note': 'Note'
    };
    return labels[predicate] || predicate;
  };

  if (!isAuthenticated) {
    return (
      <div className="page">
        <div className="error">Please authenticate first</div>
      </div>
    );
  }

  // Person detail view
  if (selectedPerson) {
    const isOwnPerson = selectedPerson.owner_id === currentUserId;

    return (
      <div className="page">
        <header className="header">
          <button className="back-btn" onClick={handleBack}>← Back</button>
          <h1>
            {selectedPerson.display_name}
            {!isOwnPerson && <span className="shared-badge">Shared</span>}
          </h1>
        </header>

        <main className="main">
          {!isOwnPerson && (
            <div className="shared-notice">
              Contact added by another user (read-only)
            </div>
          )}
          {selectedPerson.summary && (
            <p className="person-summary">{selectedPerson.summary}</p>
          )}

          <div className="assertions-section">
            <h3>Known Facts</h3>
            {assertions.length === 0 ? (
              <p className="empty-state">No data</p>
            ) : (
              <ul className="assertions-list">
                {assertions.map((a) => (
                  <li key={a.assertion_id} className="assertion-item">
                    <span className="assertion-predicate">{formatPredicate(a.predicate)}</span>
                    <span className="assertion-value">{a.object_value}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </main>
      </div>
    );
  }

  // People list view
  return (
    <div className="page">
      <header className="header">
        <h1>People</h1>
        <p className="subtitle">{ownPeople.length} own · {sharedPeople.length} shared</p>
      </header>

      <main className="main">
        {/* Tabs */}
        <div className="mode-switcher">
          <button
            className={`mode-btn ${activeTab === 'own' ? 'active' : ''}`}
            onClick={() => setActiveTab('own')}
          >
            Mine ({ownPeople.length})
          </button>
          <button
            className={`mode-btn ${activeTab === 'shared' ? 'active' : ''}`}
            onClick={() => setActiveTab('shared')}
          >
            Shared ({sharedPeople.length})
          </button>
        </div>

        <div className="search-box">
          <input
            type="text"
            placeholder="Search by name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {loading ? (
          <div className="loading">Loading...</div>
        ) : filteredPeople.length === 0 ? (
          <div className="empty-state">
            {searchQuery
              ? 'No one found'
              : activeTab === 'own'
                ? 'No people yet. Add a note!'
                : 'No shared contacts from other users'}
          </div>
        ) : (
          <ul className="people-list">
            {filteredPeople.map((person) => {
              const isOwn = person.owner_id === currentUserId;
              return (
                <li
                  key={person.person_id}
                  className={`person-card ${!isOwn ? 'shared' : ''}`}
                  onClick={() => handlePersonClick(person)}
                >
                  <div className={`person-avatar ${!isOwn ? 'shared' : ''}`}>
                    {person.display_name.charAt(0).toUpperCase()}
                  </div>
                  <div className="person-info">
                    <span className="person-name">
                      {person.display_name}
                      {!isOwn && <span className="shared-badge">Shared</span>}
                    </span>
                    {person.summary && (
                      <span className="person-summary-preview">
                        {person.summary.slice(0, 60)}...
                      </span>
                    )}
                  </div>
                  <span className="chevron">›</span>
                </li>
              );
            })}
          </ul>
        )}
      </main>
    </div>
  );
};
