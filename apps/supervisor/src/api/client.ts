import type {
  Badge,
  CreateProcessRequest,
  CreateShiftRequest,
  CurrentUser,
  IncidentItem,
  Line,
  LoginRequest,
  NfcBadgeStatus,
  Process,
  Shift,
  StationSnapshot,
  TokenResponse,
  Topology,
  UpdateProcessRequest,
  User,
  UserRole,
} from "./types";

const BASE = "/api/v1";
const TOKEN_KEY = "solvix.token";

/** Ошибка API с HTTP-статусом — по нему различаем 401/403/409. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// === Токен ===
// sessionStorage: живёт до закрытия вкладки. Смена — 12 ч, терминал старшего
// стоит в цеху, поэтому переживать перезагрузку страницы токен должен.

export const tokenStore = {
  get(): string | null {
    try {
      return sessionStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string) {
    try {
      sessionStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* приватный режим — работаем без персистентности */
    }
  },
  clear() {
    try {
      sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  },
};

/** Колбэк на протухший токен — вешается роутером, чтобы выкинуть на вход. */
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  /** Не слать Authorization (для /auth/login). */
  anonymous?: boolean;
  signal?: AbortSignal;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, anonymous = false, signal } = opts;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (!anonymous) {
    const token = tokenStore.get();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch {
    // fetch падает только на сетевом уровне — бэк недоступен.
    throw new ApiError(0, "Сервер недоступен. Проверьте подключение к цеховой сети.");
  }

  if (res.status === 401 && !anonymous) {
    tokenStore.clear();
    onUnauthorized?.();
  }

  if (!res.ok) {
    throw new ApiError(res.status, await extractError(res));
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** FastAPI отдаёт {detail: string} либо {detail: [{msg, loc}]} при 422. */
async function extractError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    const detail = data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((d: { msg?: string }) => d.msg ?? "").filter(Boolean).join("; ");
    }
  } catch {
    /* тело не JSON */
  }
  return `Ошибка ${res.status}`;
}

// === Эндпоинты ===

export const api = {
  auth: {
    /** Вход по коду пропуска ИЛИ по UID именного бейджа (бэк принимает оба). */
    login: (pass_code: string) =>
      request<TokenResponse>("/auth/login", {
        method: "POST",
        body: { pass_code } satisfies LoginRequest,
        anonymous: true,
      }),
    me: () => request<CurrentUser>("/auth/me"),
  },

  users: {
    list: (params: { role?: UserRole; active?: boolean; limit?: number; offset?: number } = {}) =>
      request<User[]>(`/users${query(params)}`),
  },

  badges: {
    list: (params: { status?: NfcBadgeStatus; limit?: number; offset?: number } = {}) =>
      request<Badge[]>(`/badges${query(params)}`),
    create: (uid: string) => request<Badge>("/badges", { method: "POST", body: { uid } }),
    updateStatus: (badgeId: string, status: NfcBadgeStatus) =>
      request<Badge>(`/badges/${badgeId}`, { method: "PATCH", body: { status } }),
  },

  shifts: {
    create: (body: CreateShiftRequest) => request<Shift>("/shifts", { method: "POST", body }),
    forceClose: (shiftId: string) =>
      request<Shift>(`/shifts/${shiftId}/force_close`, { method: "POST" }),
  },

  dashboard: {
    stations: () => request<StationSnapshot[]>("/dashboard/stations"),
    incidents: (params: { since?: string; limit?: number; offset?: number } = {}) =>
      request<IncidentItem[]>(`/dashboard/incidents${query(params)}`),
  },

  processes: {
    list: (params: { line_id?: string; station_id?: string; limit?: number; offset?: number } = {}) =>
      request<Process[]>(`/processes${query(params)}`),
    create: (body: CreateProcessRequest) =>
      request<Process>("/processes", { method: "POST", body }),
    update: (processId: string, body: UpdateProcessRequest) =>
      request<Process>(`/processes/${processId}`, { method: "PATCH", body }),
    remove: (processId: string) =>
      request<void>(`/processes/${processId}`, { method: "DELETE" }),
    topology: (lineId: string) => request<Topology>(`/processes/topology/${lineId}`),
  },

  lines: {
    list: (params: { workshop_id?: string } = {}) =>
      request<Line[]>(`/lines${query(params)}`),
    get: (lineId: string) => request<Line>(`/lines/${lineId}`),
  },
};

function query(params: Record<string, string | number | boolean | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length > 0 ? `?${parts.join("&")}` : "";
}
