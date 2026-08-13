import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/AppLayout";
import { api, ApiError } from "@/api/client";
import type { Badge, StationSnapshot, User } from "@/api/types";
import { cn } from "@/lib/utils";

type Toast = { kind: "ok" | "err"; text: string } | null;

/** Состояние считывателя бейджей на экране назначений. */
type ReaderState =
  | { kind: "idle" }
  | { kind: "reading" }
  | { kind: "recognized"; uid: string; badgeId: string }
  | { kind: "busy"; uid: string } // бейдж есть, но уже выдан
  | { kind: "unknown"; uid: string }; // бейджа нет в системе

export function AssignmentsScreen() {
  const [operators, setOperators] = useState<User[]>([]);
  const [badges, setBadges] = useState<Badge[]>([]);
  const [stations, setStations] = useState<StationSnapshot[]>([]);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<Toast>(null);

  const [reader, setReader] = useState<ReaderState>({ kind: "idle" });
  const [search, setSearch] = useState("");
  const [userId, setUserId] = useState<string | null>(null);
  const [badgeId, setBadgeId] = useState<string | null>(null);
  const [stationId, setStationId] = useState<string | null>(null);
  /** Станок, для которого запрошено подтверждение освобождения. */
  const [confirmFree, setConfirmFree] = useState<string | null>(null);
  const [freeing, setFreeing] = useState<string | null>(null);

  const busyUserIds = useMemo(
    () => new Set(stations.map((s) => s.operator?.id).filter(Boolean) as string[]),
    [stations],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [ops, freeBadges, sts] = await Promise.all([
        api.users.list({ role: "operator", active: true, limit: 200 }),
        api.badges.list({ status: "free", limit: 200 }),
        api.dashboard.stations(),
      ]);
      setOperators(ops);
      setBadges(freeBadges);
      setStations(sts);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Не удалось загрузить данные");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  /**
   * Поднесение бейджа к считывателю.
   * TODO(nfc): заменить на событие реального ридера (ESP32 + PN532 → MQTT → WS).
   * Пока перебираем свободные бейджи по кругу — имитируем «поднесли следующий».
   */
  const simulateTap = useCallback(() => {
    if (reader.kind === "reading") return;
    setReader({ kind: "reading" });
    setTimeout(() => {
      if (badges.length === 0) {
        setReader({ kind: "unknown", uid: "04A3F7B9" });
        return;
      }
      const currentIdx = badges.findIndex((b) => b.id === badgeId);
      const next = badges[(currentIdx + 1) % badges.length];
      setReader({ kind: "recognized", uid: next.uid, badgeId: next.id });
      setBadgeId(next.id); // сразу подставляем в шаг 2
    }, 700);
  }, [reader.kind, badges, badgeId]);

  const visibleOperators = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? operators.filter((o) => o.full_name.toLowerCase().includes(q)) : operators;
  }, [operators, search]);

  const selectedUser = operators.find((o) => o.id === userId) ?? null;
  const selectedBadge = badges.find((b) => b.id === badgeId) ?? null;
  const selectedStation = stations.find((s) => s.id === stationId) ?? null;

  const canSubmit = !!userId && !!badgeId && !!stationId && !submitting;

  const reset = () => {
    setUserId(null);
    setBadgeId(null);
    setStationId(null);
    setSearch("");
    setReader({ kind: "idle" });
  };

  /**
   * Принудительное закрытие смены (Решение №37): оператор потерял бейдж,
   * ушёл раньше, пересменка. Освобождает станок и возвращает бейдж в пул.
   * Бэк дополнительно шлёт MQTT-команду на терминал станка.
   */
  const freeStation = async (station: StationSnapshot) => {
    if (!station.active_shift_id) return;
    setFreeing(station.id);
    try {
      await api.shifts.forceClose(station.active_shift_id);
      setToast({ kind: "ok", text: `Станок «${station.name}» освобождён` });
      setConfirmFree(null);
      await load();
    } catch (e) {
      setToast({ kind: "err", text: e instanceof ApiError ? e.message : "Не удалось освободить" });
    } finally {
      setFreeing(null);
    }
  };

  const submit = async () => {
    if (!canSubmit || !userId || !badgeId || !stationId) return;
    setSubmitting(true);
    try {
      const shift = await api.shifts.create({
        user_id: userId,
        badge_id: badgeId,
        station_id: stationId,
      });
      setToast({ kind: "ok", text: `${shift.user_full_name} назначен на «${shift.station_name}»` });
      reset();
      await load();
    } catch (e) {
      setToast({ kind: "err", text: e instanceof ApiError ? e.message : "Не удалось назначить" });
      if (e instanceof ApiError && e.status === 409) await load();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PageHeader title="Назначения" />

      {loadError && (
        <div
          className="mb-5 flex items-center justify-between rounded-[14px] px-5 py-4"
          style={{ background: "var(--fl-danger-soft)", border: "1px solid #F3C9C5" }}
        >
          <span className="text-[15px]" style={{ color: "var(--fl-danger)" }}>
            {loadError}
          </span>
          <button
            onClick={() => void load()}
            className="rounded-[9px] px-3.5 py-2 text-[14px] font-semibold"
            style={{ background: "#ffffff", border: "1px solid #F3C9C5", color: "var(--fl-danger)" }}
          >
            Повторить
          </button>
        </div>
      )}

      {toast && (
        <div
          className="mb-5 animate-fl-fade rounded-[14px] px-5 py-4 text-[15px]"
          style={{
            background: toast.kind === "ok" ? "var(--fl-ok-soft)" : "var(--fl-danger-soft)",
            border: `1px solid ${toast.kind === "ok" ? "#CDEBD9" : "#F3C9C5"}`,
            color: toast.kind === "ok" ? "#12833C" : "var(--fl-danger)",
          }}
        >
          {toast.text}
        </div>
      )}

      {/* === Верхний блок: зона NFC + состояние бейджа === */}
      <div className="mb-5 grid gap-5" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <ReaderZone state={reader} onTap={simulateTap} />
        <BadgeState state={reader} selectedUid={selectedBadge?.uid ?? null} />
      </div>

      {/* === Три шага === */}
      <div className="grid gap-5" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
        <Step index={1} title="Сотрудник">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск сотрудника…"
            className="mb-3 h-11 w-full rounded-[10px] border px-3.5 text-[15px] outline-none transition-colors focus:border-brand"
            style={{ borderColor: "#E4E7EB" }}
          />

          {loading ? (
            <Skeleton rows={4} />
          ) : visibleOperators.length === 0 ? (
            <Empty text={search ? "Никого не нашлось" : "Нет активных операторов"} />
          ) : (
            <div className="flex max-h-[360px] flex-col gap-2 overflow-y-auto pr-1">
              {visibleOperators.map((op) => {
                const busy = busyUserIds.has(op.id);
                const active = op.id === userId;
                return (
                  <button
                    key={op.id}
                    disabled={busy}
                    onClick={() => setUserId(active ? null : op.id)}
                    className={cn(
                      "flex items-center justify-between rounded-[12px] border px-3.5 py-3 text-left transition-colors",
                      active ? "border-brand bg-brand-soft" : "border-[#EDEFF2] bg-white hover:border-[#D8DDE5]",
                      busy && "cursor-not-allowed opacity-45 hover:border-[#EDEFF2]",
                    )}
                  >
                    <div className="min-w-0">
                      <div className="truncate text-[15px] font-bold">{op.full_name}</div>
                      <div className="text-[13px]" style={{ color: "#98A2B3" }}>
                        {busy ? "Уже на смене" : "Доступен"}
                      </div>
                    </div>
                    {active && <CheckDot />}
                  </button>
                );
              })}
            </div>
          )}
        </Step>

        <Step index={2} title="Бейдж и станок">
          <Label>Бейдж</Label>
          {loading ? (
            <Skeleton rows={1} />
          ) : badges.length === 0 ? (
            <Empty text="Нет свободных бейджей" />
          ) : (
            <select
              value={badgeId ?? ""}
              onChange={(e) => setBadgeId(e.target.value || null)}
              className="mb-4 h-11 w-full rounded-[10px] border bg-white px-3 text-[15px] outline-none focus:border-brand"
              style={{ borderColor: badgeId ? "var(--fl-brand)" : "#E4E7EB" }}
            >
              <option value="">Поднесите бейдж или выберите</option>
              {badges.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.uid}
                </option>
              ))}
            </select>
          )}

          <Label>Станок</Label>
          {loading ? (
            <Skeleton rows={3} />
          ) : (
            <div className="flex flex-col gap-2">
              {stations.map((st) => {
                const occupied = !!st.active_shift_id;
                const active = st.id === stationId;
                const asking = confirmFree === st.id;

                if (occupied) {
                  return (
                    <div
                      key={st.id}
                      className="rounded-[12px] border px-3.5 py-3"
                      style={{ borderColor: asking ? "#F3C9C5" : "#EDEFF2", background: asking ? "#FFFBFB" : "#FAFBFC" }}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate text-[15px] font-bold" style={{ color: "#667085" }}>
                            {st.name}
                          </div>
                          <div className="truncate text-[13px]" style={{ color: "#98A2B3" }}>
                            Занят: {st.operator?.full_name ?? "—"}
                          </div>
                        </div>
                        {!asking && (
                          <button
                            onClick={() => setConfirmFree(st.id)}
                            className="shrink-0 rounded-[8px] px-2.5 py-1.5 text-[12.5px] font-semibold transition-colors hover:bg-[#F3F4F6]"
                            style={{ color: "#667085", border: "1px solid #E4E7EB", background: "#fff" }}
                          >
                            Освободить
                          </button>
                        )}
                      </div>

                      {asking && (
                        <div className="mt-2.5 animate-fl-fade">
                          <div className="mb-2 text-[12.5px] leading-snug" style={{ color: "#667085" }}>
                            Смена будет закрыта принудительно, бейдж вернётся в пул.
                          </div>
                          <div className="flex gap-2">
                            <button
                              onClick={() => void freeStation(st)}
                              disabled={freeing === st.id}
                              className="rounded-[8px] px-3 py-1.5 text-[12.5px] font-semibold text-white transition-opacity disabled:opacity-50"
                              style={{ background: "var(--fl-danger)" }}
                            >
                              {freeing === st.id ? "Закрываем…" : "Да, освободить"}
                            </button>
                            <button
                              onClick={() => setConfirmFree(null)}
                              className="rounded-[8px] px-3 py-1.5 text-[12.5px] font-semibold transition-colors hover:bg-[#F3F4F6]"
                              style={{ color: "#667085", border: "1px solid #E4E7EB", background: "#fff" }}
                            >
                              Отмена
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                }

                return (
                  <button
                    key={st.id}
                    onClick={() => setStationId(active ? null : st.id)}
                    className={cn(
                      "flex items-center justify-between rounded-[12px] border px-3.5 py-3 text-left transition-colors",
                      active ? "border-brand bg-brand-soft" : "border-[#EDEFF2] bg-white hover:border-[#D8DDE5]",
                    )}
                  >
                    <div className="min-w-0">
                      <div className="truncate text-[15px] font-bold">{st.name}</div>
                      <div className="truncate text-[13px]" style={{ color: "#98A2B3" }}>
                        Свободен
                      </div>
                    </div>
                    {active && <CheckDot />}
                  </button>
                );
              })}
            </div>
          )}
        </Step>

        <Step index={3} title="Подтверждение">
          <div
            className="mb-4 rounded-[12px] px-4 py-3.5"
            style={{ background: "#F9FAFB", border: "1px solid #EDEFF2" }}
          >
            <div className="mb-3 text-[13.5px] font-semibold" style={{ color: "#667085" }}>
              Назначение будет создано:
            </div>
            <Row label="Сотрудник" value={selectedUser?.full_name} />
            <Row label="Бейдж" value={selectedBadge?.uid} />
            <Row label="Станок" value={selectedStation?.name} />
          </div>

          <button
            onClick={() => void submit()}
            disabled={!canSubmit}
            className="h-12 w-full rounded-[12px] bg-primary text-[16px] font-bold text-primary-foreground transition-colors hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting ? "Назначаем…" : "Назначить"}
          </button>

          <p className="mt-3 text-[13px] leading-relaxed" style={{ color: "#98A2B3" }}>
            Оператор получит бейдж и приложит его к терминалу станка, чтобы начать смену.
          </p>
        </Step>
      </div>
    </>
  );
}

// === Зона считывания NFC ===

function ReaderZone({ state, onTap }: { state: ReaderState; onTap: () => void }) {
  const reading = state.kind === "reading";
  const recognized = state.kind === "recognized";

  return (
    <div
      onClick={onTap}
      className="flex cursor-pointer flex-col items-center justify-center rounded-[16px] px-6 py-8 transition-colors"
      style={{
        background: "var(--fl-brand-faint)",
        border: `1px solid ${recognized ? "#BFE6CE" : "#DFF0E6"}`,
        minHeight: 260,
      }}
    >
      <div className="relative flex items-center justify-center" style={{ width: 150, height: 150 }}>
        <div className="absolute rounded-full" style={{ width: 108, height: 108, background: "#EAF7EF" }} />
        <div className="absolute rounded-full" style={{ width: 150, height: 150, border: "1px solid #E1EFE7" }} />
        {!reading && (
          <div
            className="absolute animate-fl-ring rounded-full"
            style={{ width: 130, height: 130, border: "1px solid #16A34A" }}
          />
        )}
        <svg
          width="52"
          height="38"
          viewBox="0 0 62 42"
          fill="none"
          stroke="#16A34A"
          strokeWidth="7"
          strokeLinecap="round"
          className={cn("relative", reading && "animate-fl-pulse")}
        >
          <path d="M6 20a34 34 0 0 1 50 0" />
          <path d="M18 31a18 18 0 0 1 26 0" />
          <circle cx="31" cy="39" r="1" strokeWidth="8" />
        </svg>
      </div>

      <div className="mt-4 text-center">
        <div className="text-[16.5px] font-bold">
          {reading ? "Считывание…" : "Готов к считыванию"}
        </div>
        <div className="mt-1.5 text-[14px]" style={{ color: "#667085" }}>
          Приложите бейдж сотрудника к считывателю NFC
        </div>
      </div>
    </div>
  );
}

// === Состояние обнаруженного бейджа ===

function BadgeState({ state, selectedUid }: { state: ReaderState; selectedUid: string | null }) {
  // Бейдж мог быть выбран и вручную из списка — карточка показывает и такой выбор.
  const readerUid = "uid" in state ? state.uid : null;
  const uid = readerUid ?? selectedUid;
  const isOk = state.kind === "recognized" || (!!selectedUid && state.kind === "idle");
  const isBad = state.kind === "busy" || state.kind === "unknown";

  const title = isOk
    ? "Бейдж обнаружен"
    : state.kind === "busy"
      ? "Бейдж уже выдан"
      : state.kind === "unknown"
        ? "Бейдж не распознан"
        : state.kind === "reading"
          ? "Считывание…"
          : "Бейдж не обнаружен";

  const tone = isOk
    ? { fg: "var(--fl-ok)", bg: "var(--fl-ok-soft)", label: "Бейдж распознан" }
    : isBad
      ? { fg: "var(--fl-danger)", bg: "var(--fl-danger-soft)", label: "Недоступен" }
      : { fg: "#C4CBD4", bg: "#F3F4F6", label: null };

  return (
    <div
      className="flex flex-col items-center justify-center rounded-[16px] bg-card px-6 py-8"
      style={{ border: "1px solid var(--fl-line-soft)", minHeight: 260 }}
    >
      <div className="text-[16.5px] font-bold">{title}</div>

      <div
        className="mt-5 flex items-center justify-center rounded-full transition-colors"
        style={{ width: 76, height: 76, background: tone.bg }}
      >
        {isOk ? (
          <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke={tone.fg} strokeWidth="2.4" strokeLinecap="round">
            <path d="M5 12.5 10 17.5 19 7" />
          </svg>
        ) : (
          <svg width="30" height="30" viewBox="0 0 20 20" fill="none" stroke={tone.fg} strokeWidth="1.8" strokeLinecap="round">
            <rect x="4.5" y="2.5" width="11" height="15" rx="2.5" />
            <path d="M8 6h4" />
            <circle cx="10" cy="11" r="1.8" />
          </svg>
        )}
      </div>

      <div className="mt-4 text-[13px]" style={{ color: "#98A2B3" }}>
        ID бейджа
      </div>
      <div
        className="mt-1 max-w-full truncate px-4 font-extrabold"
        style={{
          fontSize: uid && uid.length > 12 ? 21 : 30,
          letterSpacing: "0.02em",
          color: uid ? undefined : "#D5DAE1",
        }}
      >
        {uid ?? "— — — —"}
      </div>

      {tone.label && (
        <div
          className="mt-3 flex items-center gap-2 rounded-full px-3.5 py-1.5 text-[13.5px] font-semibold"
          style={{ background: tone.bg, color: tone.fg }}
        >
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: tone.fg }} />
          {tone.label}
        </div>
      )}
    </div>
  );
}

