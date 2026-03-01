import React from 'react';

/**
 * Icon System for Atlantis Plus Mini App
 *
 * All icons use:
 * - currentColor for fill/stroke (inherits text color)
 * - 2px stroke width for Neobrutalism consistency
 * - Default 24px size
 * - Simple, bold shapes recognizable at 16-24px
 */

interface IconProps {
  className?: string;
  size?: number | string;
  strokeWidth?: number;
  style?: React.CSSProperties;
}

const defaultProps: Required<Pick<IconProps, 'size' | 'strokeWidth'>> = {
  size: 24,
  strokeWidth: 2,
};

// ============================================
// NAVIGATION ICONS
// ============================================

/** Group of people silhouettes - replaces 👥 */
export const PeopleIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    {/* Left person */}
    <circle cx="9" cy="7" r="3" />
    <path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
    {/* Right person (smaller, behind) */}
    <circle cx="17" cy="8" r="2.5" />
    <path d="M21 21v-1.5a3 3 0 0 0-3-3h-1" />
  </svg>
);

/** Document with lines - replaces 📝 */
export const NotesIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="8" y1="13" x2="16" y2="13" />
    <line x1="8" y1="17" x2="14" y2="17" />
  </svg>
);

/** Speech bubble - replaces 💬 */
export const ChatIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
  </svg>
);

/** Download arrow into tray - replaces 📥 */
export const ImportIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

// ============================================
// ACTION ICONS
// ============================================

/** Microphone - replaces 🎤 */
export const MicrophoneIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="23" />
    <line x1="8" y1="23" x2="16" y2="23" />
  </svg>
);

/** Pencil/edit - replaces ✏️ */
export const TextIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
  </svg>
);

/** Magnifying glass - replaces 🔍 */
export const SearchIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

/** Arrow pointing right - replaces ➤ */
export const SendIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

/** Clipboard/list - replaces 📋 */
export const HistoryIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

/** Plus symbol - replaces ✨ for new chat */
export const PlusIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);

/** Chevron pointing right - for navigation */
export const ChevronRightIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <polyline points="9 18 15 12 9 6" />
  </svg>
);

/** Chevron pointing left - for back button */
export const ChevronLeftIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <polyline points="15 18 9 12 15 6" />
  </svg>
);

/** Chevron pointing down - for dropdowns */
export const ChevronDownIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <polyline points="6 9 12 15 18 9" />
  </svg>
);

/** Trash can - for delete actions */
export const TrashIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    <line x1="10" y1="11" x2="10" y2="17" />
    <line x1="14" y1="11" x2="14" y2="17" />
  </svg>
);

/** External link - for opening links */
export const ExternalLinkIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <polyline points="15 3 21 3 21 9" />
    <line x1="10" y1="14" x2="21" y2="3" />
  </svg>
);

// ============================================
// STATUS ICONS
// ============================================

/** Check in circle - replaces ✅ */
export const CheckCircleIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
);

/** X in circle - replaces ❌ */
export const ErrorCircleIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <circle cx="12" cy="12" r="10" />
    <line x1="15" y1="9" x2="9" y2="15" />
    <line x1="9" y1="9" x2="15" y2="15" />
  </svg>
);

/** Headphones - replaces 🎧 for transcribing */
export const HeadphonesIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M3 18v-6a9 9 0 0 1 18 0v6" />
    <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z" />
  </svg>
);

/** Scan/processing - replaces 🔍 for extracting */
export const ScanIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    {/* Corner brackets */}
    <path d="M3 7V5a2 2 0 0 1 2-2h2" />
    <path d="M17 3h2a2 2 0 0 1 2 2v2" />
    <path d="M21 17v2a2 2 0 0 1-2 2h-2" />
    <path d="M7 21H5a2 2 0 0 1-2-2v-2" />
    {/* Scan line */}
    <line x1="7" y1="12" x2="17" y2="12" />
  </svg>
);

/** Clock - replaces ⏳ for pending */
export const ClockIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

/** Spinner - for loading states (use CSS animation) */
export const SpinnerIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={{ animation: 'spin 1s linear infinite', ...style }}
  >
    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
  </svg>
);

// ============================================
// CONTACT TYPE ICONS
// ============================================

/** Email envelope - replaces 📧 */
export const EmailIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
    <polyline points="22,6 12,13 2,6" />
  </svg>
);

/** LinkedIn logo simplified - replaces 🔗 */
export const LinkedInIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
    <rect x="2" y="9" width="4" height="12" />
    <circle cx="4" cy="4" r="2" />
  </svg>
);

/** Telegram paper plane - replaces ✈️ */
export const TelegramIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M22 2L11 13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

/** Phone - replaces 📱 */
export const PhoneIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
  </svg>
);

/** Calendar - replaces 📅 */
export const CalendarIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
    <line x1="16" y1="2" x2="16" y2="6" />
    <line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
  </svg>
);

/** Single user - replaces 📝 for name variants */
export const UserIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

// ============================================
// OTHER ICONS
// ============================================

/** Robot - replaces 🤖 for AI assistant */
export const RobotIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    {/* Head */}
    <rect x="4" y="6" width="16" height="12" rx="2" />
    {/* Antenna */}
    <line x1="12" y1="6" x2="12" y2="2" />
    <circle cx="12" cy="2" r="1" fill="currentColor" />
    {/* Eyes */}
    <circle cx="9" cy="11" r="1.5" />
    <circle cx="15" cy="11" r="1.5" />
    {/* Mouth */}
    <path d="M9 15h6" />
    {/* Ears */}
    <line x1="4" y1="10" x2="2" y2="10" />
    <line x1="22" y1="10" x2="20" y2="10" />
  </svg>
);

/** Refresh/sync - replaces 🔄 */
export const RefreshIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <polyline points="23 4 23 10 17 10" />
    <polyline points="1 20 1 14 7 14" />
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
  </svg>
);

/** Star - for recommendations */
export const StarIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);

/** X/close - for close buttons */
export const XIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

/** Info circle - for information */
export const InfoIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="16" x2="12" y2="12" />
    <line x1="12" y1="8" x2="12.01" y2="8" />
  </svg>
);

/** Enrichment/sparkles - for PDL enrichment */
export const EnrichIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    {/* Main sparkle */}
    <path d="M12 3v4m0 10v4M3 12h4m10 0h4" />
    {/* Diagonal sparkles */}
    <path d="M5.64 5.64l2.83 2.83m7.07 7.07l2.83 2.83M5.64 18.36l2.83-2.83m7.07-7.07l2.83-2.83" />
    {/* Center dot */}
    <circle cx="12" cy="12" r="2" fill="currentColor" />
  </svg>
);

/** Copy - for clipboard copy */
export const CopyIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </svg>
);

/** Upload - for file upload */
export const UploadIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

/** Community/group - for communities section */
export const CommunityIcon: React.FC<IconProps> = ({
  className,
  size = defaultProps.size,
  strokeWidth = defaultProps.strokeWidth,
  style
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    {/* House/home shape for community */}
    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9z" />
    {/* People inside */}
    <circle cx="9" cy="13" r="2" />
    <circle cx="15" cy="13" r="2" />
    <path d="M9 18v-1a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1" />
  </svg>
);

