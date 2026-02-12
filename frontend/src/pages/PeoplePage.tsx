import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { supabase } from '../lib/supabase';
import { api } from '../lib/api';
import type { EnrichmentQuotaResponse, EnrichmentStatusResponse } from '../lib/api';
import {
  ChevronLeftIcon, ChevronRightIcon, SearchIcon,
  EmailIcon, LinkedInIcon, TelegramIcon, PhoneIcon, CalendarIcon, UserIcon,
  TrashIcon, EnrichIcon, CheckCircleIcon, ErrorCircleIcon, SpinnerIcon,
  XIcon, StarIcon, RobotIcon, InfoIcon, ExternalLinkIcon
} from '../components/icons';

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

// Helper to get predicate category for color coding
const getPredicateCategory = (predicate: string): 'role' | 'skill' | 'location' | 'relationship' | 'reputation' | 'anti' | 'default' => {
  const rolePredicates = ['role', 'role_is', 'works_at', 'worked_on'];
  const skillPredicates = ['strong_at', 'can_help_with', 'expertise', 'interested_in', 'notable_achievement'];
  const locationPredicates = ['located_in', 'location', 'speaks_language'];
  const relationshipPredicates = ['contact_context', 'knows', 'relationship_depth', 'background'];
  const reputationPredicates = ['recommend_for', 'reputation_note'];
  const antiPredicates = ['not_recommend_for'];

  if (rolePredicates.includes(predicate)) return 'role';
  if (skillPredicates.includes(predicate)) return 'skill';
  if (locationPredicates.includes(predicate)) return 'location';
  if (relationshipPredicates.includes(predicate)) return 'relationship';
  if (reputationPredicates.includes(predicate)) return 'reputation';
  if (antiPredicates.includes(predicate)) return 'anti';
  return 'default';
};

