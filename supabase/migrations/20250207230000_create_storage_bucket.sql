-- Create storage bucket for voice notes
INSERT INTO storage.buckets (id, name, public)
VALUES ('voice-notes', 'voice-notes', false)
ON CONFLICT (id) DO NOTHING;

-- RLS policy: users can upload to their own folder
CREATE POLICY "Users can upload voice notes"
ON storage.objects FOR INSERT
WITH CHECK (
    bucket_id = 'voice-notes'
    AND auth.uid()::text = (storage.foldername(name))[1]
);

-- RLS policy: users can read their own files
CREATE POLICY "Users can read own voice notes"
ON storage.objects FOR SELECT
USING (
    bucket_id = 'voice-notes'
    AND auth.uid()::text = (storage.foldername(name))[1]
);

-- RLS policy: users can delete their own files
CREATE POLICY "Users can delete own voice notes"
ON storage.objects FOR DELETE
USING (
    bucket_id = 'voice-notes'
    AND auth.uid()::text = (storage.foldername(name))[1]
);
