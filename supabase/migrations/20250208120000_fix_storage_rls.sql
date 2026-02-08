-- Enable RLS on storage.objects (may already be enabled)
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

-- Drop and recreate policies with correct syntax
DROP POLICY IF EXISTS "Users can upload voice notes" ON storage.objects;
DROP POLICY IF EXISTS "Users can read own voice notes" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete own voice notes" ON storage.objects;

-- Allow authenticated users to upload to their folder
CREATE POLICY "Users can upload voice notes"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
    bucket_id = 'voice-notes'
    AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to read their files
CREATE POLICY "Users can read own voice notes"
ON storage.objects FOR SELECT
TO authenticated
USING (
    bucket_id = 'voice-notes'
    AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to delete their files
CREATE POLICY "Users can delete own voice notes"
ON storage.objects FOR DELETE
TO authenticated
USING (
    bucket_id = 'voice-notes'
    AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to update their files
CREATE POLICY "Users can update own voice notes"
ON storage.objects FOR UPDATE
TO authenticated
USING (
    bucket_id = 'voice-notes'
    AND (storage.foldername(name))[1] = auth.uid()::text
);
