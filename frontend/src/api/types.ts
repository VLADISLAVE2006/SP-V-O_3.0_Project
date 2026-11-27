// ============================================================================
// API Types - Based on OpenAPI schema from backend/openapi.yaml
// ============================================================================

// --- Auth ---
export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  nickname: string;
  password: string;
}

export interface RefreshRequest {
  refresh: string;
}

export interface Tokens {
  access: string;
  refresh: string;
}

export interface AuthResult {
  access: string;
  refresh: string;
  profile: Profile;
}

// --- User & Profile ---
export interface PublicUser {
  id: number;
  nickname: string;
  avatar_url: string | null;
  created_at: string;
}

export interface Profile {
  id: number;
  nickname: string;
  avatar_url: string | null;
  created_at: string;
  email: string;
  role: string;
  is_banned: boolean;
  polls_count: number;
  warnings_count: number;
}

export interface PatchedNicknameRequest {
  nickname: string;
}

export interface PasswordRequest {
  old_password: string;
  new_password: string;
  new_password_confirm: string;
}

export interface UserPage {
  items: Profile[];
  total: number;
  has_more: boolean;
}

// --- Enums ---
export type AccessMode = 'anonymous' | 'registered';
export type Visibility = 'public' | 'link';
export type PollStatus = 'draft' | 'active' | 'finished' | 'scheduled';
export type QuestionType = 'single' | 'multiple' | 'scale';
export type ReviewStatus = 'accepted' | 'rejected';
export type Role = 'user' | 'moderator' | 'admin';

// --- Poll ---
export interface Option {
  id: number;
  text: string;
}

export interface OptionInputRequest {
  text: string;
}

export interface OptionResult {
  id: number;
  text: string;
  votes: number;
  percent: number;
}

export interface Question {
  id: number;
  text: string;
  type: QuestionType;
  min_choices: number;
  max_choices: number;
  position: number;
  options: Option[];
}

export interface QuestionInputRequest {
  text: string;
  type: QuestionType;
  min_choices?: number;
  max_choices?: number;
  options?: OptionInputRequest[];
}

export interface QuestionResult {
  id: number;
  text: string;
  type: string;
  options: OptionResult[];
}

export interface PollInputRequest {
  title: string;
  description?: string | null;
  access_mode: AccessMode;
  visibility: Visibility;
  allow_revote: boolean;
  comments_enabled: boolean;
  questions: QuestionInputRequest[];
}

export interface PatchedPollInputRequest {
  title?: string;
  description?: string | null;
  access_mode?: AccessMode;
  visibility?: Visibility;
  allow_revote?: boolean;
  comments_enabled?: boolean;
  ends_at?: string | null;
  max_votes?: number | null;
  questions?: QuestionInputRequest[];
}

export interface PollSummary {
  id: number;
  slug: string;
  title: string;
  description: string | null;
  status: PollStatus;
  access_mode: AccessMode;
  visibility: Visibility;
  author: PublicUser;
  responses_count: number;
  created_at: string;
  ends_at: string | null;
}

export interface PollDetail extends PollSummary {
  allow_revote: boolean;
  comments_enabled: boolean;
  starts_at: string | null;
  max_votes: number | null;
  updated_at: string;
  published_at: string | null;
  questions: Question[];
}

export interface PublishRequest {
  starts_at?: string | null;
}

// --- Vote ---
export interface MyAnswer {
  question_id: number;
  option_ids: number[];
}

export interface VoteAnswerRequest {
  question_id: number;
  option_ids: number[];
}

export interface VoteRequest {
  answers: VoteAnswerRequest[];
}

export interface Results {
  total_responses: number;
  questions: QuestionResult[];
}

// --- Voter ---
export interface Voter {
  user: PublicUser;
  answers: MyAnswer[];
}

export interface VoterPage {
  items: Voter[];
  total: number;
  has_more: boolean;
}

// --- Comments ---
export interface Comment {
  id: number;
  poll_id: number;
  author: PublicUser;
  parent_id: number | null;
  text: string;
  likes_count: number;
  created_at: string;
  updated_at: string;
}

export interface CommentInputRequest {
  text: string;
  parent_id?: number | null;
}

export interface PatchedCommentEditRequest {
  text: string;
}

export interface CommentPage {
  items: Comment[];
  total: number;
  has_more: boolean;
}

export interface LikeResult {
  liked: boolean;
  likes_count: number;
}

// --- Reports ---
export interface ModerationDeleteRequest {
  is_violation?: boolean;
  comment?: string;
}

export interface PatchedReviewRequest {
  status: ReviewStatus;
}

export interface Report {
  id: number;
  reason: string;
  poll_slug: string | null;
  comment_id: number | null;
  status: ReviewStatus;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: number | null;
}

export interface ReportPage {
  items: Report[];
  total: number;
  has_more: boolean;
}

// --- Bans & Warnings ---
export interface Ban {
  id: number;
  user_id: number;
  banned_by: number | null;
  is_auto: boolean;
  reason: string | null;
  banned_at: string;
  unbanned_at: string | null;
}

export interface BanInputRequest {
  reason?: string | null;
}

export interface BanPage {
  items: Ban[];
  total: number;
  has_more: boolean;
}

export interface Warning {
  id: number;
  user_id: number;
  moderator_id: number | null;
  reason: string;
  created_at: string;
}

export interface WarningPage {
  items: Warning[];
  total: number;
  has_more: boolean;
}

export interface WarningResult {
  warnings_count: number;
  auto_banned: boolean;
}

// --- Avatar ---
export interface AvatarRequest {
  avatar: File;
}

// --- Errors ---
export interface ApiError {
  detail: string;
}

export interface ValidationErrors {
  [key: string]: string | string[] | ValidationErrors | undefined;
  non_field_errors?: string[];
}

// --- Pagination ---
export interface PaginationParams {
  limit?: number;
  offset?: number;
  q?: string;
  status?: string;
  sort?: string;
}