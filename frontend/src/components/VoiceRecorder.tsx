import { useState, useRef, useCallback } from 'react';
import { supabase } from '../lib/supabase';
import { api } from '../lib/api';

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
    <div className="voice-recorder">
      {debugInfo && (
        <div className="debug-info" style={{ fontSize: '10px', color: '#666', marginBottom: '8px' }}>
          {debugInfo}
        </div>
      )}
      {uploading ? (
        <div className="recorder-status">
          <div className="spinner"></div>
          <span>Uploading...</span>
        </div>
      ) : recording ? (
        <div className="recorder-active">
          <div className="recording-indicator">
            <span className="pulse"></span>
            <span className="duration">{formatDuration(duration)}</span>
          </div>
          <button className="stop-btn" onClick={stopRecording}>
            Stop Recording
          </button>
        </div>
      ) : (
        <button className="record-btn" onClick={startRecording}>
          <span className="icon">🎤</span>
          <span>Start Recording</span>
        </button>
      )}
    </div>
  );
};
