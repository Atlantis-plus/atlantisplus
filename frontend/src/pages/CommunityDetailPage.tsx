import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import type { Community, CommunityMember } from '../lib/api';
import {
  SpinnerIcon, PeopleIcon, ChevronLeftIcon, CopyIcon,
  CheckCircleIcon, RefreshIcon, ErrorCircleIcon
} from '../components/icons';

interface CommunityDetailPageProps {
  communityId: string;
  onBack: () => void;
}

export function CommunityDetailPage({ communityId, onBack }: CommunityDetailPageProps) {
  const [community, setCommunity] = useState<Community | null>(null);
  const [members, setMembers] = useState<CommunityMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    loadData();
  }, [communityId]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [communityData, membersData] = await Promise.all([
        api.getCommunity(communityId),
        api.getCommunityMembers(communityId)
      ]);
      setCommunity(communityData);
      setMembers(membersData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load community');
    } finally {
      setLoading(false);
    }
  };

  const copyInviteLink = () => {
    if (!community) return;
    const link = `https://t.me/atlantisplus_bot?start=join_${community.invite_code}`;
    navigator.clipboard.writeText(link);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2000);
  };

  const regenerateInvite = async () => {
    if (!community) return;
    try {
      setRegenerating(true);
      const result = await api.regenerateInviteCode(communityId);
      setCommunity({ ...community, invite_code: result.invite_code });
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to regenerate invite');
    } finally {
      setRegenerating(false);
    }
  };

  const formatAssertions = (assertions: CommunityMember['assertions']) => {
    const role = assertions.find(a => a.predicate === 'self_role')?.value;
    const offers = assertions.filter(a => a.predicate === 'self_offer').map(a => a.value);
    const seeks = assertions.filter(a => a.predicate === 'self_seek').map(a => a.value);

    return { role, offers, seeks };
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)]">
        <div className="flex items-center justify-center py-12">
          <SpinnerIcon size={32} className="text-[var(--accent-primary)]" />
        </div>
      </div>
    );
  }

  if (error || !community) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)]">
        <div className="p-4">
          <div className="card-neo p-8 text-center">
            <ErrorCircleIcon size={48} className="mx-auto mb-4 text-coral" />
            <p className="text-coral mb-4">{error || 'Community not found'}</p>
            <button onClick={onBack} className="btn-neo">
              <ChevronLeftIcon size={18} />
              Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  const inviteLink = `https://t.me/atlantisplus_bot?start=join_${community.invite_code}`;

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-[var(--bg-primary)] border-b-3 border-black p-4">
        <div className="flex items-center gap-3">
          <button
            className="btn-neo p-2 flex-shrink-0"
            onClick={onBack}
            aria-label="Back"
          >
            <ChevronLeftIcon size={20} />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="font-heading text-xl font-bold truncate">{community.name}</h1>
            <p className="text-sm text-[var(--text-muted)]">
              {members.length} member{members.length !== 1 ? 's' : ''}
            </p>
          </div>
        </div>
      </header>

      <main className="p-4 pb-24 space-y-4">
        {/* Community info card */}
        <div className="card-neo p-4">
          {community.description && (
            <p className="text-[var(--text-secondary)] mb-4">{community.description}</p>
          )}

          {/* Invite link section */}
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm text-[var(--text-muted)]">Invite link:</span>
              <div className="flex items-center gap-2">
                <code className="text-xs bg-[var(--bg-secondary)] border-2 border-black px-2 py-1 truncate max-w-[180px]">
                  {inviteLink.length > 35 ? `...${inviteLink.slice(-30)}` : inviteLink}
                </code>
                <button
                  onClick={copyInviteLink}
                  className="btn-neo p-2"
                  title="Copy invite link"
                >
                  {copiedLink ? (
                    <CheckCircleIcon size={16} className="text-green-600" />
                  ) : (
                    <CopyIcon size={16} />
                  )}
                </button>
              </div>
            </div>

            <button
              onClick={regenerateInvite}
              disabled={regenerating}
              className="btn-neo w-full flex items-center justify-center gap-2"
            >
              {regenerating ? (
                <>
                  <SpinnerIcon size={16} />
                  Regenerating...
                </>
              ) : (
                <>
                  <RefreshIcon size={16} />
                  Regenerate Invite Link
                </>
              )}
            </button>
          </div>
        </div>

        {/* Members section */}
        <div className="card-neo p-4">
          <h2 className="font-heading font-bold text-lg mb-3 flex items-center gap-2">
            <PeopleIcon size={20} />
            Members ({members.length})
          </h2>

          {members.length === 0 ? (
            <div className="text-center py-6 text-[var(--text-muted)]">
              <PeopleIcon size={32} className="mx-auto mb-2 opacity-50" />
              <p>No members yet</p>
              <p className="text-sm mt-1">Share the invite link to get started</p>
            </div>
          ) : (
            <ul className="space-y-3">
              {members.map((member) => {
                const { role, offers, seeks } = formatAssertions(member.assertions);

                return (
                  <li
                    key={member.person_id}
                    className="bg-[var(--bg-secondary)] border-2 border-black p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-3 flex-1 min-w-0">
                        {/* Avatar */}
                        <div className="w-10 h-10 flex-shrink-0 flex items-center justify-center text-sm font-bold border-2 border-black bg-mint">
                          {member.display_name.charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 className="font-semibold truncate">
                            {member.display_name}
                          </h3>
                          {role && (
                            <p className="text-sm text-[var(--text-secondary)] truncate mt-0.5">
                              {role}
                            </p>
                          )}
                        </div>
                      </div>
                      <span className="text-xs text-[var(--text-muted)] flex-shrink-0">
                        {new Date(member.created_at).toLocaleDateString()}
                      </span>
                    </div>

                    {(offers.length > 0 || seeks.length > 0) && (
                      <div className="mt-3 space-y-2">
                        {offers.length > 0 && (
                          <div>
                            <span className="text-xs text-[var(--text-muted)]">Can help with:</span>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {offers.map((offer, i) => (
                                <span
                                  key={i}
                                  className="badge-neo badge-neo-success text-xs"
                                >
                                  {offer}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        {seeks.length > 0 && (
                          <div>
                            <span className="text-xs text-[var(--text-muted)]">Looking for:</span>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {seeks.map((seek, i) => (
                                <span
                                  key={i}
                                  className="badge-neo badge-neo-primary text-xs"
                                >
                                  {seek}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </main>
    </div>
  );
}
