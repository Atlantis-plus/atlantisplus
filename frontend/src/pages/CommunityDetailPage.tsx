import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import type { Community, CommunityMember } from '../lib/api';
import { SpinnerIcon, PeopleIcon } from '../components/icons';

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
      <div className="page-container">
        <div className="flex items-center justify-center py-12">
          <SpinnerIcon size={32} className="text-[var(--accent-primary)]" />
        </div>
      </div>
    );
  }

  if (error || !community) {
    return (
      <div className="page-container">
        <div className="text-center py-12">
          <p className="text-[var(--text-error)] mb-4">{error || 'Community not found'}</p>
          <button
            onClick={onBack}
            className="px-4 py-2 bg-[var(--accent-primary)] text-white rounded-lg"
          >
            Back
          </button>
        </div>
      </div>
    );
  }

  const inviteLink = `https://t.me/atlantisplus_bot?start=join_${community.invite_code}`;

  return (
    <div className="page-container">
      {/* Header with back button */}
      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={onBack}
          className="p-2 rounded-lg hover:bg-[var(--bg-hover)] text-[var(--text-secondary)]"
        >
          ←
        </button>
        <h1 className="page-title flex-1">{community.name}</h1>
      </div>

      {/* Community info */}
      <div className="bg-[var(--bg-secondary)] rounded-xl p-4 border border-[var(--border-color)] mb-4">
        {community.description && (
          <p className="text-[var(--text-secondary)] mb-3">{community.description}</p>
        )}

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--text-muted)]">Invite link:</span>
            <div className="flex items-center gap-2">
              <code className="text-xs bg-[var(--bg-tertiary)] px-2 py-1 rounded">
                {inviteLink.length > 40 ? `...${inviteLink.slice(-35)}` : inviteLink}
              </code>
              <button
                onClick={copyInviteLink}
                className="px-2 py-1 text-xs bg-[var(--accent-primary)] text-white rounded"
              >
                {copiedLink ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--text-muted)]">Members:</span>
            <span className="text-sm font-medium">{members.length}</span>
          </div>

          <button
            onClick={regenerateInvite}
            disabled={regenerating}
            className="w-full mt-2 px-3 py-2 text-sm bg-[var(--bg-tertiary)] text-[var(--text-secondary)] rounded-lg hover:bg-[var(--bg-hover)] disabled:opacity-50"
          >
            {regenerating ? 'Regenerating...' : 'Regenerate Invite Link'}
          </button>
        </div>
      </div>

      {/* Members list */}
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-3 flex items-center gap-2">
          <PeopleIcon size={20} />
          Members ({members.length})
        </h2>

        {members.length === 0 ? (
          <div className="text-center py-8 text-[var(--text-muted)]">
            <p>No members yet</p>
            <p className="text-sm mt-1">Share the invite link to get started</p>
          </div>
        ) : (
          <div className="space-y-3">
            {members.map((member) => {
              const { role, offers, seeks } = formatAssertions(member.assertions);

              return (
                <div
                  key={member.person_id}
                  className="bg-[var(--bg-secondary)] rounded-xl p-4 border border-[var(--border-color)]"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-semibold text-[var(--text-primary)]">
                        {member.display_name}
                      </h3>
                      {role && (
                        <p className="text-sm text-[var(--text-secondary)] mt-1">
                          {role}
                        </p>
                      )}
                    </div>
                    <span className="text-xs text-[var(--text-muted)]">
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
                                className="px-2 py-0.5 text-xs bg-green-500/10 text-green-600 rounded-full"
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
                                className="px-2 py-0.5 text-xs bg-blue-500/10 text-blue-600 rounded-full"
                              >
                                {seek}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
