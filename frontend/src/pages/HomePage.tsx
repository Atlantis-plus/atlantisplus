import { useState, useRef, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { api } from '../lib/api';
import { openExternalLink } from '../lib/telegram';
import { supabase } from '../lib/supabase';

type Page = 'home' | 'notes' | 'search' | 'people' | 'chat';

interface HomePageProps {
  onNavigate?: (page: Page) => void;
}

// LinkedIn types
interface LinkedInContact {
  first_name: string;
  last_name: string;
  email: string | null;
  company: string | null;
  position: string | null;
  connected_on: string | null;
}

interface LinkedInPreview {
  total_contacts: number;
  with_email: number;
  without_email: number;
  sample: LinkedInContact[];
}

interface LinkedInAnalytics {
  by_year: Record<string, number>;
  by_company: Record<string, number>;
  with_email: number;
  without_email: number;
  total: number;
}

interface DedupResult {
  checked?: number;
  duplicates_found?: number;
  error?: string;
}

interface LinkedInResult {
  imported: number;
  skipped: number;
  duplicates_found: number;
  updated: number;
  batch_id: string;
  evidence_id: string;
  analytics: LinkedInAnalytics;
  dedup_result: DedupResult | null;
}

// Calendar types
interface CalendarAttendee {
  email: string;
  name: string | null;
  meeting_count: number;
}

interface CalendarEvent {
  summary: string;
  date: string;
  attendee_count: number;
  attendees: string[];
}

interface CalendarPreview {
  total_events: number;
  events_with_attendees: number;
  unique_attendees: number;
  date_range: string;
  top_attendees: CalendarAttendee[];
  sample_events: CalendarEvent[];
}

interface CalendarAnalytics {
  by_frequency: Record<string, number>;
  date_range: string;
  top_domains: Record<string, number>;
  top_attendees: Array<{ email: string; name: string | null; meetings: number }>;
  total_events: number;
  total_people: number;
}

interface CalendarResult {
  imported_people: number;
  imported_meetings: number;
  skipped_duplicates: number;
  updated_existing: number;
  batch_id: string;
  evidence_id: string;
  analytics: CalendarAnalytics;
  dedup_result: DedupResult | null;
}

// Progress tracking
type ProcessingStatus = 'pending' | 'extracting' | 'done' | 'error';

interface ImportProgress {
  evidenceId: string | null;
  batchId: string | null;
  totalContacts: number;
  status: ProcessingStatus;
  content: string | null;  // Progress message from backend
  error: string | null;
}

// LocalStorage keys
const LINKEDIN_IMPORT_KEY = 'atlantis_linkedin_import';
const CALENDAR_IMPORT_KEY = 'atlantis_calendar_import';

export const HomePage = ({ onNavigate }: HomePageProps) => {
  const { displayName, isAuthenticated, loading, error } = useAuth();

  // LinkedIn state
  const linkedInFileRef = useRef<HTMLInputElement>(null);
  const [linkedInFile, setLinkedInFile] = useState<File | null>(null);
  const [linkedInPreview, setLinkedInPreview] = useState<LinkedInPreview | null>(null);
  const [linkedInResult, setLinkedInResult] = useState<LinkedInResult | null>(null);
  const [linkedInLoading, setLinkedInLoading] = useState(false);
  const [linkedInError, setLinkedInError] = useState<string | null>(null);

  // Calendar state
  const calendarFileRef = useRef<HTMLInputElement>(null);
  const [calendarFile, setCalendarFile] = useState<File | null>(null);
  const [calendarPreview, setCalendarPreview] = useState<CalendarPreview | null>(null);
  const [calendarResult, setCalendarResult] = useState<CalendarResult | null>(null);
  const [calendarLoading, setCalendarLoading] = useState(false);
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [ownerEmail, setOwnerEmail] = useState<string>('');

  // Progress state for real-time updates
  const [linkedInProgress, setLinkedInProgress] = useState<ImportProgress>({
    evidenceId: null,
    batchId: null,
    totalContacts: 0,
    status: 'pending',
    content: null,
    error: null
  });
  const [calendarProgress, setCalendarProgress] = useState<ImportProgress>({
    evidenceId: null,
    batchId: null,
    totalContacts: 0,
    status: 'pending',
    content: null,
    error: null
  });

  // Restore active import from localStorage on mount
  useEffect(() => {
    const restoreActiveImport = async () => {
      const savedLinkedIn = localStorage.getItem(LINKEDIN_IMPORT_KEY);
      if (savedLinkedIn) {
        try {
          const saved = JSON.parse(savedLinkedIn);
          // Check current status in DB
          const { data } = await supabase
            .from('raw_evidence')
            .select('processing_status, content, error_message')
            .eq('evidence_id', saved.evidenceId)
            .single();

          if (data) {
            if (data.processing_status === 'done' || data.processing_status === 'error') {
              // Import finished, clear localStorage
              localStorage.removeItem(LINKEDIN_IMPORT_KEY);
              if (data.processing_status === 'done') {
                // Could show a "completed" message
              }
            } else {
              // Import still in progress, restore state
              setLinkedInProgress({
                evidenceId: saved.evidenceId,
                batchId: saved.batchId,
                totalContacts: saved.totalContacts,
                status: data.processing_status,
                content: data.content,
                error: data.error_message
              });
              setLinkedInLoading(true);
            }
          }
        } catch (e) {
          localStorage.removeItem(LINKEDIN_IMPORT_KEY);
        }
      }

      const savedCalendar = localStorage.getItem(CALENDAR_IMPORT_KEY);
      if (savedCalendar) {
        try {
          const saved = JSON.parse(savedCalendar);
          const { data } = await supabase
            .from('raw_evidence')
            .select('processing_status, content, error_message')
            .eq('evidence_id', saved.evidenceId)
            .single();

          if (data) {
            if (data.processing_status === 'done' || data.processing_status === 'error') {
              localStorage.removeItem(CALENDAR_IMPORT_KEY);
            } else {
              setCalendarProgress({
                evidenceId: saved.evidenceId,
                batchId: saved.batchId,
                totalContacts: saved.totalContacts,
                status: data.processing_status,
                content: data.content,
                error: data.error_message
              });
              setCalendarLoading(true);
            }
          }
        } catch (e) {
          localStorage.removeItem(CALENDAR_IMPORT_KEY);
        }
      }
    };

    if (isAuthenticated) {
      restoreActiveImport();
    }
  }, [isAuthenticated]);

  // Subscribe to real-time progress updates
  useEffect(() => {
    if (!linkedInProgress.evidenceId && !calendarProgress.evidenceId) return;

    const evidenceIds = [linkedInProgress.evidenceId, calendarProgress.evidenceId].filter(Boolean);
    if (evidenceIds.length === 0) return;

    const channel = supabase
      .channel('import-progress')
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'raw_evidence',
          filter: `evidence_id=in.(${evidenceIds.join(',')})`
        },
        (payload) => {
          const { evidence_id, processing_status, content, error_message } = payload.new as {
            evidence_id: string;
            processing_status: ProcessingStatus;
            content: string;
            error_message: string | null;
          };

          if (evidence_id === linkedInProgress.evidenceId) {
            setLinkedInProgress(prev => ({
              ...prev,
              status: processing_status,
              content: content,
              error: error_message
            }));

            // If done or error, clear localStorage and loading
            if (processing_status === 'done' || processing_status === 'error') {
              localStorage.removeItem(LINKEDIN_IMPORT_KEY);
              setLinkedInLoading(false);
              if (processing_status === 'done') {
                // Parse result from content if available
                setLinkedInResult({
                  imported: 0, // Will be updated from content parsing
                  skipped: 0,
                  duplicates_found: 0,
                  updated: 0,
                  batch_id: linkedInProgress.batchId || '',
                  evidence_id: evidence_id,
                  analytics: { by_year: {}, by_company: {}, with_email: 0, without_email: 0, total: linkedInProgress.totalContacts },
                  dedup_result: null
                });
              }
            }
          }
          if (evidence_id === calendarProgress.evidenceId) {
            setCalendarProgress(prev => ({
              ...prev,
              status: processing_status,
              content: content,
              error: error_message
            }));

            if (processing_status === 'done' || processing_status === 'error') {
              localStorage.removeItem(CALENDAR_IMPORT_KEY);
              setCalendarLoading(false);
            }
          }
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [linkedInProgress.evidenceId, calendarProgress.evidenceId]);

  // LinkedIn handlers
  const handleLinkedInFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setLinkedInFile(file);
    setLinkedInPreview(null);
    setLinkedInResult(null);
    setLinkedInError(null);
    setLinkedInLoading(true);

    try {
      const previewData = await api.previewLinkedInImport(file);
      setLinkedInPreview(previewData);
    } catch (err) {
      setLinkedInError(err instanceof Error ? err.message : 'Failed to preview file');
    } finally {
      setLinkedInLoading(false);
    }
  };

  const handleLinkedInImport = async () => {
    if (!linkedInFile) return;

    setLinkedInLoading(true);
    setLinkedInError(null);

    try {
      // API now returns 202 immediately with tracking info
      const startResult = await api.importLinkedIn(linkedInFile, true);

      // Save to localStorage for recovery after reload
      localStorage.setItem(LINKEDIN_IMPORT_KEY, JSON.stringify({
        evidenceId: startResult.evidence_id,
        batchId: startResult.batch_id,
        totalContacts: startResult.total_contacts
      }));

      // Set progress state to enable Realtime subscription
      setLinkedInProgress({
        evidenceId: startResult.evidence_id,
        batchId: startResult.batch_id,
        totalContacts: startResult.total_contacts,
        status: 'pending',
        content: startResult.message,
        error: null
      });

      // Clear file selection (but keep loading until done via Realtime)
      setLinkedInPreview(null);
      setLinkedInFile(null);
      if (linkedInFileRef.current) {
        linkedInFileRef.current.value = '';
      }

      // Note: setLinkedInLoading(false) will be called by Realtime when status='done'
    } catch (err) {
      setLinkedInError(err instanceof Error ? err.message : 'Import failed');
      setLinkedInLoading(false);
    }
  };

  const handleLinkedInReset = () => {
    setLinkedInFile(null);
    setLinkedInPreview(null);
    setLinkedInResult(null);
    setLinkedInError(null);
    setLinkedInLoading(false);
    setLinkedInProgress({
      evidenceId: null,
      batchId: null,
      totalContacts: 0,
      status: 'pending',
      content: null,
      error: null
    });
    localStorage.removeItem(LINKEDIN_IMPORT_KEY);
    if (linkedInFileRef.current) {
      linkedInFileRef.current.value = '';
    }
  };

  // Calendar handlers
  const handleCalendarFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setCalendarFile(file);
    setCalendarPreview(null);
    setCalendarResult(null);
    setCalendarError(null);
    setCalendarLoading(true);

    try {
      const previewData = await api.previewCalendarImport(file, ownerEmail || undefined);
      setCalendarPreview(previewData);
    } catch (err) {
      setCalendarError(err instanceof Error ? err.message : 'Failed to preview file');
    } finally {
      setCalendarLoading(false);
    }
  };

  const handleCalendarImport = async () => {
    if (!calendarFile) return;

    setCalendarLoading(true);
    setCalendarError(null);

    try {
      const result = await api.importCalendar(calendarFile, ownerEmail || undefined);
      setCalendarResult(result);
      setCalendarPreview(null);
      setCalendarFile(null);
      if (calendarFileRef.current) {
        calendarFileRef.current.value = '';
      }
    } catch (err) {
      setCalendarError(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setCalendarLoading(false);
    }
  };

  const handleCalendarReset = () => {
    setCalendarFile(null);
    setCalendarPreview(null);
    setCalendarResult(null);
    setCalendarError(null);
    if (calendarFileRef.current) {
      calendarFileRef.current.value = '';
    }
  };

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
          <>
            <div className="welcome">
              <p>Welcome, <strong>{displayName}</strong>!</p>
            </div>

            {/* LinkedIn Import Section */}
            <div className="import-section">
              <h2>LinkedIn Contacts</h2>

              <div className="import-instructions">
                <p>To export your LinkedIn connections:</p>
                <ol>
                  <li>
                    <a
                      href="#"
                      onClick={(e) => {
                        e.preventDefault();
                        openExternalLink('https://www.linkedin.com/mypreferences/d/download-my-data');
                      }}
                      className="external-link"
                    >
                      Open LinkedIn Settings
                    </a>
                  </li>
                  <li>Click "Get a copy of your data"</li>
                  <li>Select "Connections"</li>
                  <li>Download and upload here</li>
                </ol>
              </div>

              {/* Show progress when background import is running */}
              {linkedInProgress.evidenceId && linkedInLoading && (
                <div className="progress-section">
                  <h3>Import in Progress</h3>
                  <div className="progress-stats">
                    <span>{linkedInProgress.totalContacts} contacts</span>
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill progress-animated"></div>
                  </div>
                  <div className="progress-status">
                    {linkedInProgress.content || 'Processing...'}
                  </div>
                  <p className="progress-hint">
                    You can close this page. Import continues in background.
                  </p>
                  {linkedInProgress.error && (
                    <div className="error-message">{linkedInProgress.error}</div>
                  )}
                </div>
              )}

              {!linkedInPreview && !linkedInResult && !linkedInProgress.evidenceId && (
                <div className="file-upload">
                  <input
                    ref={linkedInFileRef}
                    type="file"
                    accept=".csv"
                    onChange={handleLinkedInFileSelect}
                    disabled={linkedInLoading}
                    id="linkedin-upload"
                    style={{ display: 'none' }}
                  />
                  <label htmlFor="linkedin-upload" className="upload-btn">
                    {linkedInLoading ? 'Loading...' : 'Upload CSV File'}
                  </label>
                </div>
              )}

              {linkedInError && (
                <div className="error-message">
                  {linkedInError}
                  <button onClick={handleLinkedInReset} className="retry-btn">Try Again</button>
                </div>
              )}

              {linkedInPreview && (
                <div className="preview-section">
                  <h3>Preview</h3>
                  <div className="preview-stats">
                    <div className="stat">
                      <span className="stat-value">{linkedInPreview.total_contacts}</span>
                      <span className="stat-label">Total Contacts</span>
                    </div>
                    <div className="stat">
                      <span className="stat-value">{linkedInPreview.with_email}</span>
                      <span className="stat-label">With Email</span>
                    </div>
                    <div className="stat">
                      <span className="stat-value">{linkedInPreview.without_email}</span>
                      <span className="stat-label">Without Email</span>
                    </div>
                  </div>

                  <div className="preview-sample">
                    <h4>Sample Contacts:</h4>
                    <ul>
                      {linkedInPreview.sample.map((contact, i) => (
                        <li key={i}>
                          <strong>{contact.first_name} {contact.last_name}</strong>
                          {contact.company && <span> - {contact.company}</span>}
                          {contact.position && <span> ({contact.position})</span>}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="preview-actions">
                    <button
                      onClick={handleLinkedInImport}
                      className="import-btn"
                      disabled={linkedInLoading}
                    >
                      {linkedInLoading ? 'Importing...' : `Import ${linkedInPreview.total_contacts} Contacts`}
                    </button>
                    <button onClick={handleLinkedInReset} className="cancel-btn" disabled={linkedInLoading}>
                      Cancel
                    </button>
                  </div>

                  {linkedInLoading && (
                    <div className="progress-section">
                      <div className="progress-bar">
                        <div className="progress-fill progress-animated"></div>
                      </div>
                      <div className="progress-status">
                        {linkedInProgress.content || 'Starting import...'}
                      </div>
                      <p className="progress-hint">
                        You can close this page. Import continues in background.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {linkedInResult && (
                <div className="import-result">
                  <h3>Import Complete!</h3>
                  <div className="result-stats">
                    <div className="stat success">
                      <span className="stat-value">{linkedInResult.imported}</span>
                      <span className="stat-label">Imported</span>
                    </div>
                    {linkedInResult.updated > 0 && (
                      <div className="stat">
                        <span className="stat-value">{linkedInResult.updated}</span>
                        <span className="stat-label">Updated</span>
                      </div>
                    )}
                    {linkedInResult.duplicates_found > 0 && (
                      <div className="stat warning">
                        <span className="stat-value">{linkedInResult.duplicates_found}</span>
                        <span className="stat-label">Skipped</span>
                      </div>
                    )}
                  </div>

                  {/* Analytics */}
                  {linkedInResult.analytics && (
                    <div className="analytics-section">
                      {Object.keys(linkedInResult.analytics.by_year || {}).length > 0 && (
                        <div className="analytics-block">
                          <h4>By Year</h4>
                          <div className="analytics-list">
                            {Object.entries(linkedInResult.analytics.by_year)
                              .slice(0, 5)
                              .map(([year, count]) => (
                                <span key={year} className="analytics-item">
                                  {year}: {count}
                                </span>
                              ))}
                          </div>
                        </div>
                      )}
                      {Object.keys(linkedInResult.analytics.by_company || {}).length > 0 && (
                        <div className="analytics-block">
                          <h4>Top Companies</h4>
                          <div className="analytics-list">
                            {Object.entries(linkedInResult.analytics.by_company)
                              .slice(0, 5)
                              .map(([company, count]) => (
                                <span key={company} className="analytics-item">
                                  {company} ({count})
                                </span>
                              ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Dedup Result */}
                  {linkedInResult.dedup_result && linkedInResult.dedup_result.duplicates_found !== undefined && linkedInResult.dedup_result.duplicates_found > 0 && (
                    <div className="dedup-notice">
                      Found {linkedInResult.dedup_result.duplicates_found} potential duplicates with existing contacts
                    </div>
                  )}

                  <div className="result-actions">
                    <button
                      onClick={() => onNavigate?.('people')}
                      className="view-btn"
                    >
                      View Contacts
                    </button>
                    <button onClick={handleLinkedInReset} className="another-btn">
                      Import More
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Calendar Import Section */}
            <div className="import-section">
              <h2>Google Calendar</h2>

              <div className="import-instructions">
                <p>To export your Google Calendar:</p>
                <ol>
                  <li>
                    <a
                      href="#"
                      onClick={(e) => {
                        e.preventDefault();
                        openExternalLink('https://calendar.google.com/calendar/r/settings/export');
                      }}
                      className="external-link"
                    >
                      Open Google Calendar Export
                    </a>
                  </li>
                  <li>Click "Export" to download ZIP</li>
                  <li>Extract the .ics file</li>
                  <li>Upload here</li>
                </ol>
              </div>

              {!calendarPreview && !calendarResult && (
                <div className="file-upload">
                  <div className="owner-email-input">
                    <input
                      type="email"
                      placeholder="Your email (to exclude from attendees)"
                      value={ownerEmail}
                      onChange={(e) => setOwnerEmail(e.target.value)}
                      className="email-input"
                    />
                  </div>
                  <input
                    ref={calendarFileRef}
                    type="file"
                    accept=".ics"
                    onChange={handleCalendarFileSelect}
                    disabled={calendarLoading}
                    id="calendar-upload"
                    style={{ display: 'none' }}
                  />
                  <label htmlFor="calendar-upload" className="upload-btn">
                    {calendarLoading ? 'Loading...' : 'Upload ICS File'}
                  </label>
                </div>
              )}

              {calendarError && (
                <div className="error-message">
                  {calendarError}
                  <button onClick={handleCalendarReset} className="retry-btn">Try Again</button>
                </div>
              )}

              {calendarPreview && (
                <div className="preview-section">
                  <h3>Preview</h3>
                  <div className="preview-stats">
                    <div className="stat">
                      <span className="stat-value">{calendarPreview.events_with_attendees}</span>
                      <span className="stat-label">Meetings</span>
                    </div>
                    <div className="stat">
                      <span className="stat-value">{calendarPreview.unique_attendees}</span>
                      <span className="stat-label">People</span>
                    </div>
                  </div>
                  <p className="date-range">Date range: {calendarPreview.date_range}</p>

                  <div className="preview-sample">
                    <h4>Top Attendees:</h4>
                    <ul>
                      {calendarPreview.top_attendees.slice(0, 5).map((attendee, i) => (
                        <li key={i}>
                          <strong>{attendee.name || attendee.email}</strong>
                          <span className="meeting-count"> ({attendee.meeting_count} meetings)</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="preview-sample">
                    <h4>Sample Events:</h4>
                    <ul>
                      {calendarPreview.sample_events.map((event, i) => (
                        <li key={i}>
                          <strong>{event.summary}</strong>
                          <span className="event-date"> - {event.date}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="preview-actions">
                    <button
                      onClick={handleCalendarImport}
                      className="import-btn"
                      disabled={calendarLoading}
                    >
                      {calendarLoading ? 'Importing...' : `Import ${calendarPreview.unique_attendees} People`}
                    </button>
                    <button onClick={handleCalendarReset} className="cancel-btn" disabled={calendarLoading}>
                      Cancel
                    </button>
                  </div>

                  {calendarLoading && (
                    <div className="progress-section">
                      <div className="progress-bar">
                        <div className="progress-fill progress-animated"></div>
                      </div>
                      <div className="progress-steps">
                        <span className="step active">Uploading</span>
                        <span className="step">Processing calendar</span>
                        <span className="step">Creating contacts</span>
                        <span className="step">Finding duplicates</span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {calendarResult && (
                <div className="import-result">
                  <h3>Import Complete!</h3>
                  <div className="result-stats">
                    <div className="stat success">
                      <span className="stat-value">{calendarResult.imported_people}</span>
                      <span className="stat-label">New People</span>
                    </div>
                    <div className="stat">
                      <span className="stat-value">{calendarResult.updated_existing}</span>
                      <span className="stat-label">Updated</span>
                    </div>
                    <div className="stat">
                      <span className="stat-value">{calendarResult.imported_meetings}</span>
                      <span className="stat-label">Meetings</span>
                    </div>
                  </div>

                  {/* Analytics */}
                  {calendarResult.analytics && (
                    <div className="analytics-section">
                      <p className="date-range">Period: {calendarResult.analytics.date_range}</p>

                      {calendarResult.analytics.by_frequency && (
                        <div className="analytics-block">
                          <h4>By Meeting Frequency</h4>
                          <div className="analytics-list">
                            {Object.entries(calendarResult.analytics.by_frequency).map(([freq, count]) => (
                              <span key={freq} className="analytics-item">
                                {freq} meetings: {count} people
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {Object.keys(calendarResult.analytics.top_domains || {}).length > 0 && (
                        <div className="analytics-block">
                          <h4>Top Domains</h4>
                          <div className="analytics-list">
                            {Object.entries(calendarResult.analytics.top_domains)
                              .slice(0, 5)
                              .map(([domain, count]) => (
                                <span key={domain} className="analytics-item">
                                  {domain} ({count})
                                </span>
                              ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Dedup Result */}
                  {calendarResult.dedup_result && calendarResult.dedup_result.duplicates_found !== undefined && calendarResult.dedup_result.duplicates_found > 0 && (
                    <div className="dedup-notice">
                      Found {calendarResult.dedup_result.duplicates_found} potential duplicates with existing contacts
                    </div>
                  )}

                  <div className="result-actions">
                    <button
                      onClick={() => onNavigate?.('people')}
                      className="view-btn"
                    >
                      View Contacts
                    </button>
                    <button onClick={handleCalendarReset} className="another-btn">
                      Import More
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="dev-mode">
            <p>Development mode</p>
            <p className="hint">Open in Telegram Mini App for full functionality</p>
          </div>
        )}
      </main>
    </div>
  );
};
