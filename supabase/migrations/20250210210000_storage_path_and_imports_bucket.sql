-- Migration: Rename audio_storage_path to storage_path and create imports bucket
-- This makes the column more generic for storing any file type (audio, CSV, ICS, etc.)

-- 1. Rename column in raw_evidence
ALTER TABLE raw_evidence RENAME COLUMN audio_storage_path TO storage_path;

-- 2. Add comment for clarity
COMMENT ON COLUMN raw_evidence.storage_path IS 'Path to file in Supabase Storage (voice notes, import files, etc.)';

-- 3. Create imports bucket for storing import files (CSV, ICS)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'imports',
    'imports',
    false,
    52428800,  -- 50MB limit
    ARRAY['text/csv', 'text/calendar', 'application/octet-stream', 'text/plain']
)
ON CONFLICT (id) DO NOTHING;

-- 4. RLS policies for imports bucket
-- Users can only access their own imports (folder structure: imports/{user_id}/...)

CREATE POLICY "Users can upload their own imports"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
    bucket_id = 'imports'
    AND (storage.foldername(name))[1] = auth.uid()::text
);

CREATE POLICY "Users can view their own imports"
ON storage.objects FOR SELECT
TO authenticated
USING (
    bucket_id = 'imports'
    AND (storage.foldername(name))[1] = auth.uid()::text
);

CREATE POLICY "Users can delete their own imports"
ON storage.objects FOR DELETE
TO authenticated
USING (
    bucket_id = 'imports'
    AND (storage.foldername(name))[1] = auth.uid()::text
);

-- 5. Service role can access all imports (for backend processing)
CREATE POLICY "Service role full access to imports"
ON storage.objects FOR ALL
TO service_role
USING (bucket_id = 'imports')
WITH CHECK (bucket_id = 'imports');
