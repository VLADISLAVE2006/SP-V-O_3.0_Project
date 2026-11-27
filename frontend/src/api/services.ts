import {
  apiClient,
  saveTokens,
  clearTokens,
  setLogoutCallback,
} from './client';
import type {
  AuthResult,
  LoginRequest,
  RegisterRequest,
  Tokens,
  Profile,
  PatchedNicknameRequest,
  PasswordRequest,
  PollInputRequest,
  PatchedPollInputRequest,
  VoteRequest,
  CommentInputRequest,
  PatchedCommentEditRequest,
  ModerationDeleteRequest,
  PatchedReviewRequest,
  BanInputRequest,
  PaginationParams,
} from './types';

// ============================================================================
// Auth
// ============================================================================

export const authApi = {
  register: (data: RegisterRequest): Promise<AuthResult> =>
    apiClient.post('/auth/register', data).then((r) => r.data),

  login: (data: LoginRequest): Promise<AuthResult> =>
    apiClient.post('/auth/login', data).then((r) => {
      saveTokens({ access: r.data.access, refresh: r.data.refresh });
      return r.data;
    }),

  logout: (): Promise<void> =>
    apiClient
      .post('/auth/logout', { refresh: '' })
      .then(() => {
        clearTokens();
      })
      .catch(() => {
        clearTokens();
      }),

  refresh: (): Promise<Tokens> =>
    apiClient.post('/auth/refresh', { refresh: '' }).then((r) => {
      saveTokens(r.data);
      return r.data;
    }),

  me: (): Promise<Profile> => apiClient.get('/users/me').then((r) => r.data),
};

setLogoutCallback(() => {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('auth:logout'));
  }
});

// ============================================================================
// Users
// ============================================================================

export const usersApi = {
  getProfile: (id: number): Promise<Profile> =>
    apiClient.get(`/users/${id}`).then((r) => r.data),

  updateNickname: (data: PatchedNicknameRequest): Promise<Profile> =>
    apiClient.patch('/users/me/nickname', data).then((r) => r.data),

  changePassword: (data: PasswordRequest): Promise<Tokens> =>
    apiClient.post('/users/me/password', data).then((r) => r.data),

  uploadAvatar: (formData: FormData): Promise<{ avatar_url: string }> =>
    apiClient
      .post('/users/me/avatar', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data),

  list: (params?: PaginationParams) =>
    apiClient.get('/admin/users', { params }).then((r) => r.data),
};

// ============================================================================
// Polls
// ============================================================================

export const pollsApi = {
  list: (params?: PaginationParams) =>
    apiClient.get('/polls', { params }).then((r) => r.data),

  create: (data: PollInputRequest) =>
    apiClient.post('/polls', data).then((r) => r.data),

  get: (slug: string) =>
    apiClient.get(`/polls/${slug}`).then((r) => r.data),

  update: (slug: string, data: PatchedPollInputRequest) =>
    apiClient.patch(`/polls/${slug}`, data).then((r) => r.data),

  publish: (slug: string, data?: { starts_at?: string | null }) =>
    apiClient.post(`/polls/${slug}/publish`, data ?? {}).then((r) => r.data),

  close: (slug: string) =>
    apiClient.post(`/polls/${slug}/close`, {}).then((r) => r.data),

  vote: (slug: string, data: VoteRequest) =>
    apiClient.post(`/polls/${slug}/vote`, data).then((r) => r.data),

  results: (slug: string) =>
    apiClient.get(`/polls/${slug}/results`).then((r) => r.data),

  voters: (slug: string, params?: PaginationParams) =>
    apiClient.get(`/polls/${slug}/voters`, { params }).then((r) => r.data),

  export: (slug: string, format: 'csv' | 'xlsx' | 'pdf') =>
    apiClient
      .get(`/polls/${slug}/export`, {
        params: { format },
        responseType: 'blob',
      })
      .then((r) => r.data as Blob),
};

// ============================================================================
// Comments
// ============================================================================

export const commentsApi = {
  list: (slug: string, params?: PaginationParams) =>
    apiClient.get(`/polls/${slug}/comments`, { params }).then((r) => r.data),

  create: (slug: string, data: CommentInputRequest) =>
    apiClient.post(`/polls/${slug}/comments`, data).then((r) => r.data),

  update: (id: number, data: PatchedCommentEditRequest) =>
    apiClient.patch(`/comments/${id}`, data).then((r) => r.data),

  remove: (id: number) =>
    apiClient.delete(`/comments/${id}`).then(() => undefined),

  like: (id: number) =>
    apiClient.post(`/comments/${id}/like`).then((r) => r.data),

  unlike: (id: number) =>
    apiClient.delete(`/comments/${id}/like`).then(() => undefined),
};

// ============================================================================
// Reports
// ============================================================================

export const reportsApi = {
  create: (data: { reason: string; poll_slug?: string; comment_id?: number }) =>
    apiClient.post('/reports', data).then((r) => r.data),

  list: (params?: PaginationParams & { status?: string }) =>
    apiClient.get('/moderation/reports', { params }).then((r) => r.data),

  review: (id: number, data: PatchedReviewRequest) =>
    apiClient.patch(`/moderation/reports/${id}`, data).then((r) => r.data),
};

// ============================================================================
// Admin / Moderation
// ============================================================================

export const adminApi = {
  banUser: (id: number, data: BanInputRequest) =>
    apiClient.post(`/admin/users/${id}/ban`, data).then((r) => r.data),

  unbanUser: (id: number) =>
    apiClient.post(`/admin/users/${id}/unban`).then((r) => r.data),

  getBans: (id: number, params?: PaginationParams) =>
    apiClient.get(`/admin/users/${id}/bans`, { params }).then((r) => r.data),

  updateRole: (id: number, data: { role: string }) =>
    apiClient.patch(`/admin/users/${id}/role`, data).then((r) => r.data),

  getWarnings: (id: number, params?: PaginationParams) =>
    apiClient.get(`/moderation/users/${id}/warnings`, { params }).then((r) => r.data),

  moderateCommentDelete: (id: number, data: ModerationDeleteRequest) =>
    apiClient.post(`/moderation/comments/${id}/delete`, data).then(() => undefined),

  moderatePollDelete: (slug: string, data: ModerationDeleteRequest) =>
    apiClient.post(`/moderation/polls/${slug}/delete`, data).then(() => undefined),
};

// ============================================================================
// Health
// ============================================================================

export const healthApi = {
  check: () => apiClient.get('/health').then((r) => r.data),
};