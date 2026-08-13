import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/api/client";
import type { StationSnapshot, User } from "@/api/types";
import { initials } from "@/components/ui-kit";

/**
 * «Сотрудники» — вёрстка 1:1 из прототипа (блок isPeople).
 * Живое: список операторов (users), кто где на смене (dashboard/stations).
 * Прочерки (нет в системе): табельный номер, эффективность, выпуск,
 * график по часам — появятся с планом смены и учётом рабочего времени.
 */

interface PersonRow {
  user: User;
  status: "working" | "free";
  stationName: string | null;
  operation: string | null;
  lastEventAt: string | null;
}

export function PeopleScreen() {
  const [users, setUsers] = useState<User[]>([]);
  const [stations, setStations] = useState<StationSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "working" | "free">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [us, sts] = await Promise.all([
        api.users.list({ role: "operator", limit: 200 }),
        api.dashboard.stations(),
      ]);
      setUsers(us);
      setStations(sts);
      setNow(new Date());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить сотрудников");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const rows = useMemo<PersonRow[]>(() => {
    const byUser = new Map<string, StationSnapshot>();
    for (const s of stations) if (s.operator) byUser.set(s.operator.id, s);
    return users.map((user) => {
      const st = byUser.get(user.id);
      return {
        user,
        status: st ? "working" : "free",
        stationName: st?.name ?? null,
        operation: st?.last_event ? eventLabel(st.last_event.type) : null,
        lastEventAt: st?.last_event?.at ?? null,
      };
    });
  }, [users, stations]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows
      .filter((r) => statusFilter === "all" || r.status === statusFilter)
      .filter((r) => !q || r.user.full_name.toLowerCase().includes(q));
  }, [rows, search, statusFilter]);

  const selected = rows.find((r) => r.user.id === selectedId) ?? null;

  const counts = useMemo(() => {
    const working = rows.filter((r) => r.status === "working").length;
    return { total: rows.length, working, free: rows.length - working };
  }, [rows]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      {/* Шапка */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24 }}>
        <div style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-0.025em" }}>Сотрудники</div>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, padding: "11px 15px", fontSize: 14.5, fontWeight: 600, cursor: "pointer" }}>
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="#475467" strokeWidth="1.6" strokeLinecap="round"><rect x="2.8" y="4" width="14.4" height="13.2" rx="3" /><path d="M6.4 2.4v3M13.6 2.4v3M2.8 8.2h14.4" /></svg>
            Смена: 08:00 – 20:00
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="#98A2B3" strokeWidth="1.8" strokeLinecap="round"><path d="M4 6.5 8 10.5 12 6.5" /></svg>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 12.5, color: "#98A2B3" }}>
            Обновлено: {now.toLocaleTimeString("ru-RU")}
            <div onClick={() => void load()} className="animate-fl-pulse" style={{ width: 7, height: 7, borderRadius: 4, background: "#16A34A", cursor: "pointer" }} />
          </div>
        </div>
      </div>

      {/* KPI */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 16 }}>
        <PeopleKpi icon="people" iconBg="#EAF7EF" iconFg="#16A34A" label="Всего операторов" value={String(counts.total)} note="в системе" />
        <PeopleKpi icon="check" iconBg="#EAF7EF" iconFg="#16A34A" label="На смене" value={String(counts.working)} note="работают сейчас" />
        <PeopleKpi icon="pause" iconBg="#F1F3F6" iconFg="#98A2B3" label="Свободны" value={String(counts.free)} note="не назначены" />
        <PeopleKpi icon="perf" iconBg="#EFF5FE" iconFg="#3B82F6" label="Ср. эффективность" value="—" note="появится с планом смены" />
        <PeopleKpi icon="clock" iconBg="#FEF3E6" iconFg="#F79009" label="Ср. простой" value="—" note="появится с учётом времени" />
      </div>

      {error && (
        <div style={{ background: "#FDEEEC", border: "1px solid #F3C9C5", borderRadius: 14, padding: "14px 18px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 14.5, color: "#C0453C" }}>{error}</span>
          <button onClick={() => void load()} style={{ background: "#fff", border: "1px solid #F3C9C5", color: "#C0453C", borderRadius: 9, padding: "7px 13px", fontSize: 13.5, fontWeight: 600 }}>Повторить</button>
        </div>
      )}

      {/* Фильтры */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, padding: "0 14px", width: 280, height: 42 }}>
          <svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="#98A2B3" strokeWidth="1.7" strokeLinecap="round"><circle cx="8" cy="8" r="5" /><path d="M11.8 11.8 15.4 15.4" /></svg>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Поиск по сотруднику..." style={{ border: "none", outline: "none", fontSize: 14, width: "100%", background: "transparent" }} />
        </div>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as "all" | "working" | "free")} style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, padding: "0 14px", height: 42, fontSize: 14, color: "#475467", outline: "none" }}>
          <option value="all">Статус: Все</option>
          <option value="working">На смене</option>
          <option value="free">Свободны</option>
        </select>
        {(search || statusFilter !== "all") && (
          <div onClick={() => { setSearch(""); setStatusFilter("all"); }} style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, padding: "11px 16px", fontSize: 14, color: "#475467", cursor: "pointer" }}>Сбросить</div>
        )}
      </div>

      {/* Таблица + профиль */}
      <div style={{ display: "grid", gridTemplateColumns: selected ? "minmax(420px,0.85fr) minmax(520px,1.15fr)" : "1fr", gap: 18, alignItems: "start" }}>
        {/* Таблица */}
        <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 16, overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1.35fr 120px 1fr 20px", gap: 12, padding: "14px 20px", borderBottom: "1px solid #EFF1F4", background: "#FAFBFC", fontSize: 13, color: "#667085", fontWeight: 600 }}>
            <div>Сотрудник</div><div>Статус</div><div>Текущая станция</div><div />
          </div>

          {loading ? (
            <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 10 }}>
              {[0, 1, 2].map((i) => <div key={i} className="animate-fl-pulse" style={{ height: 52, borderRadius: 10, background: "#F3F4F6" }} />)}
            </div>
          ) : filtered.length === 0 ? (
            <div style={{ padding: "40px 20px", textAlign: "center" }}>
              <div style={{ fontSize: 15, fontWeight: 700 }}>{rows.length === 0 ? "Операторов пока нет" : "Ничего не нашлось"}</div>
              <div style={{ fontSize: 13.5, color: "#98A2B3", marginTop: 5 }}>{rows.length === 0 ? "Заведите операторов сидом." : "Измените поиск или фильтр."}</div>
            </div>
          ) : (
            filtered.map((r) => <PersonTableRow key={r.user.id} row={r} selected={r.user.id === selectedId} onPick={() => setSelectedId(r.user.id === selectedId ? null : r.user.id)} />)
          )}

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 20px" }}>
            <div style={{ fontSize: 13, color: "#98A2B3" }}>{filtered.length > 0 ? `Показано ${filtered.length} из ${rows.length} сотрудников` : ""}</div>
          </div>
        </div>

        {/* Профиль */}
        {selected && <PersonProfile row={selected} now={now} onClose={() => setSelectedId(null)} />}
      </div>
    </div>
  );
}

