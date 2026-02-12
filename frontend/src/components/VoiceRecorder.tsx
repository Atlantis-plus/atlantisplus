import { useState, useRef, useCallback } from 'react';
import { supabase } from '../lib/supabase';
import { api } from '../lib/api';
import { MicrophoneIcon, SpinnerIcon } from './icons';

interface VoiceRecorderProps {
  userId: string;
  onProcessingStarted?: (evidenceId: string) => void;
  onError?: (error: string) => void;
}

export const VoiceRecorder = ({ userId, onProcessingStarted, onError }: VoiceRecorderProps) => {
  const [recording, setRecording] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [duration, setDuration] = useState(0);
  const [debugInfo, setDebugInfo] = useState<string>('');
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const timerRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Try to use webm, fallback to whatever is supported
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : 'audio/mp4';

      mediaRecorder.current = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];

      mediaRecorder.current.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorder.current.onstop = async () => {
        // Stop all tracks
        stream.getTracks().forEach(track => track.stop());

        // Create blob
        const blob = new Blob(chunksRef.current, { type: mimeType });
        await uploadAndProcess(blob, mimeType);
      };

      mediaRecorder.current.start(1000); // Collect data every second
      setRecording(true);
      setDuration(0);

      // Start timer
      timerRef.current = window.setInterval(() => {
        setDuration(d => d + 1);
      }, 1000);

    } catch (err) {
      onError?.('Could not access microphone');
      console.error('Microphone error:', err);
    }
  }, [onError]);

  const stopRecording = useCallback(() => {
    if (mediaRecorder.current && recording) {
      mediaRecorder.current.stop();
      setRecording(false);

      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  }, [recording]);

  const uploadAndProcess = async (blob: Blob, mimeType: string) => {
    setUploading(true);
    setDebugInfo('Starting...');

    try {
      // Generate unique filename
      const extension = mimeType.includes('webm') ? 'webm' : 'mp4';
      const filename = `${Date.now()}.${extension}`;
      const storagePath = `${userId}/${filename}`;

      setDebugInfo(`Uploading ${(blob.size / 1024).toFixed(1)}KB...`);
      console.log('[VoiceRecorder] Starting upload:', { storagePath, blobSize: blob.size, mimeType });

      // Upload to Supabase Storage
      const { error: uploadError, data: uploadData } = await supabase.storage
        .from('voice-notes')
        .upload(storagePath, blob, {
          contentType: mimeType,
          upsert: false
        });

      if (uploadError) {
        console.error('[VoiceRecorder] Storage upload failed:', uploadError);
        throw new Error(`Storage: ${uploadError.message}`);
      }

      setDebugInfo('Storage OK. Calling API...');
      console.log('[VoiceRecorder] Storage upload success:', uploadData);

      // Check token before API call
      const hasToken = api.hasAccessToken();
      const apiUrl = api.getApiUrl();
      console.log('[VoiceRecorder] Pre-API check:', { hasToken, apiUrl });
      setDebugInfo(`API: ${apiUrl.substring(0, 30)}... Token: ${hasToken ? 'YES' : 'NO'}`);

      if (!hasToken) {
        throw new Error('No auth token - please re-authenticate');
      }

      // Small delay then call API
      await new Promise(resolve => setTimeout(resolve, 100));

      console.log('[VoiceRecorder] Calling processVoice with path:', storagePath);
      setDebugInfo('Calling processVoice...');

      // Start processing
      const response = await api.processVoice(storagePath);
      console.log('[VoiceRecorder] processVoice response:', response);
      setDebugInfo('Success!');
      onProcessingStarted?.(response.evidence_id);

    } catch (err) {
      console.error('[VoiceRecorder] Error details:', {
        error: err,
        message: err instanceof Error ? err.message : 'Unknown',
        stack: err instanceof Error ? err.stack : undefined
      });
      const message = err instanceof Error ? err.message : 'Upload failed';
      setDebugInfo(`Error: ${message}`);
      onError?.(message);
    } finally {
      setUploading(false);
    }
  };

  const formatDuration = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Debug info - subtle styling */}
      {debugInfo && (
        <div className="w-full px-3 py-2 text-xs text-[var(--text-muted)] bg-[var(--bg-secondary)] border-2 border-[var(--border-color)] font-mono">
          {debugInfo}
        </div>
      )}

      {uploading ? (
        /* Uploading state */
        <div className="flex flex-col items-center gap-3">
          <div
            className="w-20 h-20 flex items-center justify-center rounded-full bg-[var(--bg-card)] border-3 border-[var(--border-color)]"
            style={{ boxShadow: '4px 4px 0 var(--shadow-color)' }}
          >
            <SpinnerIcon size={32} className="text-[var(--accent-primary)]" />
          </div>
          <span className="font-semibold text-[var(--text-primary)]">Uploading...</span>
        </div>
      ) : recording ? (
        /* Recording state */
        <div className="flex flex-col items-center gap-4">
          {/* Recording indicator with pulsing dot */}
          <div className="flex items-center gap-3">
            <span
              className="w-3 h-3 rounded-full bg-[var(--accent-danger)]"
              style={{ animation: 'neo-pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite' }}
            />
            <span
              className="font-mono font-bold text-2xl text-[var(--text-primary)] tracking-wider"
              style={{ minWidth: '80px', textAlign: 'center' }}
            >
              {formatDuration(duration)}
            </span>
          </div>

          {/* Stop button */}
          <button
            className="btn-neo btn-neo-danger px-6 py-3 rounded-none font-bold uppercase tracking-wide"
            onClick={stopRecording}
          >
            Stop Recording
          </button>
        </div>
      ) : (
        /* Idle state - large record button */
        <button
          className="w-20 h-20 flex items-center justify-center rounded-full bg-[var(--accent-primary)] border-3 border-[var(--border-color)] cursor-pointer transition-transform duration-100 hover:translate-x-[-2px] hover:translate-y-[-2px] active:translate-x-[2px] active:translate-y-[2px]"
          style={{
            boxShadow: '4px 4px 0 var(--shadow-color)',
          }}
          onClick={startRecording}
          aria-label="Start Recording"
        >
          <MicrophoneIcon size={28} className="text-white" strokeWidth={2.5} />
        </button>
      )}
    </div>
  );
};
