import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { api } from '../lib/api';
import type { CommunityMembership } from '../lib/api';
import {
  ChevronLeftIcon, ChevronDownIcon, UserIcon, TrashIcon, SpinnerIcon,
  CheckCircleIcon, ErrorCircleIcon, MicrophoneIcon, TextIcon, CommunityIcon
} from '../components/icons';

interface SelfAssertion {
  predicate: string;
  value: string;
}

interface SelfProfile {
  person_id: string;
  display_name: string;
  community_id: string;
  community_name: string;
  assertions: SelfAssertion[];
  created_at: string;
}

interface SelfProfilePageProps {
  communityId?: string;
  communities?: CommunityMembership[];
  onBack?: () => void;
  onCommunityChange?: (communityId: string) => void;
}

// Helper to format predicate for display
const formatPredicate = (predicate: string): string => {
  const labels: Record<string, string> = {
    'self_role': 'Role',
    'self_offer': 'Can help with',
    'self_seek': 'Looking for',
    'background': 'Background',
    'located_in': 'Location',
    'contact_preference': 'Contact',
    'interested_in': 'Interests'
  };
  return labels[predicate] || predicate;
};

// Get badge color based on predicate
const getPredicateBadgeClass = (predicate: string): string => {
  const baseClass = 'inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold border-2 border-black';

  const colors: Record<string, string> = {
    'self_role': 'bg-blue-200',
    'self_offer': 'bg-mint',
    'self_seek': 'bg-peach',
    'background': 'bg-lavender',
    'located_in': 'bg-neo-yellow',
    'contact_preference': 'bg-neo-gray-200',
    'interested_in': 'bg-pink-200'
  };

  return `${baseClass} ${colors[predicate] || 'bg-neo-gray-200'} text-black`;
};

