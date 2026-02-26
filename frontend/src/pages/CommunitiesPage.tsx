import type { Community } from '../lib/api';
import { SpinnerIcon, PeopleIcon } from '../components/icons';

interface CommunitiesPageProps {
  onSelectCommunity: (communityId: string) => void;
  communities?: Community[];
  loading?: boolean;
}

export function CommunitiesPage({ onSelectCommunity, communities = [], loading = false }: CommunitiesPageProps) {

  const copyInviteLink = (inviteCode: string) => {
    const link = `https://t.me/atlantisplus_bot?start=join_${inviteCode}`;
    navigator.clipboard.writeText(link);
    // Could add a toast notification here
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

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">My Communities</h1>
        <p className="text-[var(--text-muted)] text-sm mt-1">
          Manage your communities and view members
        </p>
      </div>

      {communities.length === 0 ? (
        <div className="text-center py-12">
          <PeopleIcon size={48} className="mx-auto mb-4 text-[var(--text-muted)]" />
          <p className="text-[var(--text-muted)] mb-2">No communities yet</p>
          <p className="text-[var(--text-muted)] text-sm">
            Use <code>/newcommunity</code> in the bot to create one
          </p>
        </div>
      ) : (
        <div className="space-y-3 mt-4">
          {communities.map((community) => (
            <div
              key={community.community_id}
              className="bg-[var(--bg-secondary)] rounded-xl p-4 border border-[var(--border-color)]"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1" onClick={() => onSelectCommunity(community.community_id)}>
                  <h3 className="font-semibold text-[var(--text-primary)]">
                    {community.name}
                  </h3>
                  {community.description && (
                    <p className="text-sm text-[var(--text-muted)] mt-1">
                      {community.description}
                    </p>
                  )}
                  <div className="flex items-center gap-4 mt-2 text-sm text-[var(--text-secondary)]">
                    <span className="flex items-center gap-1">
                      <PeopleIcon size={14} />
                      {community.member_count} member{community.member_count !== 1 ? 's' : ''}
                    </span>
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    copyInviteLink(community.invite_code);
                  }}
                  className="px-3 py-1.5 text-xs bg-[var(--bg-tertiary)] text-[var(--text-secondary)] rounded-lg hover:bg-[var(--bg-hover)]"
                  title="Copy invite link"
                >
                  Copy Link
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
