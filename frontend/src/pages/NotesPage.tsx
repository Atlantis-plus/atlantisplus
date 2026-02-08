import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { VoiceRecorder } from '../components/VoiceRecorder';
import { supabase } from '../lib/supabase';
import { api } from '../lib/api';

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
      case 'done': return '✅';
      case 'error': return '❌';
      case 'transcribing': return '🎧';
      case 'extracting': return '🔍';
      default: return '⏳';
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="page">
        <div className="error">
          <p>Please authenticate first</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="header">
        <h1>Add Note</h1>
        <p className="subtitle">Record or write about people you know</p>
      </header>

      <main className="main">
        {/* Mode switcher */}
        <div className="mode-switcher">
          <button
            className={`mode-btn ${mode === 'voice' ? 'active' : ''}`}
            onClick={() => setMode('voice')}
          >
            🎤 Voice
          </button>
          <button
            className={`mode-btn ${mode === 'text' ? 'active' : ''}`}
            onClick={() => setMode('text')}
          >
            ✏️ Text
          </button>
        </div>

        {/* Error display */}
        {error && (
          <div className="error-banner">
            {error}
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        {/* Input area */}
        <div className="input-area">
          {mode === 'voice' ? (
            <VoiceRecorder
              userId={userId!}
              onProcessingStarted={handleProcessingStarted}
              onError={handleError}
            />
          ) : (
            <div className="text-input">
              <textarea
                value={textNote}
                onChange={(e) => setTextNote(e.target.value)}
                placeholder="Write about someone you know...&#10;&#10;Example: Met Ivan at the conference. He's CTO at TechStartup, strong in ML and data pipelines. Based in Moscow. Very responsive, helped me with a recommendation last month."
                rows={6}
              />
              <button
                className="submit-btn"
                onClick={handleTextSubmit}
                disabled={!textNote.trim() || submitting}
              >
                {submitting ? 'Processing...' : 'Submit'}
              </button>
            </div>
          )}
        </div>

        {/* Recent evidence */}
        {recentEvidence.length > 0 && (
          <div className="recent-section">
            <h3>Recent Notes</h3>
            <ul className="evidence-list">
              {recentEvidence.map((e) => (
                <li key={e.evidence_id} className="evidence-item">
                  <span className="status-icon">{getStatusIcon(e.processing_status)}</span>
                  <span className="evidence-preview">
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
