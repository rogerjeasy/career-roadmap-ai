// ── API error types ───────────────────────────────────────────────────────────

/** Error body from the backend — already camelCase-converted by the server middleware. */
export interface ApiErrorBody {
  errorCode: string;
  detail: string;
}

/** Thrown by the API client when the backend returns a structured error. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly errorCode: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ── User profile ──────────────────────────────────────────────────────────────
// All fields are camelCase — the conversion layer in client.ts translates
// snake_case from the backend automatically.

export interface NotificationPreferences {
  weeklyDigest: boolean;
  milestoneAlerts: boolean;
  marketAlerts: boolean;
}

export interface UserProfile {
  id: string;             // = firebaseUid (Firestore document ID)
  firebaseUid: string;
  email: string;
  displayName: string | null;
  photoUrl: string | null;
  /** Firebase provider ID: "password" | "google.com" | "github.com" */
  provider: string;
  emailVerified: boolean;
  isActive: boolean;
  /** Authorization role: "user" | "admin" | "superadmin". Drives admin-area access. */
  role: UserRole;
  notificationPreferences: NotificationPreferences;
  createdAt: string;
  updatedAt: string;
}

/** Authorization role mirrored from the Firebase custom claim. */
export type UserRole = "user" | "admin" | "superadmin";

/** Partial profile update — omitted fields are left unchanged. */
export interface UserUpdateInput {
  displayName?: string;
  notificationPreferences?: NotificationPreferences;
}

// ── Auth responses ────────────────────────────────────────────────────────────

export interface AuthResponse {
  user: UserProfile;
  idToken: string;
  refreshToken: string;
  expiresIn: number;
  tokenType: string;
}

export interface TokenRefreshResponse {
  idToken: string;
  refreshToken: string;
  expiresIn: number;
  tokenType: string;
}

// ── Pagination ────────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasNext: boolean;
}