function PersonTableRow({ row, selected, onPick }: { row: PersonRow; selected: boolean; onPick: () => void }) {
  const [hover, setHover] = useState(false);
  const st = row.status === "working"
    ? { label: "На смене", color: "#16A34A", bg: "#EAF7EF" }
    : { label: "Свободен", color: "#98A2B3", bg: "#F1F3F6" };
  return (
    <div
      onClick={onPick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ display: "grid", gridTemplateColumns: "1.35fr 120px 1fr 20px", gap: 12, alignItems: "center", padding: "14px 20px", borderBottom: "1px solid #F3F4F6", cursor: "pointer", background: selected ? "#F4FBF6" : hover ? "#FBFCFD" : undefined, boxShadow: selected ? "inset 3px 0 0 #16A34A" : undefined }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
        <div style={{ width: 38, height: 38, borderRadius: 19, background: "#E7EDF3", color: "#475467", fontSize: 12.5, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>{initials(row.user.full_name)}</div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 14.5, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{row.user.full_name}</div>
          <div style={{ fontSize: 12, color: "#98A2B3", marginTop: 2 }}>Оператор</div>
        </div>
      </div>
      <div style={{ fontSize: 12.5, fontWeight: 600, color: st.color, background: st.bg, padding: "6px 11px", borderRadius: 8, justifySelf: "start" }}>{st.label}</div>
      <div style={{ minWidth: 0 }}>
        {row.stationName ? (
          <>
            <div style={{ fontSize: 14, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{row.stationName}</div>
            <div style={{ fontSize: 12.5, color: "#98A2B3", marginTop: 2 }}>{row.operation ?? "—"}</div>
          </>
        ) : (
          <span style={{ fontSize: 13.5, color: "#C4CBD4" }}>Не на смене</span>
        )}
      </div>
      <svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="#98A2B3" strokeWidth="1.7" strokeLinecap="round"><path d="M6.6 4 11.6 9l-5 5" /></svg>
    </div>
  );
}

function PersonProfile({ row, now, onClose }: { row: PersonRow; now: Date; onClose: () => void }) {
  const st = row.status === "working"
    ? { label: "На смене", color: "#16A34A" }
    : { label: "Свободен", color: "#98A2B3" };
  const worked = row.lastEventAt ? minutesSince(row.lastEventAt, now) : null;
  return (
    <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 16, overflow: "hidden" }} className="animate-fl-fade">
      <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 20 }}>
        {/* Шапка профиля */}
        <div style={{ display: "flex", alignItems: "flex-start", gap: 18 }}>
          <div style={{ width: 88, height: 88, borderRadius: 44, background: "#E7EDF3", color: "#475467", fontSize: 24, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>{initials(row.user.full_name)}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ fontSize: 23, fontWeight: 800, letterSpacing: "-0.02em" }}>{row.user.full_name}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 13.5, fontWeight: 600, color: st.color }}>
                <div style={{ width: 7, height: 7, borderRadius: 4, background: st.color }} />{st.label}
              </div>
            </div>
            <div style={{ display: "flex", gap: 34, marginTop: 12 }}>
              <div style={{ fontSize: 13.5, color: "#667085" }}>Роль: <span style={{ color: "#101828", fontWeight: 600 }}>Оператор</span></div>
              <div style={{ fontSize: 13.5, color: "#667085" }}>Статус учётки: <span style={{ color: "#101828", fontWeight: 600 }}>{row.user.active ? "Активна" : "Отключена"}</span></div>
            </div>
            <div style={{ display: "flex", gap: 34, marginTop: 8 }}>
              <div style={{ fontSize: 13.5, color: "#667085" }}>Табельный номер: <span style={{ color: "#C4CBD4", fontWeight: 600 }}>—</span></div>
            </div>
          </div>
          <div onClick={onClose} style={{ width: 28, height: 28, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flex: "0 0 auto" }}>
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="#98A2B3" strokeWidth="1.7" strokeLinecap="round"><path d="M4 4l8 8M12 4l-8 8" /></svg>
          </div>
        </div>

        {/* Три карточки: станция, операция, последнее событие */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
          <MiniCard iconStroke="#3B82F6" label="Станция" value={row.stationName ?? "—"} sub={row.status === "working" ? "на смене" : "не назначена"} icon="pin" />
          <MiniCard iconStroke="#3B82F6" label="Операция" value={row.operation ?? "—"} sub={row.stationName ? "текущая" : "—"} icon="gear" />
          <MiniCard iconStroke="#3B82F6" label="На станции" value={worked !== null ? fmtDuration(worked) : "—"} sub="от последнего события" icon="clock" />
        </div>
      </div>

      {/* Показатели смены — структура макета, значения-заглушки */}
      <div style={{ padding: "0 24px 22px" }}>
        <div style={{ border: "1px solid #EAECF0", borderRadius: 13, padding: 18 }}>
          <div style={{ fontSize: 14.5, fontWeight: 700 }}>Показатели смены</div>
          <div style={{ display: "flex", flexDirection: "column", marginTop: 12 }}>
            <MetricRow label="Эффективность" value="—" />
            <MetricRow label="Выпуск (готово / план)" value="—" />
            <MetricRow label="Производительность" value="—" />
            <MetricRow label="Время работы" value={worked !== null ? fmtDuration(worked) : "—"} live={worked !== null} />
            <MetricRow label="Простои" value="—" last />
          </div>
          <div style={{ fontSize: 12.5, color: "#98A2B3", marginTop: 12, display: "flex", alignItems: "center", gap: 7 }}>
            <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="#98A2B3" strokeWidth="1.6" strokeLinecap="round"><circle cx="10" cy="10" r="7.4" /><path d="M10 9.2v4.2" /><path d="M10 6.6h.01" /></svg>
            Полные показатели появятся с планом смены и учётом рабочего времени
          </div>
        </div>
      </div>
    </div>
  );
}

