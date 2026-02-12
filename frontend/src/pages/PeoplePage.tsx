import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { supabase } from '../lib/supabase';
import { api } from '../lib/api';
import type { EnrichmentQuotaResponse, EnrichmentStatusResponse } from '../lib/api';

interface Person {
  person_id: string;
  display_name: string;
  summary: string | null;
  created_at: string;
  owner_id: string;
  import_source?: string;
  identity_count?: number;
  has_email?: boolean;
}

interface Identity {
  identity_id: string;
  namespace: string;
  value: string;
  verified: boolean;
}

type TabType = 'own' | 'shared';

interface Assertion {
  assertion_id: string;
  predicate: string;
  object_value: string;
  confidence: number;
}

interface PeoplePageProps {
  /** Person ID from deeplink - if provided, will open this person's profile directly */
  initialPersonId?: string | null;
  /** Callback when initialPersonId has been consumed (used for navigation) */
  onInitialPersonIdConsumed?: () => void;
}

export const PeoplePage = ({ initialPersonId, onInitialPersonIdConsumed }: PeoplePageProps) => {
  const { isAuthenticated, session } = useAuth();
  const [people, setPeople] = useState<Person[]>([]);
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);
  const [assertions, setAssertions] = useState<Assertion[]>([]);
  const [identities, setIdentities] = useState<Identity[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<TabType>('own');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Enrichment state
  const [enrichmentQuota, setEnrichmentQuota] = useState<EnrichmentQuotaResponse | null>(null);
  const [enrichmentStatus, setEnrichmentStatus] = useState<EnrichmentStatusResponse | null>(null);
  const [enriching, setEnriching] = useState(false);
  const [enrichmentResult, setEnrichmentResult] = useState<{
    success: boolean;
    assertions_created: number;
    identities_created: number;
    error: string | null;
  } | null>(null);

  // Helper to convert backend errors to user-friendly messages
  const getUserFriendlyError = (error: string): string => {
    if (error.includes('quota') || error.includes('limit')) return 'Daily enrichment limit reached. Try again tomorrow.';
    if (error.includes('not found in external')) return 'No external data found for this person.';
    if (error.includes('No identifiers')) return 'Add email or LinkedIn URL to enable enrichment.';
    if (error.includes('Person not found')) return 'Person not found.';
    if (error.includes('PDL API')) return 'External service temporarily unavailable.';
    return 'Enrichment failed. Please try again later.';
  };

  const currentUserId = session?.user?.id;

  useEffect(() => {
    if (isAuthenticated) {
      fetchPeople();
    }
  }, [isAuthenticated]);

  // Handle deeplink: auto-open person profile when initialPersonId is provided
  useEffect(() => {
    if (initialPersonId && !loading && people.length > 0) {
      // Find the person by ID
      const person = people.find(p => p.person_id === initialPersonId);
      if (person) {
        // Open their profile
        handlePersonClick(person);
      }
      // Mark the initialPersonId as consumed (even if not found, to prevent infinite loop)
      onInitialPersonIdConsumed?.();
    }
  }, [initialPersonId, loading, people]);

  const fetchPeople = async () => {
    setLoading(true);

    // PostgREST has a server-side max_rows limit (default 1000)
    // We need to paginate to get all records
    const PAGE_SIZE = 1000;
    let allPeople: Person[] = [];
    let page = 0;
    let hasMore = true;

    while (hasMore) {
      const from = page * PAGE_SIZE;
      const to = from + PAGE_SIZE - 1;

      const { data, error } = await supabase
        .from('person')
        .select('person_id, display_name, summary, created_at, owner_id')
        .eq('status', 'active')
        .order('created_at', { ascending: false })
        .range(from, to);

      if (error || !data) {
        break;
      }

      allPeople = [...allPeople, ...data];
      hasMore = data.length === PAGE_SIZE;
      page++;
    }

    setPeople(allPeople);
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

  const fetchIdentities = async (personId: string) => {
    const { data } = await supabase
      .from('identity')
      .select('identity_id, namespace, value, verified')
      .eq('person_id', personId);

    if (data) {
      setIdentities(data);
    }
  };

  const handlePersonClick = async (person: Person) => {
    setSelectedPerson(person);
    setIdentities([]); // Reset identities
    setAssertions([]); // Reset assertions
    setEnrichmentResult(null); // Reset enrichment result
    setEnrichmentStatus(null); // Reset enrichment status
    await Promise.all([
      fetchAssertions(person.person_id),
      fetchIdentities(person.person_id),
      fetchEnrichmentData(person.person_id)
    ]);
  };

  const fetchEnrichmentData = async (personId: string) => {
    try {
      // Fetch quota (always should succeed)
      const quota = await api.getEnrichmentQuota();
      setEnrichmentQuota(quota);

      // Fetch status (may return 404 for never-enriched people, that's OK)
      try {
        const status = await api.getEnrichmentStatus(personId);
        setEnrichmentStatus(status);
      } catch (statusErr) {
        // 404 or "not_found" is expected for new contacts - not an error
        if (statusErr instanceof Error && (statusErr.message.includes('404') || statusErr.message.includes('not found'))) {
          setEnrichmentStatus({ status: 'not_enriched', last_enriched_at: null, last_job: null });
        } else {
          console.error('Failed to fetch enrichment status:', statusErr);
        }
      }
    } catch (err) {
      console.error('Failed to fetch enrichment quota:', err);
      // Non-critical, don't block the UI
    }
  };

  const handleEnrich = async () => {
    if (!selectedPerson || enriching) return;

    setEnriching(true);
    setEnrichmentResult(null);

    try {
      const result = await api.enrichPerson(selectedPerson.person_id);
      setEnrichmentResult(result);

      if (result.success) {
        // Refresh person data to show new assertions and identities
        await Promise.all([
          fetchAssertions(selectedPerson.person_id),
          fetchIdentities(selectedPerson.person_id),
          fetchEnrichmentData(selectedPerson.person_id)
        ]);
      }
    } catch (err) {
      setEnrichmentResult({
        success: false,
        assertions_created: 0,
        identities_created: 0,
        error: err instanceof Error ? err.message : 'Unknown error'
      });
    } finally {
      setEnriching(false);
    }
  };

  const handleBack = () => {
    setSelectedPerson(null);
    setAssertions([]);
    setIdentities([]);
    setShowDeleteConfirm(false);
    setEnrichmentResult(null);
    setEnrichmentStatus(null);
  };

  // Helper to format namespace for display
  const formatNamespace = (namespace: string): string => {
    const labels: Record<string, string> = {
      'email': '📧 Email',
      'linkedin_name': '💼 LinkedIn',
      'linkedin_url': '🔗 LinkedIn URL',
      'calendar_name': '📅 Calendar',
      'telegram_username': '✈️ Telegram',
      'freeform_name': '📝 Name variant',
      'phone': '📱 Phone',
      'email_hash': '📧 Email',
    };
    return labels[namespace] || namespace;
  };

  // Get contact identities (email, phone, social)
  const contactIdentities = identities.filter(i =>
    ['email', 'linkedin_url', 'telegram_username', 'phone'].includes(i.namespace)
  );

  // Get name identities (linkedin_name removed - no longer created by backend)
  const nameIdentities = identities.filter(i =>
    ['calendar_name', 'freeform_name'].includes(i.namespace)
  );

  // Helper to parse and format LinkedIn values
  const formatLinkedInValue = (value: string): { href: string; label: string } => {
    // Case 1: Profile URL - https://www.linkedin.com/in/john-smith/ or https://linkedin.com/in/john-smith
    const profileMatch = value.match(/^https?:\/\/(?:www\.)?linkedin\.com\/in\/([^/?]+)/);
    if (profileMatch) {
      const slug = profileMatch[1].replace(/\/$/, ''); // Remove trailing slash
      return { href: value, label: slug };
    }

    // Case 2: Search URL - https://www.linkedin.com/search/results/people/?keywords=John%20Smith
    const searchMatch = value.match(/^https?:\/\/(?:www\.)?linkedin\.com\/search\/results\/people\/\?.*keywords=([^&]+)/);
    if (searchMatch) {
      let keywords: string;
      try {
        keywords = decodeURIComponent(searchMatch[1]).replace(/\+/g, ' ');
      } catch {
        // Fallback if malformed percent-encoding
        keywords = searchMatch[1].replace(/\+/g, ' ');
      }
      return { href: value, label: `Search: ${keywords}` };
    }

    // Case 3: Any other LinkedIn URL (company pages, posts, etc.)
    if (value.match(/^https?:\/\/(?:www\.)?linkedin\.com\//)) {
      // Extract meaningful part after linkedin.com/
      const pathMatch = value.match(/linkedin\.com\/(.+)/);
      const path = pathMatch ? pathMatch[1].replace(/\/$/, '') : value;
      return { href: value, label: path.length > 40 ? path.slice(0, 40) + '...' : path };
    }

    // Case 4: Just a username/slug without URL
    if (!value.includes('://') && !value.includes(' ')) {
      const cleanSlug = value.replace(/^@/, '').replace(/\/$/, '');
      return {
        href: `https://www.linkedin.com/in/${cleanSlug}`,
        label: cleanSlug
      };
    }

    // Fallback: treat as a name and create safe search URL (prevents XSS with javascript: protocol)
    return {
      href: `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(value)}`,
      label: `Search: ${value}`
    };
  };

  const handleDelete = async () => {
    if (!selectedPerson) return;

    setDeleting(true);
    try {
      // Soft delete: update status to 'deleted'
      await supabase
        .from('person')
        .update({ status: 'deleted' })
        .eq('person_id', selectedPerson.person_id);

      // Remove from local state
      setPeople(prev => prev.filter(p => p.person_id !== selectedPerson.person_id));

      // Go back to list
      setSelectedPerson(null);
      setShowDeleteConfirm(false);
    } catch (err) {
      console.error('Failed to delete person:', err);
      alert('Failed to delete contact');
    } finally {
      setDeleting(false);
    }
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
          {isOwnPerson && (
            <button
              className="delete-btn"
              onClick={() => setShowDeleteConfirm(true)}
              disabled={deleting}
            >
              🗑️ Delete
            </button>
          )}
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

          {/* Contact Info Section - always show for debugging */}
          <div className="contacts-section">
            <h3>Contacts ({contactIdentities.length} / {identities.length} total)</h3>
            {contactIdentities.length > 0 ? (
              <ul className="contacts-list">
                {contactIdentities.map((identity) => (
                  <li key={identity.identity_id} className="contact-item">
                    <span className="contact-type">{formatNamespace(identity.namespace)}</span>
                    <span className="contact-value">
                      {identity.namespace === 'email' ? (
                        <a href={`mailto:${identity.value}`}>{identity.value}</a>
                      ) : identity.namespace === 'linkedin_url' ? (
                        (() => {
                          const { href, label } = formatLinkedInValue(identity.value);
                          return (
                            <a href={href} target="_blank" rel="noopener noreferrer">
                              {label}
                            </a>
                          );
                        })()
                      ) : identity.namespace === 'telegram_username' ? (
                        <a href={`https://t.me/${identity.value.replace('@', '')}`} target="_blank" rel="noopener noreferrer">
                          {identity.value}
                        </a>
                      ) : (
                        identity.value
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-state">No contact info</p>
            )}
          </div>

          {/* Name Variants / Sources */}
          {nameIdentities.length > 1 && (
            <div className="sources-section">
              <h3>Also known as ({nameIdentities.length} sources)</h3>
              <div className="name-variants">
                {nameIdentities.map((identity) => (
                  <span key={identity.identity_id} className="name-variant-tag">
                    {identity.value}
                    <span className="source-hint">
                      {identity.namespace === 'calendar_name' ? ' (Calendar)' : ''}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Enrichment Section - only for own people */}
          {isOwnPerson && (
            <div className="enrichment-section">
              <h3>External Data</h3>

              {/* Enrichment Result Message */}
              {enrichmentResult && (
                <div className={`enrichment-result ${enrichmentResult.success ? 'success' : 'error'}`}>
                  {enrichmentResult.success ? (
                    <>
                      Found {enrichmentResult.assertions_created} new facts
                      {enrichmentResult.identities_created > 0 && ` and ${enrichmentResult.identities_created} contacts`}
                    </>
                  ) : (
                    <>{getUserFriendlyError(enrichmentResult.error || 'Unknown error')}</>
                  )}
                </div>
              )}

              {/* Enrichment Status */}
              {enrichmentStatus?.status === 'enriched' && !enrichmentResult && (
                <div className="enrichment-status">
                  Last enriched: {enrichmentStatus.last_enriched_at
                    ? new Date(enrichmentStatus.last_enriched_at).toLocaleDateString()
                    : 'Unknown'}
                </div>
              )}

              {/* Quota Display */}
              {enrichmentQuota && (
                <div className="enrichment-quota">
                  {enrichmentQuota.daily_used}/{enrichmentQuota.daily_limit} enrichments used today
                </div>
              )}

              {/* Hint when no enrichable identifiers */}
              {!contactIdentities.some(i => ['email', 'linkedin_url'].includes(i.namespace)) && (
                <div className="enrichment-hint">
                  💡 Add email or LinkedIn URL to get better enrichment results
                </div>
              )}

              {/* Enrich Button */}
              <button
                className="enrich-btn"
                onClick={handleEnrich}
                disabled={enriching || !enrichmentQuota?.can_enrich}
              >
                {enriching ? (
                  <>
                    <span className="spinner-small"></span>
                    Enriching...
                  </>
                ) : enrichmentStatus?.status === 'enriched' ? (
                  'Re-enrich from external sources'
                ) : (
                  'Enrich from external sources'
                )}
              </button>

              {/* Quota Exhausted Message */}
              {enrichmentQuota && !enrichmentQuota.can_enrich && enrichmentQuota.reason && (
                <div className="enrichment-limit-notice">
                  {enrichmentQuota.reason}
                </div>
              )}
            </div>
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

        {/* Delete Confirmation Modal */}
        {showDeleteConfirm && (
          <div className="modal-overlay" onClick={() => setShowDeleteConfirm(false)}>
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
              <h3>Delete Contact?</h3>
              <p>Are you sure you want to delete <strong>{selectedPerson.display_name}</strong>?</p>
              <p className="modal-hint">This will remove the person and all their facts.</p>
              <div className="modal-actions">
                <button
                  className="btn-secondary"
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={deleting}
                >
                  Cancel
                </button>
                <button
                  className="btn-danger"
                  onClick={handleDelete}
                  disabled={deleting}
                >
                  {deleting ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          </div>
        )}
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
