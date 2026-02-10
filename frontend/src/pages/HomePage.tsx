import { useState, useRef } from 'react';
import { useAuth } from '../hooks/useAuth';
import { api } from '../lib/api';
import { openExternalLink } from '../lib/telegram';

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
  analytics: CalendarAnalytics;
  dedup_result: DedupResult | null;
}

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
      const result = await api.importLinkedIn(linkedInFile, true);
      setLinkedInResult(result);
      setLinkedInPreview(null);
      setLinkedInFile(null);
      if (linkedInFileRef.current) {
        linkedInFileRef.current.value = '';
      }
    } catch (err) {
      setLinkedInError(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setLinkedInLoading(false);
    }
  };

  const handleLinkedInReset = () => {
    setLinkedInFile(null);
    setLinkedInPreview(null);
    setLinkedInResult(null);
    setLinkedInError(null);
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

              {!linkedInPreview && !linkedInResult && (
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
                    <button onClick={handleLinkedInReset} className="cancel-btn">
                      Cancel
                    </button>
                  </div>
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
                    <button onClick={handleCalendarReset} className="cancel-btn">
                      Cancel
                    </button>
                  </div>
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