export const SelfProfilePage = ({ communityId, communities = [], onBack, onCommunityChange }: SelfProfilePageProps) => {
  const { isAuthenticated } = useAuth();
  const [profile, setProfile] = useState<SelfProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [_error, setError] = useState<string | null>(null);

  // Community selector state
  const [selectedCommunityId, setSelectedCommunityId] = useState<string | undefined>(communityId);
  const [showCommunitySelector, setShowCommunitySelector] = useState(false);

  // Add/edit state
  const [isAdding, setIsAdding] = useState(false);
  const [inputMode, setInputMode] = useState<'voice' | 'text'>('text');
  const [textInput, setTextInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);

  // Delete state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Sync with prop changes
  useEffect(() => {
    if (communityId && communityId !== selectedCommunityId) {
      setSelectedCommunityId(communityId);
    }
  }, [communityId]);

  useEffect(() => {
    if (isAuthenticated && selectedCommunityId) {
      fetchProfile();
    }
  }, [isAuthenticated, selectedCommunityId]);

  // Handle community selection
  const handleCommunitySelect = (id: string) => {
    setSelectedCommunityId(id);
    setShowCommunitySelector(false);
    setProfile(null); // Reset profile when switching
    setSubmitResult(null); // Clear any messages
    onCommunityChange?.(id);
  };

  // Get current community name
  const currentCommunityName = communities.find(c => c.community_id === selectedCommunityId)?.name
    || profile?.community_name
    || 'Community';

  const fetchProfile = async () => {
    if (!selectedCommunityId) return;

    setLoading(true);
    setError(null);

    try {
      const result = await api.getSelfProfile(selectedCommunityId);
      setProfile(result);
    } catch (err) {
      // 404 or null means no profile yet - that's OK
      if (err instanceof Error && !err.message.includes('404')) {
        setError(err.message);
      }
      setProfile(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitText = async () => {
    if (!textInput.trim() || !selectedCommunityId) return;

    setSubmitting(true);
    setSubmitResult(null);

    try {
      const result = await api.createOrUpdateProfile(selectedCommunityId, textInput);
      setSubmitResult({
        success: true,
        message: `Profile ${profile ? 'updated' : 'created'}! Added ${result.assertions_created} facts.`
      });
      setTextInput('');
      setIsAdding(false);
      // Refresh profile
      await fetchProfile();
    } catch (err) {
      setSubmitResult({
        success: false,
        message: err instanceof Error ? err.message : 'Failed to save profile'
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleVoiceRecorded = async (_audioBlob: Blob) => {
    // For now, voice needs to be transcribed server-side
    // This would require uploading to storage first
    // For MVP, suggest using text input
    setSubmitResult({
      success: false,
      message: 'Voice recording not yet supported in Mini App. Please use text input.'
    });
  };

  const handleDelete = async () => {
    if (!selectedCommunityId) return;

    setDeleting(true);

    try {
      await api.deleteSelfProfile(selectedCommunityId);
      setProfile(null);
      setShowDeleteConfirm(false);
      setSubmitResult({
        success: true,
        message: 'Profile deleted successfully.'
      });
    } catch (err) {
      setSubmitResult({
        success: false,
        message: err instanceof Error ? err.message : 'Failed to delete profile'
      });
    } finally {
      setDeleting(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] p-4 flex items-center justify-center">
        <div className="card-neo p-6 text-center">
          <ErrorCircleIcon size={48} className="mx-auto mb-4 text-coral" />
          <p className="text-lg font-semibold">Please authenticate first</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] p-4 flex items-center justify-center">
        <SpinnerIcon size={32} className="text-[var(--accent-primary)]" />
      </div>
    );
  }

  // Community selector component (reusable)
  const CommunitySelectorCard = () => {
    if (communities.length <= 1) return null;

    return (
      <div className="card-neo p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <CommunityIcon size={18} className="text-[var(--text-muted)]" />
          <span className="text-sm font-semibold text-[var(--text-muted)]">
            Your Communities ({communities.length})
          </span>
        </div>

        <button
          className="btn-neo w-full flex items-center justify-between px-4 py-3"
          onClick={() => setShowCommunitySelector(!showCommunitySelector)}
        >
          <span className="font-semibold">{currentCommunityName}</span>
          <ChevronDownIcon
            size={18}
            className={`transition-transform ${showCommunitySelector ? 'rotate-180' : ''}`}
          />
        </button>

        {showCommunitySelector && (
          <div className="mt-2 space-y-2">
            {communities.map((c) => (
              <button
                key={c.community_id}
                className={`w-full text-left px-4 py-3 border-2 border-black transition-all ${
                  c.community_id === selectedCommunityId
                    ? 'bg-[var(--accent-primary)] text-white font-semibold'
                    : 'bg-[var(--bg-secondary)] hover:bg-[var(--bg-card)]'
                }`}
                onClick={() => handleCommunitySelect(c.community_id)}
              >
                <div className="font-semibold">{c.name}</div>
                <div className="text-xs opacity-75">
                  Joined {new Date(c.joined_at).toLocaleDateString()}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  };

  // No profile yet - show create prompt
  if (!profile && !isAdding) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)]">
        {/* Header */}
        <header className="sticky top-0 z-10 bg-[var(--bg-primary)] border-b-3 border-black p-4">
          {onBack && (
            <button
              className="btn-neo p-2 mb-2"
              onClick={onBack}
              aria-label="Back"
            >
              <ChevronLeftIcon size={20} />
            </button>
          )}
          <h1 className="font-heading text-2xl font-bold">Your Profile</h1>
        </header>

        <main className="p-4 pb-24">
          {/* Community selector */}
          <CommunitySelectorCard />

          <div className="card-neo p-6 text-center">
            <UserIcon size={64} className="mx-auto mb-4 text-[var(--text-muted)]" />
            <h2 className="font-heading text-xl font-bold mb-2">No profile yet</h2>
            <p className="text-[var(--text-muted)] mb-6">
              Introduce yourself to <strong>{currentCommunityName}</strong> so others can find you.
            </p>
            <button
              className="btn-neo btn-neo-primary w-full"
              onClick={() => setIsAdding(true)}
            >
              Create Profile
            </button>
          </div>
        </main>
      </div>
    );
  }

  // Adding/editing mode
  if (isAdding) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)]">
        {/* Header */}
        <header className="sticky top-0 z-10 bg-[var(--bg-primary)] border-b-3 border-black p-4">
          <div className="flex items-center gap-3">
            <button
              className="btn-neo p-2"
              onClick={() => {
                setIsAdding(false);
                setTextInput('');
              }}
              aria-label="Cancel"
            >
              <ChevronLeftIcon size={20} />
            </button>
            <h1 className="font-heading text-xl font-bold">
              {profile ? 'Add to Profile' : 'Create Profile'}
            </h1>
          </div>
        </header>

        <main className="p-4 pb-24 space-y-4">
          {/* Result message */}
          {submitResult && (
            <div className={`card-neo p-3 flex items-center gap-2 ${
              submitResult.success ? 'bg-mint' : 'bg-coral text-white'
            }`}>
              {submitResult.success ? (
                <CheckCircleIcon size={18} />
              ) : (
                <ErrorCircleIcon size={18} />
              )}
              <span>{submitResult.message}</span>
            </div>
          )}

          {/* Input mode toggle */}
          <div className="flex gap-2">
            <button
              className={`btn-neo flex-1 flex items-center justify-center gap-2 ${
                inputMode === 'text' ? 'btn-neo-primary' : ''
              }`}
              onClick={() => setInputMode('text')}
            >
              <TextIcon size={18} />
              Text
            </button>
            <button
              className={`btn-neo flex-1 flex items-center justify-center gap-2 ${
                inputMode === 'voice' ? 'btn-neo-primary' : ''
              }`}
              onClick={() => setInputMode('voice')}
            >
              <MicrophoneIcon size={18} />
              Voice
            </button>
          </div>

          {/* Input area */}
          {inputMode === 'text' ? (
            <div className="space-y-4">
              <div className="card-neo p-4">
                <label className="block font-semibold mb-2">
                  Tell us about yourself:
                </label>
                <textarea
                  className="input-neo w-full h-40 resize-none"
                  placeholder="Hi! I'm [name], I work as [role] at [company].

I can help with: [skills, expertise]

I'm looking for: [connections, opportunities]"
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                />
                <p className="text-sm text-[var(--text-muted)] mt-2">
                  Include your name, role, skills, and what you're looking for.
                </p>
              </div>

              <button
                className="btn-neo btn-neo-primary w-full flex items-center justify-center gap-2"
                onClick={handleSubmitText}
                disabled={submitting || !textInput.trim()}
              >
                {submitting ? (
                  <>
                    <SpinnerIcon size={18} />
                    Processing...
                  </>
                ) : (
                  <>
                    <CheckCircleIcon size={18} />
                    {profile ? 'Add to Profile' : 'Create Profile'}
                  </>
                )}
              </button>
            </div>
          ) : (
            <div className="card-neo p-4 text-center">
              <button
                className="btn-neo btn-neo-primary px-6 py-3 flex items-center justify-center gap-2 mx-auto"
                onClick={() => handleVoiceRecorded(new Blob())}
              >
                <MicrophoneIcon size={20} />
                Record Voice Note
              </button>
              <p className="text-sm text-[var(--text-muted)] mt-4">
                Record up to 60 seconds about yourself.
              </p>
            </div>
          )}
        </main>
      </div>
    );
  }

  // Profile view
  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-[var(--bg-primary)] border-b-3 border-black p-4">
        <div className="flex items-center gap-3">
          {onBack && (
            <button
              className="btn-neo p-2 flex-shrink-0"
              onClick={onBack}
              aria-label="Back"
            >
              <ChevronLeftIcon size={20} />
            </button>
          )}
          <div className="flex-1 min-w-0">
            <h1 className="font-heading text-xl font-bold truncate">
              {profile?.display_name}
            </h1>
            <p className="text-sm text-[var(--text-muted)]">
              in {profile?.community_name}
            </p>
          </div>
        </div>
      </header>

      <main className="p-4 pb-24 space-y-4">
        {/* Community selector */}
        <CommunitySelectorCard />

        {/* Result message */}
        {submitResult && (
          <div className={`card-neo p-3 flex items-center gap-2 ${
            submitResult.success ? 'bg-mint' : 'bg-coral text-white'
          }`}>
            {submitResult.success ? (
              <CheckCircleIcon size={18} />
            ) : (
              <ErrorCircleIcon size={18} />
            )}
            <span>{submitResult.message}</span>
          </div>
        )}

        {/* Profile info */}
        <div className="card-neo p-4">
          <h3 className="font-heading font-bold text-lg mb-3">About You</h3>

          {profile?.assertions && profile.assertions.length > 0 ? (
            <ul className="space-y-2">
              {profile.assertions.map((a, i) => (
                <li
                  key={`${a.predicate}-${i}`}
                  className="flex items-start gap-3 p-2 bg-[var(--bg-secondary)] border-2 border-black"
                >
                  <span className={getPredicateBadgeClass(a.predicate)}>
                    {formatPredicate(a.predicate)}
                  </span>
                  <span className="flex-1 text-sm">{a.value}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[var(--text-muted)] text-sm italic">
              No information yet. Add some details about yourself!
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="card-neo p-4 space-y-3">
          <button
            className="btn-neo btn-neo-primary w-full flex items-center justify-center gap-2"
            onClick={() => setIsAdding(true)}
          >
            <MicrophoneIcon size={18} />
            Add More Info
          </button>

          <button
            className="btn-neo btn-neo-danger w-full flex items-center justify-center gap-2"
            onClick={() => setShowDeleteConfirm(true)}
          >
            <TrashIcon size={18} />
            Delete Profile
          </button>
        </div>

        {/* Joined date */}
        {profile?.created_at && (
          <p className="text-center text-sm text-[var(--text-muted)]">
            Joined {new Date(profile.created_at).toLocaleDateString()}
          </p>
        )}
      </main>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
          onClick={() => setShowDeleteConfirm(false)}
        >
          <div
            className="card-neo p-6 max-w-sm w-full bg-[var(--bg-card)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-coral rounded-full">
                <TrashIcon size={24} className="text-white" />
              </div>
              <h3 className="font-heading font-bold text-xl">Delete Profile?</h3>
            </div>
            <p className="mb-2">
              Are you sure you want to delete your profile from <strong>{profile?.community_name}</strong>?
            </p>
            <p className="text-sm text-[var(--text-muted)] mb-6">
              You can rejoin anytime using the invite link.
            </p>
            <div className="flex gap-3">
              <button
                className="btn-neo flex-1"
                onClick={() => setShowDeleteConfirm(false)}
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                className="btn-neo btn-neo-danger flex-1 flex items-center justify-center gap-2"
                onClick={handleDelete}
                disabled={deleting}
              >
                {deleting ? (
                  <>
                    <SpinnerIcon size={16} />
                    Deleting...
                  </>
                ) : (
                  <>
                    <TrashIcon size={16} />
                    Delete
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