function MiniCard({ label, value, sub, icon, iconStroke }: { label: string; value: string; sub: string; icon: string; iconStroke: string }) {
  const p = { width: 18, height: 18, viewBox: "0 0 20 20", fill: "none", stroke: iconStroke, strokeWidth: 1.6, strokeLinecap: "round" as const };
  const icons: Record<string, React.ReactNode> = {
    pin: <svg {...p}><path d="M10 17.4s5.4-4.6 5.4-8.4a5.4 5.4 0 1 0-10.8 0c0 3.8 5.4 8.4 5.4 8.4Z" /><circle cx="10" cy="9" r="1.9" /></svg>,
    gear: <svg {...p}><circle cx="10" cy="10" r="2.9" /><path d="M10 2.4v2.2M10 15.4v2.2M2.4 10h2.2M15.4 10h2.2M4.6 4.6l1.6 1.6M13.8 13.8l1.6 1.6M15.4 4.6l-1.6 1.6M6.2 13.8l-1.6 1.6" /></svg>,
    clock: <svg {...p}><circle cx="10" cy="10" r="7.4" /><path d="M10 5.6V10l3 2" /></svg>,
  };
  const dim = value === "—";
  return (
    <div style={{ border: "1px solid #EAECF0", borderRadius: 12, padding: "14px 16px", display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ width: 36, height: 36, borderRadius: 10, background: "#EFF5FE", display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>{icons[icon]}</div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 12.5, color: "#98A2B3" }}>{label}</div>
        <div style={{ fontSize: 14.5, fontWeight: 700, marginTop: 2, color: dim ? "#C4CBD4" : undefined, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{value}</div>
        <div style={{ fontSize: 12, color: "#98A2B3", marginTop: 2 }}>{sub}</div>
      </div>
    </div>
  );
}

function MetricRow({ label, value, live, last }: { label: string; value: string; live?: boolean; last?: boolean }) {
  const dim = value === "—";
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "11px 0", borderBottom: last ? "none" : "1px solid #F3F4F6" }}>
      <div style={{ fontSize: 13.5, color: "#667085" }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: dim ? "#C4CBD4" : live ? "#16A34A" : undefined }}>{value}</div>
    </div>
  );
}

