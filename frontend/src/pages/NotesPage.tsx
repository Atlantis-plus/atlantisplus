import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { VoiceRecorder } from '../components/VoiceRecorder';
import { supabase } from '../lib/supabase';
import { api } from '../lib/api';
import {
  MicrophoneIcon,
  TextIcon,
  CheckCircleIcon,
  ErrorCircleIcon,
  HeadphonesIcon,
  ScanIcon,
  ClockIcon,
  XIcon
} from '../components/icons';

type NoteMode = 'voice' | 'text';

interface Evidence {
  evidence_id: string;
  processing_status: string;
  content: string;
  created_at: string;
}

export const NotesPage = () => {
  const { session, isAuthenticated } = useAuth();
  const [mode, setMode] = useState<NoteMode>('voice');
  const [textNote, setTextNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [recentEvidence, setRecentEvidence] = useState<Evidence[]>([]);
  const [error, setError] = useState<string | null>(null);

  const userId = session?.user?.id;

  // Subscribe to evidence updates
  useEffect(() => {
    if (!userId) return;

    // Fetch recent evidence
    const fetchRecent = async () => {
      const { data } = await supabase
        .from('raw_evidence')
        .select('evidence_id, processing_status, content, created_at')
        .order('created_at', { ascending: false })
        .limit(5);

      if (data) {
        setRecentEvidence(data);
      }
    };

    fetchRecent();

    // Subscribe to realtime updates
    const channel = supabase
      .channel('evidence-updates')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'raw_evidence',
          filter: `owner_id=eq.${userId}`
        },
        (payload) => {
          if (payload.eventType === 'INSERT') {
            setRecentEvidence(prev => [payload.new as Evidence, ...prev.slice(0, 4)]);
          } else if (payload.eventType === 'UPDATE') {
            setRecentEvidence(prev =>
              prev.map(e =>
                e.evidence_id === (payload.new as Evidence).evidence_id
                  ? payload.new as Evidence
                  : e
              )
            );
          }
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [userId]);

  const handleTextSubmit = async () => {
    if (!textNote.trim() || submitting) return;

    setSubmitting(true);
    setError(null);

    try {
      await api.processText(textNote);
      setTextNote('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit');
    } finally {
      setSubmitting(false);
    }
  };

  const handleProcessingStarted = (evidenceId: string) => {
    console.log('Processing started:', evidenceId);
  };

  const handleError = (error: string) => {
    setError(error);
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'done':
        return <CheckCircleIcon size={16} className="text-green-500" />;
      case 'error':
        return <ErrorCircleIcon size={16} className="text-red-500" />;
      case 'transcribing':
        return <HeadphonesIcon size={16} className="text-blue-500" />;
      case 'extracting':
        return <ScanIcon size={16} className="text-yellow-500" />;
      default:
        return <ClockIcon size={16} className="text-gray-400" />;
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="p-4">
        <div className="card-neo p-4 bg-red-50 border-red-500">
          <p className="text-red-600 font-medium">Please authenticate first</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen p-4">
      {/* Page Header */}
      <header className="mb-6">
        <h1 className="font-heading text-2xl font-bold">Add Note</h1>
        <p className="text-[var(--text-secondary)] mt-1">
          Record or write about people you know
        </p>
      </header>

      <main className="space-y-6">
        {/* Mode Switcher */}
        <div className="flex gap-2">
          <button
            className={`btn-neo flex-1 ${mode === 'voice' ? 'btn-neo-primary' : ''}`}
            onClick={() => setMode('voice')}
          >
            <MicrophoneIcon size={18} />
            <span>Voice</span>
          </button>
          <button
            className={`btn-neo flex-1 ${mode === 'text' ? 'btn-neo-primary' : ''}`}
            onClick={() => setMode('text')}
          >
            <TextIcon size={18} />
            <span>Text</span>
          </button>
        </div>

        {/* Error Display */}
        {error && (
          <div className="card-neo bg-red-50 border-red-500 flex items-center justify-between gap-3 p-3">
            <span className="text-red-600 text-sm">{error}</span>
            <button
              onClick={() => setError(null)}
              className="p-1 hover:bg-red-100 rounded transition-colors"
              aria-label="Dismiss error"
            >
              <XIcon size={18} className="text-red-500" />
            </button>
          </div>
        )}

        {/* Input Area */}
        <div className="card-neo p-4">
          {mode === 'voice' ? (
            <VoiceRecorder
              userId={userId!}
              onProcessingStarted={handleProcessingStarted}
              onError={handleError}
            />
          ) : (
            <div className="space-y-4">
              <textarea
                value={textNote}
                onChange={(e) => setTextNote(e.target.value)}
                placeholder={`Write about someone you know...\n\nExample: Met Ivan at the conference. He's CTO at TechStartup, strong in ML and data pipelines. Based in Moscow. Very responsive, helped me with a recommendation last month.`}
                rows={6}
                className="input-neo"
              />
              <button
                className="btn-neo btn-neo-primary w-full"
                onClick={handleTextSubmit}
                disabled={!textNote.trim() || submitting}
              >
                {submitting ? 'Processing...' : 'Submit'}
              </button>
            </div>
          )}
        </div>

        {/* Recent Evidence */}
        {recentEvidence.length > 0 && (
          <div className="space-y-3">
            <h3 className="font-heading font-semibold text-lg">Recent Notes</h3>
            <ul className="space-y-2">
              {recentEvidence.map((e) => (
                <li
                  key={e.evidence_id}
                  className="card-neo p-3 flex items-center gap-3"
                >
                  <span className="flex-shrink-0">
                    {getStatusIcon(e.processing_status)}
                  </span>
                  <span className="text-sm truncate">
                    {e.content?.slice(0, 50) || 'Processing...'}
                    {e.content?.length > 50 ? '...' : ''}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>
    </div>
  );
};
