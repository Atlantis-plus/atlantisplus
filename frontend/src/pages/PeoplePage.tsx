import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { supabase } from '../lib/supabase';

interface Person {
  person_id: string;
  display_name: string;
  summary: string | null;
  created_at: string;
}

interface Assertion {
  assertion_id: string;
  predicate: string;
  object_value: string;
  confidence: number;
}

export const PeoplePage = () => {
  const { isAuthenticated } = useAuth();
  const [people, setPeople] = useState<Person[]>([]);
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);
  const [assertions, setAssertions] = useState<Assertion[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (isAuthenticated) {
      fetchPeople();
    }
  }, [isAuthenticated]);

  const fetchPeople = async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from('person')
      .select('person_id, display_name, summary, created_at')
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

  const filteredPeople = people.filter(p =>
    p.display_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const formatPredicate = (predicate: string): string => {
    const labels: Record<string, string> = {
      'role': 'Роль',
      'role_is': 'Роль',
      'works_at': 'Работает в',
      'expertise': 'Экспертиза',
      'strong_at': 'Силён в',
      'can_help_with': 'Может помочь с',
      'location': 'Локация',
      'located_in': 'Локация',
      'background': 'Бэкграунд',
      'notable_achievement': 'Достижение',
      'contact_context': 'Контекст знакомства',
      'reputation_note': 'Репутация',
      'interested_in': 'Интересуется',
      'years_in_location': 'Лет в локации'
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
    return (
      <div className="page">
        <header className="header">
          <button className="back-btn" onClick={handleBack}>← Назад</button>
          <h1>{selectedPerson.display_name}</h1>
        </header>

        <main className="main">
          {selectedPerson.summary && (
            <p className="person-summary">{selectedPerson.summary}</p>
          )}

          <div className="assertions-section">
            <h3>Известные факты</h3>
            {assertions.length === 0 ? (
              <p className="empty-state">Нет данных</p>
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
        <p className="subtitle">{people.length} человек в сети</p>
      </header>

      <main className="main">
        <div className="search-box">
          <input
            type="text"
            placeholder="Поиск по имени..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {loading ? (
          <div className="loading">Загрузка...</div>
        ) : filteredPeople.length === 0 ? (
          <div className="empty-state">
            {searchQuery ? 'Никого не найдено' : 'Пока нет людей. Добавьте заметку!'}
          </div>
        ) : (
          <ul className="people-list">
            {filteredPeople.map((person) => (
              <li
                key={person.person_id}
                className="person-card"
                onClick={() => handlePersonClick(person)}
              >
                <div className="person-avatar">
                  {person.display_name.charAt(0).toUpperCase()}
                </div>
                <div className="person-info">
                  <span className="person-name">{person.display_name}</span>
                  {person.summary && (
                    <span className="person-summary-preview">
                      {person.summary.slice(0, 60)}...
                    </span>
                  )}
                </div>
                <span className="chevron">›</span>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
};
