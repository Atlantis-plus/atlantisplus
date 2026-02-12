import { useState, useRef, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { api } from '../lib/api';
import { openExternalLink } from '../lib/telegram';
import { supabase } from '../lib/supabase';
import {
  UploadIcon,
  LinkedInIcon,
  CalendarIcon,
  CheckCircleIcon,
  ErrorCircleIcon,
  SpinnerIcon,
  RefreshIcon,
  InfoIcon,
  XIcon,
  ExternalLinkIcon,
  PeopleIcon
} from '../components/icons';

type Page = 'people' | 'notes' | 'chat' | 'import';

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
  content: string | null;
  error: string | null;
}

// LocalStorage keys
const LINKEDIN_IMPORT_KEY = 'atlantis_linkedin_import';
const CALENDAR_IMPORT_KEY = 'atlantis_calendar_import';

// Import tab type
type ImportTab = 'linkedin' | 'calendar';

export const HomePage = ({ onNavigate }: HomePageProps) => {
  const { displayName, isAuthenticated, loading, error } = useAuth();

  // Active tab
  const [activeTab, setActiveTab] = useState<ImportTab>('linkedin');

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
          const { data } = await supabase
            .from('raw_evidence')
            .select('processing_status, content, error_message')
            .eq('evidence_id', saved.evidenceId)
            .single();

          if (data) {
            if (data.processing_status === 'done' || data.processing_status === 'error') {
              localStorage.removeItem(LINKEDIN_IMPORT_KEY);
            } else {
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

            if (processing_status === 'done' || processing_status === 'error') {
              localStorage.removeItem(LINKEDIN_IMPORT_KEY);
              setLinkedInLoading(false);
              if (processing_status === 'done') {
                setLinkedInResult({
                  imported: 0,
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
      const startResult = await api.importLinkedIn(linkedInFile, true);

      localStorage.setItem(LINKEDIN_IMPORT_KEY, JSON.stringify({
        evidenceId: startResult.evidence_id,
        batchId: startResult.batch_id,
        totalContacts: startResult.total_contacts
      }));

      setLinkedInProgress({
        evidenceId: startResult.evidence_id,
        batchId: startResult.batch_id,
        totalContacts: startResult.total_contacts,
        status: 'pending',
        content: startResult.message,
        error: null
      });

      setLinkedInPreview(null);
      setLinkedInFile(null);
      if (linkedInFileRef.current) {
        linkedInFileRef.current.value = '';
      }
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
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div className="card-neo p-8 flex flex-col items-center gap-4">
          <SpinnerIcon size={32} className="text-primary" />
          <span className="font-heading text-lg" style={{ color: 'var(--text-primary)' }}>Loading...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div className="card-neo p-6 max-w-md" style={{ backgroundColor: 'var(--accent-danger)' }}>
          <div className="flex items-center gap-3 mb-3">
            <ErrorCircleIcon size={24} className="text-white" />
            <h2 className="font-heading text-xl text-white">Error</h2>
          </div>
          <p className="text-white">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen p-4" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Header */}
      <header className="mb-6">
        <h1 className="font-heading text-2xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>
          Import Contacts
        </h1>
        <p style={{ color: 'var(--text-secondary)' }}>Build your network from existing connections</p>
      </header>

      {isAuthenticated ? (
        <main className="space-y-6">
          {/* Welcome message */}
          <div className="card-neo p-4" style={{ backgroundColor: 'var(--accent-warning)' }}>
            <p className="font-body" style={{ color: 'var(--text-primary)' }}>
              Welcome, <strong className="font-heading">{displayName}</strong>!
            </p>
          </div>

          {/* Tab navigation */}
          <div className="flex gap-3">
            <button
              onClick={() => setActiveTab('linkedin')}
              className={`btn-neo flex items-center gap-2 ${activeTab === 'linkedin' ? 'btn-neo-primary' : ''}`}
            >
              <LinkedInIcon size={18} />
              LinkedIn
            </button>
            <button
              onClick={() => setActiveTab('calendar')}
              className={`btn-neo flex items-center gap-2 ${activeTab === 'calendar' ? 'btn-neo-primary' : ''}`}
            >
              <CalendarIcon size={18} />
              Calendar
            </button>
          </div>

          {/* LinkedIn Tab Content */}
          {activeTab === 'linkedin' && (
            <div className="card-neo p-5">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 border-3 border-black" style={{ backgroundColor: 'var(--accent-primary)' }}>
                  <LinkedInIcon size={20} className="text-white" />
                </div>
                <h2 className="font-heading text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
                  LinkedIn Contacts
                </h2>
              </div>

              {/* Instructions */}
              <div className="card-neo p-4 mb-5" style={{ backgroundColor: 'var(--bg-secondary)', borderStyle: 'dashed' }}>
                <div className="flex items-start gap-2 mb-2">
                  <InfoIcon size={18} style={{ color: 'var(--text-secondary)', flexShrink: 0, marginTop: '2px' }} />
                  <p className="font-body text-sm" style={{ color: 'var(--text-secondary)' }}>
                    To export your LinkedIn connections:
                  </p>
                </div>
                <ol className="list-decimal list-inside space-y-1 text-sm pl-6" style={{ color: 'var(--text-secondary)' }}>
                  <li>
                    <a
                      href="#"
                      onClick={(e) => {
                        e.preventDefault();
                        openExternalLink('https://www.linkedin.com/mypreferences/d/download-my-data');
                      }}
                      className="inline-flex items-center gap-1 font-semibold"
                      style={{ color: 'var(--accent-primary)' }}
                    >
                      Open LinkedIn Settings
                      <ExternalLinkIcon size={14} />
                    </a>
                  </li>
                  <li>Click "Get a copy of your data"</li>
                  <li>Select "Connections"</li>
                  <li>Download and upload here</li>
                </ol>
              </div>

              {/* Progress indicator for background import */}
              {linkedInProgress.evidenceId && linkedInLoading && (
                <div className="card-neo p-5 mb-5" style={{ backgroundColor: 'var(--accent-warning)' }}>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-heading font-bold" style={{ color: 'var(--text-primary)' }}>
                      Import in Progress
                    </h3>
                    <span className="badge-neo">
                      {linkedInProgress.totalContacts} contacts
                    </span>
                  </div>

                  {/* Progress bar */}
                  <div className="h-4 border-3 border-black bg-white mb-3 overflow-hidden">
                    <div
                      className="h-full animate-pulse"
                      style={{
                        backgroundColor: 'var(--accent-primary)',
                        width: '100%',
                        animation: 'neo-pulse 1.5s ease-in-out infinite'
                      }}
                    />
                  </div>

                  <div className="flex items-center gap-2 mb-2">
                    <SpinnerIcon size={16} />
                    <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      {linkedInProgress.content || 'Processing...'}
                    </span>
                  </div>

                  <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    You can close this page. Import continues in background.
                  </p>

                  {linkedInProgress.error && (
                    <div className="mt-3 p-3 border-3 border-black flex items-center gap-2" style={{ backgroundColor: 'var(--accent-danger)' }}>
                      <ErrorCircleIcon size={16} className="text-white flex-shrink-0" />
                      <span className="text-white text-sm">{linkedInProgress.error}</span>
                    </div>
                  )}
                </div>
              )}

              {/* File upload area */}
              {!linkedInPreview && !linkedInResult && !linkedInProgress.evidenceId && (
                <div className="mb-5">
                  <input
                    ref={linkedInFileRef}
                    type="file"
                    accept=".csv"
                    onChange={handleLinkedInFileSelect}
                    disabled={linkedInLoading}
                    id="linkedin-upload"
                    className="hidden"
                  />
                  <label
                    htmlFor="linkedin-upload"
                    className={`card-neo p-8 flex flex-col items-center gap-3 cursor-pointer transition-all ${
                      linkedInLoading ? 'opacity-50 cursor-not-allowed' : 'hover:translate-x-[-2px] hover:translate-y-[-2px] hover:shadow-[6px_6px_0_var(--shadow-color)]'
                    }`}
                    style={{ borderStyle: 'dashed', backgroundColor: 'var(--bg-card)' }}
                  >
                    {linkedInLoading ? (
                      <SpinnerIcon size={32} style={{ color: 'var(--text-muted)' }} />
                    ) : (
                      <UploadIcon size={32} style={{ color: 'var(--text-muted)' }} />
                    )}
                    <span className="font-heading font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {linkedInLoading ? 'Loading...' : 'Upload CSV File'}
                    </span>
                    <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
                      Click to select or drag and drop
                    </span>
                  </label>
                </div>
              )}

              {/* Error message */}
              {linkedInError && (
                <div className="card-neo p-4 mb-5 flex items-center justify-between" style={{ backgroundColor: 'var(--accent-danger)' }}>
                  <div className="flex items-center gap-2">
                    <ErrorCircleIcon size={18} className="text-white flex-shrink-0" />
                    <span className="text-white text-sm">{linkedInError}</span>
                  </div>
                  <button
                    onClick={handleLinkedInReset}
                    className="btn-neo btn-neo-danger flex items-center gap-1 py-1 px-3 text-sm"
                  >
                    <RefreshIcon size={14} />
                    Try Again
                  </button>
                </div>
              )}

              {/* Preview section */}
              {linkedInPreview && (
                <div className="space-y-5">
                  <h3 className="font-heading text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                    Preview
                  </h3>

                  {/* Stats cards */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="card-neo p-4 text-center" style={{ backgroundColor: 'var(--accent-primary)' }}>
                      <div className="font-heading text-2xl font-bold text-white">
                        {linkedInPreview.total_contacts}
                      </div>
                      <div className="text-xs text-white opacity-80 uppercase tracking-wide">
                        Total
                      </div>
                    </div>
                    <div className="card-neo p-4 text-center" style={{ backgroundColor: 'var(--accent-success)' }}>
                      <div className="font-heading text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
                        {linkedInPreview.with_email}
                      </div>
                      <div className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-primary)', opacity: 0.7 }}>
                        With Email
                      </div>
                    </div>
                    <div className="card-neo p-4 text-center" style={{ backgroundColor: 'var(--bg-secondary)' }}>
                      <div className="font-heading text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
                        {linkedInPreview.without_email}
                      </div>
                      <div className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
                        No Email
                      </div>
                    </div>
                  </div>

                  {/* Sample contacts table */}
                  <div className="card-neo p-4" style={{ backgroundColor: 'var(--bg-card)' }}>
                    <h4 className="font-heading font-bold mb-3" style={{ color: 'var(--text-primary)' }}>
                      Sample Contacts
                    </h4>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm border-collapse">
                        <thead>
                          <tr>
                            <th className="text-left p-2 border-b-3 border-black font-heading" style={{ color: 'var(--text-primary)' }}>Name</th>
                            <th className="text-left p-2 border-b-3 border-black font-heading" style={{ color: 'var(--text-primary)' }}>Company</th>
                            <th className="text-left p-2 border-b-3 border-black font-heading" style={{ color: 'var(--text-primary)' }}>Position</th>
                          </tr>
                        </thead>
                        <tbody>
                          {linkedInPreview.sample.map((contact, i) => (
                            <tr key={i} className="border-b border-gray-200">
                              <td className="p-2 font-semibold" style={{ color: 'var(--text-primary)' }}>
                                {contact.first_name} {contact.last_name}
                              </td>
                              <td className="p-2" style={{ color: 'var(--text-secondary)' }}>
                                {contact.company || '-'}
                              </td>
                              <td className="p-2" style={{ color: 'var(--text-secondary)' }}>
                                {contact.position || '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="flex gap-3">
                    <button
                      onClick={handleLinkedInImport}
                      className="btn-neo btn-neo-primary flex-1 flex items-center justify-center gap-2"
                      disabled={linkedInLoading}
                    >
                      {linkedInLoading ? (
                        <>
                          <SpinnerIcon size={18} />
                          Importing...
                        </>
                      ) : (
                        <>
                          <UploadIcon size={18} />
                          Import {linkedInPreview.total_contacts} Contacts
                        </>
                      )}
                    </button>
                    <button
                      onClick={handleLinkedInReset}
                      className="btn-neo flex items-center gap-2"
                      disabled={linkedInLoading}
                    >
                      <XIcon size={18} />
                      Cancel
                    </button>
                  </div>

                  {/* Progress during import */}
                  {linkedInLoading && (
                    <div className="card-neo p-4" style={{ backgroundColor: 'var(--accent-warning)' }}>
                      <div className="h-3 border-2 border-black bg-white mb-2 overflow-hidden">
                        <div
                          className="h-full"
                          style={{
                            backgroundColor: 'var(--accent-primary)',
                            width: '100%',
                            animation: 'neo-pulse 1.5s ease-in-out infinite'
                          }}
                        />
                      </div>
                      <p className="text-sm flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
                        <SpinnerIcon size={14} />
                        {linkedInProgress.content || 'Starting import...'}
                      </p>
                      <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                        You can close this page. Import continues in background.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Import result */}
              {linkedInResult && (
                <div className="space-y-5">
                  {/* Success header */}
                  <div className="card-neo p-5" style={{ backgroundColor: 'var(--accent-success)' }}>
                    <div className="flex items-center gap-3">
                      <CheckCircleIcon size={28} />
                      <h3 className="font-heading text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
                        Import Complete!
                      </h3>
                    </div>
                  </div>

                  {/* Result stats */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="card-neo p-4 text-center" style={{ backgroundColor: 'var(--accent-success)' }}>
                      <div className="font-heading text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
                        {linkedInResult.imported}
                      </div>
                      <div className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-primary)' }}>
                        Imported
                      </div>
                    </div>
                    {linkedInResult.updated > 0 && (
                      <div className="card-neo p-4 text-center" style={{ backgroundColor: 'var(--accent-primary)' }}>
                        <div className="font-heading text-2xl font-bold text-white">
                          {linkedInResult.updated}
                        </div>
                        <div className="text-xs text-white uppercase tracking-wide opacity-80">
                          Updated
                        </div>
                      </div>
                    )}
                    {linkedInResult.duplicates_found > 0 && (
                      <div className="card-neo p-4 text-center" style={{ backgroundColor: 'var(--accent-warning)' }}>
                        <div className="font-heading text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
                          {linkedInResult.duplicates_found}
                        </div>
                        <div className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-primary)' }}>
                          Skipped
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Analytics */}
                  {linkedInResult.analytics && (
                    <div className="grid gap-4 md:grid-cols-2">
                      {Object.keys(linkedInResult.analytics.by_year || {}).length > 0 && (
                        <div className="card-neo p-4">
                          <h4 className="font-heading font-bold mb-3" style={{ color: 'var(--text-primary)' }}>
                            By Year
                          </h4>
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(linkedInResult.analytics.by_year)
                              .slice(0, 5)
                              .map(([year, count]) => (
                                <span key={year} className="badge-neo badge-neo-primary">
                                  {year}: {count}
                                </span>
                              ))}
                          </div>
                        </div>
                      )}
                      {Object.keys(linkedInResult.analytics.by_company || {}).length > 0 && (
                        <div className="card-neo p-4">
                          <h4 className="font-heading font-bold mb-3" style={{ color: 'var(--text-primary)' }}>
                            Top Companies
                          </h4>
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(linkedInResult.analytics.by_company)
                              .slice(0, 5)
                              .map(([company, count]) => (
                                <span key={company} className="badge-neo badge-neo-lavender">
                                  {company} ({count})
                                </span>
                              ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Dedup notice */}
                  {linkedInResult.dedup_result && linkedInResult.dedup_result.duplicates_found !== undefined && linkedInResult.dedup_result.duplicates_found > 0 && (
                    <div className="card-neo p-4 flex items-center gap-3" style={{ backgroundColor: 'var(--bg-secondary)' }}>
                      <RefreshIcon size={18} style={{ color: 'var(--text-secondary)' }} />
                      <span style={{ color: 'var(--text-secondary)' }}>
                        Found {linkedInResult.dedup_result.duplicates_found} potential duplicates with existing contacts
                      </span>
                    </div>
                  )}

                  {/* Action buttons */}
                  <div className="flex gap-3">
                    <button
                      onClick={() => onNavigate?.('people')}
                      className="btn-neo btn-neo-primary flex-1 flex items-center justify-center gap-2"
                    >
                      <PeopleIcon size={18} />
                      View Contacts
                    </button>
                    <button
                      onClick={handleLinkedInReset}
                      className="btn-neo flex items-center gap-2"
                    >
                      <RefreshIcon size={18} />
                      Import More
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Calendar Tab Content */}
          {activeTab === 'calendar' && (
            <div className="card-neo p-5">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 border-3 border-black" style={{ backgroundColor: 'var(--accent-danger)' }}>
                  <CalendarIcon size={20} className="text-white" />
                </div>
                <h2 className="font-heading text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
                  Google Calendar
                </h2>
              </div>

              {/* Instructions */}
              <div className="card-neo p-4 mb-5" style={{ backgroundColor: 'var(--bg-secondary)', borderStyle: 'dashed' }}>
                <div className="flex items-start gap-2 mb-2">
                  <InfoIcon size={18} style={{ color: 'var(--text-secondary)', flexShrink: 0, marginTop: '2px' }} />
                  <p className="font-body text-sm" style={{ color: 'var(--text-secondary)' }}>
                    To export your Google Calendar:
                  </p>
                </div>
                <ol className="list-decimal list-inside space-y-1 text-sm pl-6" style={{ color: 'var(--text-secondary)' }}>
                  <li>
                    <a
                      href="#"
                      onClick={(e) => {
                        e.preventDefault();
                        openExternalLink('https://calendar.google.com/calendar/r/settings/export');
                      }}
                      className="inline-flex items-center gap-1 font-semibold"
                      style={{ color: 'var(--accent-primary)' }}
                    >
                      Open Google Calendar Export
                      <ExternalLinkIcon size={14} />
                    </a>
                  </li>
                  <li>Click "Export" to download ZIP</li>
                  <li>Extract the .ics file</li>
                  <li>Upload here</li>
                </ol>
              </div>

              {/* File upload area */}
              {!calendarPreview && !calendarResult && (
                <div className="space-y-4 mb-5">
                  {/* Owner email input */}
                  <div>
                    <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
                      Your email (to exclude from attendees)
                    </label>
                    <input
                      type="email"
                      placeholder="you@example.com"
                      value={ownerEmail}
                      onChange={(e) => setOwnerEmail(e.target.value)}
                      className="input-neo"
                    />
                  </div>

                  <input
                    ref={calendarFileRef}
                    type="file"
                    accept=".ics"
                    onChange={handleCalendarFileSelect}
                    disabled={calendarLoading}
                    id="calendar-upload"
                    className="hidden"
                  />
                  <label
                    htmlFor="calendar-upload"
                    className={`card-neo p-8 flex flex-col items-center gap-3 cursor-pointer transition-all ${
                      calendarLoading ? 'opacity-50 cursor-not-allowed' : 'hover:translate-x-[-2px] hover:translate-y-[-2px] hover:shadow-[6px_6px_0_var(--shadow-color)]'
                    }`}
                    style={{ borderStyle: 'dashed', backgroundColor: 'var(--bg-card)' }}
                  >
                    {calendarLoading ? (
                      <SpinnerIcon size={32} style={{ color: 'var(--text-muted)' }} />
                    ) : (
                      <UploadIcon size={32} style={{ color: 'var(--text-muted)' }} />
                    )}
                    <span className="font-heading font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {calendarLoading ? 'Loading...' : 'Upload ICS File'}
                    </span>
                    <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
                      Click to select or drag and drop
                    </span>
                  </label>
                </div>
              )}

              {/* Error message */}
              {calendarError && (
                <div className="card-neo p-4 mb-5 flex items-center justify-between" style={{ backgroundColor: 'var(--accent-danger)' }}>
                  <div className="flex items-center gap-2">
                    <ErrorCircleIcon size={18} className="text-white flex-shrink-0" />
                    <span className="text-white text-sm">{calendarError}</span>
                  </div>
                  <button
                    onClick={handleCalendarReset}
                    className="btn-neo btn-neo-danger flex items-center gap-1 py-1 px-3 text-sm"
                  >
                    <RefreshIcon size={14} />
                    Try Again
                  </button>
                </div>
              )}

              {/* Preview section */}
              {calendarPreview && (
                <div className="space-y-5">
                  <h3 className="font-heading text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                    Preview
                  </h3>

                  {/* Stats cards */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="card-neo p-4 text-center" style={{ backgroundColor: 'var(--accent-primary)' }}>
                      <div className="font-heading text-2xl font-bold text-white">
                        {calendarPreview.events_with_attendees}
                      </div>
                      <div className="text-xs text-white opacity-80 uppercase tracking-wide">
                        Meetings
                      </div>
                    </div>
                    <div className="card-neo p-4 text-center" style={{ backgroundColor: 'var(--accent-success)' }}>
                      <div className="font-heading text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
                        {calendarPreview.unique_attendees}
                      </div>
                      <div className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-primary)', opacity: 0.7 }}>
                        People
                      </div>
                    </div>
                  </div>

                  {/* Date range */}
                  <div className="card-neo p-3 flex items-center gap-2" style={{ backgroundColor: 'var(--bg-secondary)' }}>
                    <CalendarIcon size={16} style={{ color: 'var(--text-secondary)' }} />
                    <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                      Date range: {calendarPreview.date_range}
                    </span>
                  </div>

                  {/* Top attendees */}
                  <div className="card-neo p-4" style={{ backgroundColor: 'var(--bg-card)' }}>
                    <h4 className="font-heading font-bold mb-3" style={{ color: 'var(--text-primary)' }}>
                      Top Attendees
                    </h4>
                    <div className="space-y-2">
                      {calendarPreview.top_attendees.slice(0, 5).map((attendee, i) => (
                        <div key={i} className="flex items-center justify-between p-2 border-b border-gray-200 last:border-b-0">
                          <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                            {attendee.name || attendee.email}
                          </span>
                          <span className="badge-neo badge-neo-primary text-xs">
                            {attendee.meeting_count} meetings
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Sample events */}
                  <div className="card-neo p-4" style={{ backgroundColor: 'var(--bg-card)' }}>
                    <h4 className="font-heading font-bold mb-3" style={{ color: 'var(--text-primary)' }}>
                      Sample Events
                    </h4>
                    <div className="space-y-2">
                      {calendarPreview.sample_events.map((event, i) => (
                        <div key={i} className="p-2 border-b border-gray-200 last:border-b-0">
                          <div className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                            {event.summary}
                          </div>
                          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                            {event.date}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="flex gap-3">
                    <button
                      onClick={handleCalendarImport}
                      className="btn-neo btn-neo-primary flex-1 flex items-center justify-center gap-2"
                      disabled={calendarLoading}
                    >
                      {calendarLoading ? (
                        <>
                          <SpinnerIcon size={18} />
                          Importing...
                        </>
                      ) : (
                        <>
                          <UploadIcon size={18} />
                          Import {calendarPreview.unique_attendees} People
                        </>
                      )}
                    </button>
                    <button
                      onClick={handleCalendarReset}
                      className="btn-neo flex items-center gap-2"
                      disabled={calendarLoading}
                    >
                      <XIcon size={18} />
                      Cancel
                    </button>
                  </div>

                  {/* Progress during import */}
                  {calendarLoading && (
                    <div className="card-neo p-4" style={{ backgroundColor: 'var(--accent-warning)' }}>
                      <div className="h-3 border-2 border-black bg-white mb-3 overflow-hidden">
                        <div
                          className="h-full"
                          style={{
                            backgroundColor: 'var(--accent-primary)',
                            width: '100%',
                            animation: 'neo-pulse 1.5s ease-in-out infinite'
                          }}
                        />
                      </div>
                      <div className="flex flex-wrap gap-2 text-xs">
                        <span className="badge-neo badge-neo-primary">Uploading</span>
                        <span className="badge-neo">Processing calendar</span>
                        <span className="badge-neo">Creating contacts</span>
                        <span className="badge-neo">Finding duplicates</span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Import result */}
              {calendarResult && (
                <div className="space-y-5">
                  {/* Success header */}
                  <div className="card-neo p-5" style={{ backgroundColor: 'var(--accent-success)' }}>
                    <div className="flex items-center gap-3">
                      <CheckCircleIcon size={28} />
                      <h3 className="font-heading text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
                        Import Complete!
                      </h3>
                    </div>
                  </div>

                  {/* Result stats */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="card-neo p-4 text-center" style={{ backgroundColor: 'var(--accent-success)' }}>
                      <div className="font-heading text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
                        {calendarResult.imported_people}
                      </div>
                      <div className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-primary)' }}>
                        New People
                      </div>
                    </div>
                    <div className="card-neo p-4 text-center" style={{ backgroundColor: 'var(--accent-primary)' }}>
                      <div className="font-heading text-2xl font-bold text-white">
                        {calendarResult.updated_existing}
                      </div>
                      <div className="text-xs text-white uppercase tracking-wide opacity-80">
                        Updated
                      </div>
                    </div>
                    <div className="card-neo p-4 text-center" style={{ backgroundColor: 'var(--accent-warning)' }}>
                      <div className="font-heading text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
                        {calendarResult.imported_meetings}
                      </div>
                      <div className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-primary)' }}>
                        Meetings
                      </div>
                    </div>
                  </div>

                  {/* Analytics */}
                  {calendarResult.analytics && (
                    <div className="space-y-4">
                      {/* Date range */}
                      <div className="card-neo p-3 flex items-center gap-2" style={{ backgroundColor: 'var(--bg-secondary)' }}>
                        <CalendarIcon size={16} style={{ color: 'var(--text-secondary)' }} />
                        <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                          Period: {calendarResult.analytics.date_range}
                        </span>
                      </div>

                      <div className="grid gap-4 md:grid-cols-2">
                        {calendarResult.analytics.by_frequency && (
                          <div className="card-neo p-4">
                            <h4 className="font-heading font-bold mb-3" style={{ color: 'var(--text-primary)' }}>
                              By Meeting Frequency
                            </h4>
                            <div className="flex flex-wrap gap-2">
                              {Object.entries(calendarResult.analytics.by_frequency).map(([freq, count]) => (
                                <span key={freq} className="badge-neo badge-neo-primary">
                                  {freq}: {count} people
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        {Object.keys(calendarResult.analytics.top_domains || {}).length > 0 && (
                          <div className="card-neo p-4">
                            <h4 className="font-heading font-bold mb-3" style={{ color: 'var(--text-primary)' }}>
                              Top Domains
                            </h4>
                            <div className="flex flex-wrap gap-2">
                              {Object.entries(calendarResult.analytics.top_domains)
                                .slice(0, 5)
                                .map(([domain, count]) => (
                                  <span key={domain} className="badge-neo badge-neo-peach">
                                    {domain} ({count})
                                  </span>
                                ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Dedup notice */}
                  {calendarResult.dedup_result && calendarResult.dedup_result.duplicates_found !== undefined && calendarResult.dedup_result.duplicates_found > 0 && (
                    <div className="card-neo p-4 flex items-center gap-3" style={{ backgroundColor: 'var(--bg-secondary)' }}>
                      <RefreshIcon size={18} style={{ color: 'var(--text-secondary)' }} />
                      <span style={{ color: 'var(--text-secondary)' }}>
                        Found {calendarResult.dedup_result.duplicates_found} potential duplicates with existing contacts
                      </span>
                    </div>
                  )}

                  {/* Action buttons */}
                  <div className="flex gap-3">
                    <button
                      onClick={() => onNavigate?.('people')}
                      className="btn-neo btn-neo-primary flex-1 flex items-center justify-center gap-2"
                    >
                      <PeopleIcon size={18} />
                      View Contacts
                    </button>
                    <button
                      onClick={handleCalendarReset}
                      className="btn-neo flex items-center gap-2"
                    >
                      <RefreshIcon size={18} />
                      Import More
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </main>
      ) : (
        <div className="card-neo p-8 text-center">
          <h2 className="font-heading text-xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
            Development Mode
          </h2>
          <p style={{ color: 'var(--text-secondary)' }}>
            Open in Telegram Mini App for full functionality
          </p>
        </div>
      )}
    </div>
  );
};
