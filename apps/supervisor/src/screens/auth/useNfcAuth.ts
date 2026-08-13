import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/api/client";
import { useAuth } from "@/api/AuthContext";

/** Состояния считывателя на экране входа. */
export type AuthState =
  | "waiting" // ожидание бейджа
  | "detected" // бейдж обнаружен, читаем UID
  | "checking" // проверка доступа на бэке
  | "granted" // доступ разрешён
  | "unknown" // бейдж не найден в системе
  | "denied" // роль не supervisor
  | "error"; // ридер / сеть

export interface AuthStateView {
  color: string;
  iconBg: string;
  title: string;
  hint: string;
}

const V = {
  ok: { color: "var(--fl-ok)", iconBg: "var(--fl-ok-soft)" },
  info: { color: "var(--fl-info)", iconBg: "var(--fl-info-soft)" },
  warn: { color: "var(--fl-warn)", iconBg: "var(--fl-warn-soft)" },
  danger: { color: "var(--fl-danger)", iconBg: "var(--fl-danger-soft)" },
};

const BASE_VIEW: Record<AuthState, AuthStateView> = {
  waiting: { ...V.ok, title: "Ожидание бейджа…", hint: "Поднесите бейдж к области считывания" },
  detected: { ...V.info, title: "Бейдж обнаружен", hint: "Считываем идентификатор…" },
  checking: { ...V.warn, title: "Проверка доступа", hint: "Сверяем права старшего смены…" },
  granted: { ...V.ok, title: "Доступ разрешён", hint: "Входим в систему…" },
  unknown: {
    ...V.danger,
    title: "Бейдж не распознан",
    hint: "Бейдж не зарегистрирован в системе",
  },
  denied: {
    ...V.danger,
    title: "Доступ запрещён",
    hint: "У этого бейджа нет прав старшего смены",
  },
  error: { ...V.danger, title: "Ошибка считывателя", hint: "Проверьте связь и повторите" },
};

/** Сколько держать сообщение об отказе перед возвратом в ожидание. */
const RESET_MS = 3200;

/**
 * Вход старшего смены.
 *
 * Основной путь — именной NFC-бейдж: его UID хранится у пользователя как
 * код доступа, поэтому бэк принимает его тем же `POST /auth/login`
 * (поле `pass_code` описано как «Код пропуска / UID NFC-бейджа»).
 *
 * Запасной путь — ручной ввод кода: если бейдж забыт или ридер неисправен.
 */
export function useNfcAuth() {
  const { login } = useAuth();
  const [state, setState] = useState<AuthState>("waiting");
  const [errorText, setErrorText] = useState<string | null>(null);
  const resetTimer = useRef<ReturnType<typeof setTimeout>>();

  const reset = useCallback(() => {
    setState("waiting");
    setErrorText(null);
  }, []);

  /** Единая точка входа: и для UID бейджа, и для введённого кода. */
  const submitCode = useCallback(
    async (code: string, { fromBadge = false }: { fromBadge?: boolean } = {}) => {
      if (!code.trim()) return;
      setErrorText(null);
      if (fromBadge) {
        setState("detected");
        // Пауза, чтобы состояние «бейдж обнаружен» было заметно глазу.
        await new Promise((r) => setTimeout(r, 400));
      }
      setState("checking");
      try {
        await login(code.trim());
        setState("granted");
        // Навигацию делает экран — по появлению user в контексте.
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.status === 401) setState("unknown");
          else if (e.status === 403) setState("denied");
          else {
            setState("error");
            setErrorText(e.message);
          }
        } else {
          setState("error");
          setErrorText("Неизвестная ошибка");
        }
      }
    },
    [login],
  );

  /**
   * Симуляция поднесения бейджа (клик по зоне считывания).
   * TODO(nfc): заменить на событие реального ридера — ESP32 + PN532
   * публикует UID в MQTT, бэк форвардит его на терминал старшего.
   */
  const simulateBadge = useCallback(() => {
    if (state !== "waiting") return;
    void submitCode("04A3F7B9", { fromBadge: true });
  }, [state, submitCode]);

  // Отказы сами возвращают экран в ожидание.
  useEffect(() => {
    if (state === "unknown" || state === "denied" || state === "error") {
      resetTimer.current = setTimeout(reset, RESET_MS);
      return () => clearTimeout(resetTimer.current);
    }
  }, [state, reset]);

  const view = { ...BASE_VIEW[state] };
  if (errorText) view.hint = errorText;

  return {
    state,
    view,
    busy: state === "detected" || state === "checking" || state === "granted",
    submitCode,
    simulateBadge,
    reset,
  };
}