// Get badge style class based on predicate category
const getPredicateBadgeClass = (predicate: string): string => {
  const category = getPredicateCategory(predicate);
  const baseClass = 'inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold border-2 border-black';

  switch (category) {
    case 'role':
      return `${baseClass} bg-blue-200 text-black`;
    case 'skill':
      return `${baseClass} bg-mint text-black`;
    case 'location':
      return `${baseClass} bg-peach text-black`;
    case 'relationship':
      return `${baseClass} bg-lavender text-black`;
    case 'reputation':
      return `${baseClass} bg-neo-yellow text-black`;
    case 'anti':
      return `${baseClass} bg-coral text-white`;
    default:
      return `${baseClass} bg-neo-gray-200 text-black`;
  }
};

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

  // Helper to render identity icon based on namespace
  const renderIdentityIcon = (namespace: string) => {
    switch (namespace) {
      case 'email':
      case 'email_hash':
        return <EmailIcon size={16} className="flex-shrink-0" />;
      case 'linkedin_name':
      case 'linkedin_url':
        return <LinkedInIcon size={16} className="flex-shrink-0" />;
      case 'telegram_username':
        return <TelegramIcon size={16} className="flex-shrink-0" />;
      case 'phone':
        return <PhoneIcon size={16} className="flex-shrink-0" />;
      case 'calendar_name':
        return <CalendarIcon size={16} className="flex-shrink-0" />;
      case 'freeform_name':
        return <UserIcon size={16} className="flex-shrink-0" />;
      default:
        return <InfoIcon size={16} className="flex-shrink-0" />;
    }
  };

  // Helper to format namespace for display
  const formatNamespace = (namespace: string): string => {
    const labels: Record<string, string> = {
      'email': 'Email',
      'linkedin_name': 'LinkedIn',
      'linkedin_url': 'LinkedIn URL',
      'calendar_name': 'Calendar',
      'telegram_username': 'Telegram',
      'freeform_name': 'Name variant',
      'phone': 'Phone',
      'email_hash': 'Email',
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

  const formatPredicate = (predicate: string): { label: string; icon?: React.ReactNode } => {
    const labels: Record<string, { label: string; icon?: React.ReactNode }> = {
      'role': { label: 'Role' },
      'role_is': { label: 'Role' },
      'works_at': { label: 'Works at' },
      'expertise': { label: 'Expertise' },
      'strong_at': { label: 'Strong at' },
      'can_help_with': { label: 'Can help with' },
      'worked_on': { label: 'Worked on' },
      'location': { label: 'Location' },
      'located_in': { label: 'Location' },
      'background': { label: 'Background' },
      'speaks_language': { label: 'Languages' },
      'notable_achievement': { label: 'Achievement' },
      'contact_context': { label: 'How we met' },
      'relationship_depth': { label: 'Relationship' },
      'recommend_for': { label: 'Recommended for', icon: <StarIcon size={14} className="text-green-600" /> },
      'not_recommend_for': { label: 'Not recommended for', icon: <XIcon size={14} className="text-red-500" /> },
      'reputation_note': { label: 'Reputation' },
      'interested_in': { label: 'Interested in' },
      'note': { label: 'Note' }
    };
    return labels[predicate] || { label: predicate };
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] p-4 flex items-center justify-center">
        <div className="card-neo p-6 text-center">
          <ErrorCircleIcon size={48} className="mx-auto mb-4 text-coral" />
          <p className="text-lg font-semibold">Please authenticate first</p>
        </div>
      </div>
    );
  }

  // Person detail view
  if (selectedPerson) {
    const isOwnPerson = selectedPerson.owner_id === currentUserId;

    return (
      <div className="min-h-screen bg-[var(--bg-primary)]">
        {/* Header */}
        <header className="sticky top-0 z-10 bg-[var(--bg-primary)] border-b-3 border-black p-4">
          <div className="flex items-center gap-3">
            <button
              className="btn-neo p-2 flex-shrink-0"
              onClick={handleBack}
              aria-label="Back"
            >
              <ChevronLeftIcon size={20} />
            </button>
            <div className="flex-1 min-w-0">
              <h1 className="font-heading text-xl font-bold truncate flex items-center gap-2">
                {selectedPerson.display_name}
                {!isOwnPerson && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold bg-lavender border-2 border-black">
                    <RobotIcon size={12} />
                    Shared
                  </span>
                )}
              </h1>
            </div>
          </div>
        </header>

        <main className="p-4 pb-24 space-y-4">
          {/* Shared notice */}
          {!isOwnPerson && (
            <div className="card-neo bg-lavender/30 p-3 flex items-center gap-2">
              <InfoIcon size={18} className="flex-shrink-0" />
              <span className="text-sm">Contact added by another user (read-only)</span>
            </div>
          )}

          {/* Summary */}
          {selectedPerson.summary && (
            <div className="card-neo p-4">
              <p className="text-[var(--text-secondary)]">{selectedPerson.summary}</p>
            </div>
          )}

          {/* Contact Info Section */}
          <div className="card-neo p-4">
            <h3 className="font-heading font-bold text-lg mb-3 flex items-center gap-2">
              Contacts
              <span className="text-sm font-normal text-[var(--text-muted)]">
                ({contactIdentities.length})
              </span>
            </h3>
            {contactIdentities.length > 0 ? (
              <ul className="space-y-2">
                {contactIdentities.map((identity) => (
                  <li
                    key={identity.identity_id}
                    className="flex items-center gap-3 p-2 bg-[var(--bg-secondary)] border-2 border-black"
                  >
                    {renderIdentityIcon(identity.namespace)}
                    <span className="text-sm font-medium text-[var(--text-muted)] min-w-[80px]">
                      {formatNamespace(identity.namespace)}
                    </span>
                    <span className="flex-1 truncate">
                      {identity.namespace === 'email' ? (
                        <a
                          href={`mailto:${identity.value}`}
                          className="text-[var(--accent-primary)] hover:underline flex items-center gap-1"
                        >
                          {identity.value}
                          <ExternalLinkIcon size={12} />
                        </a>
                      ) : identity.namespace === 'linkedin_url' ? (
                        (() => {
                          const { href, label } = formatLinkedInValue(identity.value);
                          return (
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[var(--accent-primary)] hover:underline flex items-center gap-1"
                            >
                              {label}
                              <ExternalLinkIcon size={12} />
                            </a>
                          );
                        })()
                      ) : identity.namespace === 'telegram_username' ? (
                        <a
                          href={`https://t.me/${identity.value.replace('@', '')}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[var(--accent-primary)] hover:underline flex items-center gap-1"
                        >
                          {identity.value}
                          <ExternalLinkIcon size={12} />
                        </a>
                      ) : (
                        identity.value
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[var(--text-muted)] text-sm italic">No contact info</p>
            )}
          </div>

          {/* Name Variants / Sources */}
          {nameIdentities.length > 1 && (
            <div className="card-neo p-4">
              <h3 className="font-heading font-bold text-lg mb-3">
                Also known as
                <span className="text-sm font-normal text-[var(--text-muted)] ml-2">
                  ({nameIdentities.length} sources)
                </span>
              </h3>
              <div className="flex flex-wrap gap-2">
                {nameIdentities.map((identity) => (
                  <span
                    key={identity.identity_id}
                    className="inline-flex items-center gap-1 px-3 py-1 bg-[var(--bg-secondary)] border-2 border-black text-sm"
                  >
                    {renderIdentityIcon(identity.namespace)}
                    {identity.value}
                    {identity.namespace === 'calendar_name' && (
                      <span className="text-[var(--text-muted)] text-xs">(Calendar)</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Enrichment Section - only for own people */}
          {isOwnPerson && (
            <div className="card-neo p-4">
              <h3 className="font-heading font-bold text-lg mb-3 flex items-center gap-2">
                <EnrichIcon size={20} />
                External Data
              </h3>

              {/* Enrichment Result Message */}
              {enrichmentResult && (
                <div className={`p-3 mb-3 border-2 border-black flex items-center gap-2 ${
                  enrichmentResult.success ? 'bg-mint' : 'bg-coral text-white'
                }`}>
                  {enrichmentResult.success ? (
                    <>
                      <CheckCircleIcon size={18} />
                      <span>
                        Found {enrichmentResult.assertions_created} new facts
                        {enrichmentResult.identities_created > 0 && ` and ${enrichmentResult.identities_created} contacts`}
                      </span>
                    </>
                  ) : (
                    <>
                      <ErrorCircleIcon size={18} />
                      <span>{getUserFriendlyError(enrichmentResult.error || 'Unknown error')}</span>
                    </>
                  )}
                </div>
              )}

              {/* Enrichment Status */}
              {enrichmentStatus?.status === 'enriched' && !enrichmentResult && (
                <div className="p-3 mb-3 bg-[var(--bg-secondary)] border-2 border-black text-sm flex items-center gap-2">
                  <CheckCircleIcon size={16} className="text-green-600" />
                  <span>
                    Enriched on {enrichmentStatus.last_enriched_at
                      ? new Date(enrichmentStatus.last_enriched_at).toLocaleDateString()
                      : 'Unknown'}
                    {enrichmentStatus.enrichment_details && (
                      <span className="text-[var(--text-muted)]">
                        {' '}({enrichmentStatus.enrichment_details.facts_added} facts
                        {enrichmentStatus.enrichment_details.identities_added > 0 &&
                          `, ${enrichmentStatus.enrichment_details.identities_added} contacts`})
                      </span>
                    )}
                  </span>
                </div>
              )}

              {/* Quota Display */}
              {enrichmentQuota && (
                <div className="text-sm text-[var(--text-muted)] mb-3">
                  {enrichmentQuota.daily_used}/{enrichmentQuota.daily_limit} enrichments used today
                </div>
              )}

              {/* Hint when no enrichable identifiers */}
              {!contactIdentities.some(i => ['email', 'linkedin_url'].includes(i.namespace)) && (
                <div className="p-3 mb-3 bg-neo-yellow/30 border-2 border-black text-sm flex items-center gap-2">
                  <InfoIcon size={16} />
                  <span>Add email or LinkedIn URL to get better enrichment results</span>
                </div>
              )}

              {/* Enrich Button */}
              <button
                className="btn-neo btn-neo-primary w-full flex items-center justify-center gap-2"
                onClick={handleEnrich}
                disabled={enriching || !enrichmentQuota?.can_enrich}
              >
                {enriching ? (
                  <>
                    <SpinnerIcon size={18} />
                    Enriching...
                  </>
                ) : (
                  <>
                    <EnrichIcon size={18} />
                    {enrichmentStatus?.status === 'enriched'
                      ? 'Re-enrich from external sources'
                      : 'Enrich from external sources'}
                  </>
                )}
              </button>

              {/* Quota Exhausted Message */}
              {enrichmentQuota && !enrichmentQuota.can_enrich && enrichmentQuota.reason && (
                <div className="mt-2 text-sm text-coral text-center">
                  {enrichmentQuota.reason}
                </div>
              )}
            </div>
          )}

          {/* Known Facts Section */}
          <div className="card-neo p-4">
            <h3 className="font-heading font-bold text-lg mb-3">Known Facts</h3>
            {(() => {
              // Filter out service predicates (starting with "_")
              const visibleAssertions = assertions.filter(a => !a.predicate.startsWith('_'));
              return visibleAssertions.length === 0 ? (
                <p className="text-[var(--text-muted)] text-sm italic">No data</p>
              ) : (
                <ul className="space-y-2">
                  {visibleAssertions.map((a) => {
                    const { label, icon } = formatPredicate(a.predicate);
                    return (
                      <li
                        key={a.assertion_id}
                        className="flex items-start gap-3 p-2 bg-[var(--bg-secondary)] border-2 border-black"
                      >
                        <span className={getPredicateBadgeClass(a.predicate)}>
                          {icon}
                          {label}
                        </span>
                        <span className="flex-1 text-sm">{a.object_value}</span>
                      </li>
                    );
                  })}
                </ul>
              );
            })()}
          </div>

          {/* Danger Zone - Delete button at the bottom */}
          {isOwnPerson && (
            <div className="card-neo p-4 border-coral">
              <button
                className="btn-neo btn-neo-danger w-full flex items-center justify-center gap-2"
                onClick={() => setShowDeleteConfirm(true)}
                disabled={deleting}
              >
                <TrashIcon size={18} />
                Delete Contact
              </button>
            </div>
          )}
        </main>

        {/* Delete Confirmation Modal */}
        {showDeleteConfirm && (
          <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
            onClick={() => setShowDeleteConfirm(false)}
          >
            <div
              className="card-neo p-6 max-w-sm w-full bg-[var(--bg-card)]"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-coral rounded-full">
                  <TrashIcon size={24} className="text-white" />
                </div>
                <h3 className="font-heading font-bold text-xl">Delete Contact?</h3>
              </div>
              <p className="mb-2">
                Are you sure you want to delete <strong>{selectedPerson.display_name}</strong>?
              </p>
              <p className="text-sm text-[var(--text-muted)] mb-6">
                This will remove the person and all their facts.
              </p>
              <div className="flex gap-3">
                <button
                  className="btn-neo flex-1"
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={deleting}
                >
                  Cancel
                </button>
                <button
                  className="btn-neo btn-neo-danger flex-1 flex items-center justify-center gap-2"
                  onClick={handleDelete}
                  disabled={deleting}
                >
                  {deleting ? (
                    <>
                      <SpinnerIcon size={16} />
                      Deleting...
                    </>
                  ) : (
                    <>
                      <TrashIcon size={16} />
                      Delete
                    </>
                  )}
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
    <div className="min-h-screen bg-[var(--bg-primary)]">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-[var(--bg-primary)] border-b-3 border-black p-4">
        <h1 className="font-heading text-2xl font-bold">People</h1>
        <p className="text-sm text-[var(--text-muted)]">
          {ownPeople.length} own · {sharedPeople.length} shared
        </p>
      </header>

      <main className="p-4 pb-24 space-y-4">
        {/* Tabs */}
        <div className="flex gap-2">
          <button
            className={`btn-neo flex-1 ${activeTab === 'own' ? 'btn-neo-primary' : ''}`}
            onClick={() => setActiveTab('own')}
          >
            Mine ({ownPeople.length})
          </button>
          <button
            className={`btn-neo flex-1 ${activeTab === 'shared' ? 'btn-neo-primary' : ''}`}
            onClick={() => setActiveTab('shared')}
          >
            Shared ({sharedPeople.length})
          </button>
        </div>

        {/* Search */}
        <div className="relative">
          <SearchIcon
            size={20}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          />
          <input
            type="text"
            placeholder="Search by name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input-neo pl-10"
          />
        </div>

        {/* People List */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <SpinnerIcon size={32} className="text-[var(--accent-primary)]" />
          </div>
        ) : filteredPeople.length === 0 ? (
          <div className="card-neo p-8 text-center">
            <UserIcon size={48} className="mx-auto mb-4 text-[var(--text-muted)]" />
            <p className="text-[var(--text-muted)]">
              {searchQuery
                ? 'No one found'
                : activeTab === 'own'
                  ? 'No people yet. Add a note!'
                  : 'No shared contacts from other users'}
            </p>
          </div>
        ) : (
          <ul className="space-y-2">
            {filteredPeople.map((person) => {
              const isOwn = person.owner_id === currentUserId;
              return (
                <li
                  key={person.person_id}
                  className="card-neo-interactive flex items-center gap-3"
                  onClick={() => handlePersonClick(person)}
                >
                  {/* Avatar */}
                  <div className={`
                    w-12 h-12 flex-shrink-0 flex items-center justify-center
                    text-xl font-bold border-2 border-black
                    ${isOwn ? 'bg-mint' : 'bg-lavender'}
                  `}>
                    {person.display_name.charAt(0).toUpperCase()}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold truncate">{person.display_name}</span>
                      {!isOwn && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs font-semibold bg-lavender border border-black">
                          <RobotIcon size={10} />
                        </span>
                      )}
                    </div>
                    {person.summary && (
                      <p className="text-sm text-[var(--text-muted)] truncate">
                        {person.summary.slice(0, 60)}...
                      </p>
                    )}
                  </div>

                  {/* Chevron */}
                  <ChevronRightIcon size={20} className="flex-shrink-0 text-[var(--text-muted)]" />
                </li>
              );
            })}
          </ul>
        )}
      </main>
    </div>
  );
};