function PeopleKpi({ icon, iconBg, iconFg, label, value, note }: { icon: string; iconBg: string; iconFg: string; label: string; value: string; note: string }) {
  const dim = value === "—";
  const p = { width: 17, height: 17, viewBox: "0 0 20 20", fill: "none", stroke: iconFg, strokeWidth: 1.7, strokeLinecap: "round" as const };
  const icons: Record<string, React.ReactNode> = {
    people: <svg {...p}><circle cx="8" cy="7.2" r="2.8" /><path d="M2.8 16.4c0-2.9 2.3-4.8 5.2-4.8s5.2 1.9 5.2 4.8" /><path d="M14.2 5.2a2.6 2.6 0 0 1 0 5" /><path d="M15.4 11.9c1.5.5 2.4 1.8 2.4 3.6" /></svg>,
    check: <svg {...p} strokeLinejoin="round"><circle cx="10" cy="10" r="7.4" /><path d="M6.6 10.2 9 12.6 13.6 7.6" /></svg>,
    pause: <svg {...p}><path d="M7.6 4.6v10.8M12.4 4.6v10.8" /></svg>,
    perf: <svg {...p}><path d="M3.4 14.6a7.6 7.6 0 1 1 13.2 0" /><path d="M10 14.2 13.4 8" /></svg>,
    clock: <svg {...p}><circle cx="10" cy="10" r="7.4" /><path d="M10 5.6V10l3 2" /></svg>,
  };
  return (
    <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 14, padding: "18px 20px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ width: 38, height: 38, borderRadius: 19, background: iconBg, display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>{icons[icon]}</div>
        <div style={{ fontSize: 13.5, color: "#667085" }}>{label}</div>
      </div>
      <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: "-0.02em", color: dim ? "#C4CBD4" : undefined }}>{value}</div>
      <div style={{ fontSize: 13, color: "#98A2B3" }}>{note}</div>
    </div>
  );
}

function eventLabel(type: string): string {
  const map: Record<string, string> = {
    scan_in: "Скан входящей", start: "Работает", stop: "Стоп", scan_out: "Скан исходящей",
    break_start: "На паузе", break_end: "Вернулся", error: "Ошибка", interrupted: "Прервано", anomaly: "Аномалия",
  };
  return map[type] ?? type;
}

function minutesSince(iso: string, now: Date): number {
  return Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 60000));
}

function fmtDuration(min: number): string {
  if (min < 60) return `${min} мин`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h} ч ${m} мин` : `${h} ч`;
}
