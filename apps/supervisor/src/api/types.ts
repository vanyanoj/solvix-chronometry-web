/**
 * Типы API Solvix Chronometry Edge.
 * Сняты 1:1 с Pydantic-схем бэкенда (apps/backend/src/solvix_chronometry).
 * При изменении схем на бэке — правим здесь.
 */

// === Енумы (models/enums.py) ===

export type UserRole = "warehouse" | "supervisor" | "operator";

export type NfcBadgeStatus = "free" | "bound" | "lost";

export type ShiftClosedBy = "self" | "supervisor";

export type EventType =
  | "scan_in"
  | "start"
  | "stop"
  | "scan_out"
  | "break_start"
  | "break_end"
  | "error"
  | "interrupted"
  | "anomaly";

export type PartStatus = "pending" | "active" | "absorbed";

// === auth (auth/schemas.py) ===

export interface LoginRequest {
  /** Код пропуска ИЛИ UID именного NFC-бейджа. */
  pass_code: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  /** Срок жизни токена в секундах (по умолчанию 12 ч). */
  expires_in: number;
}

export interface CurrentUser {
  id: string;
  full_name: string;
  role: UserRole;
}

// === users (api/users.py) ===

export interface User {
  id: string;
  full_name: string;
  role: UserRole;
  active: boolean;
}

// === badges (api/badges.py) ===

export interface Badge {
  id: string;
  uid: string;
  status: NfcBadgeStatus;
}

// === shifts (api/shifts.py) ===

export interface CreateShiftRequest {
  user_id: string;
  badge_id: string;
  station_id: string;
}

export interface Shift {
  id: string;
  user_id: string;
  user_full_name: string;
  badge_id: string;
  badge_uid: string;
  station_id: string;
  station_name: string;
  bound_at: string;
  unbound_at: string | null;
  closed_by: ShiftClosedBy | null;
}

// === dashboard (api/dashboard.py) ===

export interface OperatorSnapshot {
  id: string;
  full_name: string;
}

export interface LastEventSnapshot {
  type: string;
  at: string;
  part_id: string | null;
}

export interface StationSnapshot {
  id: string;
  name: string;
  operator: OperatorSnapshot | null;
  active_shift_id: string | null;
  last_event: LastEventSnapshot | null;
}

export interface IncidentItem {
  id: string;
  timestamp: string;
  event_type: EventType;
  station_id: string;
  station_name: string;
  part_id: string | null;
  shift_id: string | null;
  details: Record<string, unknown> | null;
}

// === stations (api/stations.py) ===

export interface CommandResponse {
  command_id: string;
  station_id: string;
  command: string;
  status: string;
}

// === processes (api/processes.py) ===

export interface Process {
  id: string;
  line_id: string | null;
  input_type_1: string;
  input_type_2: string;
  output_type: string;
  station_hint: string | null;
  nominal_duration_sec: number;
  anomaly_threshold_pct: number;
  valid_from: string;
}

export interface CreateProcessRequest {
  line_id: string;
  input_type_1: string;
  input_type_2: string;
  output_type: string;
  station_hint: string;
  nominal_duration_sec: number;
  anomaly_threshold_pct?: number;
}

export interface UpdateProcessRequest {
  input_type_1?: string;
  input_type_2?: string;
  output_type?: string;
  station_hint?: string;
  nominal_duration_sec?: number;
  anomaly_threshold_pct?: number;
}

export interface TopologyNode {
  station_id: string;
  station_name: string;
  level: number;
  process_ids: string[];
  input_types: string[];
  output_types: string[];
  fed_by: string[];
  feeds_into: string[];
}

export interface Topology {
  line_id: string;
  line_name: string;
  nodes: TopologyNode[];
  base_part_types: string[];
  final_output_types: string[];
  max_level: number;
  warnings: string[];
}

// === lines (api/lines.py) ===

export interface Line {
  id: string;
  workshop_id: string;
  name: string;
  station_count: number;
  active_station_count: number;
  process_count: number;
  has_topology: boolean;
}

// === WebSocket (ws/hub.py → broadcast) ===

export interface WsEventMessage {
  type: "event";
  id: string;
  station_id: string;
  event_type: string;
  timestamp: string;
  part_id: string | null;
}