// === Мелкие блоки ===

function Step({ index, title, children }: { index: number; title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[16px] bg-card p-5" style={{ border: "1px solid var(--fl-line-soft)" }}>
      <div className="mb-4 flex items-center gap-2.5">
        <span
          className="flex items-center justify-center rounded-[8px] text-[13px] font-bold"
          style={{ width: 26, height: 26, background: "var(--fl-brand-soft)", color: "var(--fl-brand)" }}
        >
          {index}
        </span>
        <span className="text-[16px] font-bold">{title}</span>
      </div>
      {children}
    </section>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 text-[13.5px] font-semibold" style={{ color: "#667085" }}>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <span className="text-[13.5px]" style={{ color: "#98A2B3" }}>
        {label}
      </span>
      <span
        className={cn("truncate text-[14.5px] font-bold", !value && "font-normal")}
        style={{ color: value ? undefined : "#C4CBD4" }}
      >
        {value ?? "не выбрано"}
      </span>
    </div>
  );
}

function CheckDot() {
  return (
    <span
      className="flex shrink-0 items-center justify-center rounded-full"
      style={{ width: 22, height: 22, background: "var(--fl-brand)" }}
    >
      <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round">
        <path d="M3 7.5 5.8 10 11 4" />
      </svg>
    </span>
  );
}

function Skeleton({ rows }: { rows: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="animate-fl-pulse rounded-[12px]" style={{ height: 56, background: "#F3F4F6" }} />
      ))}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div
      className="rounded-[12px] px-4 py-6 text-center text-[14px]"
      style={{ background: "#FAFBFC", border: "1px dashed #E4E7EB", color: "#98A2B3" }}
    >
      {text}
    </div>
  );
}
