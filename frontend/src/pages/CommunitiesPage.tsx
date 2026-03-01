import { useState } from 'react';
import type { Community } from '../lib/api';
import { SpinnerIcon, PeopleIcon, ChevronRightIcon, CopyIcon, CheckCircleIcon } from '../components/icons';

interface CommunitiesPageProps {
  onSelectCommunity: (communityId: string) => void;
  communities?: Community[];
  loading?: boolean;
}

export function CommunitiesPage({ onSelectCommunity, communities = [], loading = false }: CommunitiesPageProps) {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const copyInviteLink = (communityId: string, inviteCode: string) => {
    const link = `https://t.me/atlantisplus_bot?start=join_${inviteCode}`;
    navigator.clipboard.writeText(link);
    setCopiedId(communityId);
    setTimeout(() => setCopiedId(null), 2000);
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

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-[var(--bg-primary)] border-b-3 border-black p-4">
        <h1 className="font-heading text-2xl font-bold">Communities</h1>
        <p className="text-sm text-[var(--text-muted)]">
          {communities.length} communit{communities.length !== 1 ? 'ies' : 'y'}
        </p>
      </header>

      <main className="p-4 pb-24 space-y-4">
        {communities.length === 0 ? (
          <div className="card-neo p-8 text-center">
            <PeopleIcon size={48} className="mx-auto mb-4 text-[var(--text-muted)]" />
            <p className="text-[var(--text-muted)] mb-2">No communities yet</p>
            <p className="text-[var(--text-muted)] text-sm">
              Use <code className="px-1.5 py-0.5 bg-[var(--bg-secondary)] border border-black text-xs">/newcommunity</code> in the bot to create one
            </p>
          </div>
        ) : (
          <ul className="space-y-3">
            {communities.map((community) => (
              <li
                key={community.community_id}
                className="card-neo-interactive"
              >
                <div className="flex items-start gap-3">
                  {/* Avatar */}
                  <div className="w-12 h-12 flex-shrink-0 flex items-center justify-center text-xl font-bold border-2 border-black bg-lavender">
                    {community.name.charAt(0).toUpperCase()}
                  </div>

                  {/* Info */}
                  <div
                    className="flex-1 min-w-0 cursor-pointer"
                    onClick={() => onSelectCommunity(community.community_id)}
                  >
                    <h3 className="font-semibold truncate">
                      {community.name}
                    </h3>
                    {community.description && (
                      <p className="text-sm text-[var(--text-muted)] truncate mt-0.5">
                        {community.description}
                      </p>
                    )}
                    <div className="flex items-center gap-1 mt-1.5 text-sm text-[var(--text-secondary)]">
                      <PeopleIcon size={14} />
                      <span>{community.member_count} member{community.member_count !== 1 ? 's' : ''}</span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        copyInviteLink(community.community_id, community.invite_code);
                      }}
                      className="btn-neo p-2"
                      title="Copy invite link"
                    >
                      {copiedId === community.community_id ? (
                        <CheckCircleIcon size={18} className="text-green-600" />
                      ) : (
                        <CopyIcon size={18} />
                      )}
                    </button>
                    <button
                      onClick={() => onSelectCommunity(community.community_id)}
                      className="btn-neo p-2"
                      title="View community"
                    >
                      <ChevronRightIcon size={18} />
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
