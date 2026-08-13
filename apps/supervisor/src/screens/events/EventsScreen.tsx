import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/api/client";
import type { IncidentItem } from "@/api/types";
import { initials } from "@/components/ui-kit";

/**
 * «События» — вёрстка 1:1 из прототипа (блок isEvents).
 * Живая лента инцидентов от watchdog (`GET /dashboard/incidents`):
 * аномалии (norm_exceeded / pause_exceeded / station_idle / transit_stuck)
 * и ошибки. Всё на реальных данных — заглушек нет.
 */

const GRID = "110px 170px 160px minmax(240px,1.5fr) 190px 170px 40px";
const PAGE_SIZE = 20;

type LevelKey = "critical" | "warning" | "info";

interface EventRow {
  id: string;
  time: string;
  date: string;
  typeLabel: string;
  level: LevelKey;
  levelLabel: string;
  title: string;
  sub: string;
  who: string | null;
  where: string;
  whereSub: string;
}

const LEVEL_META: Record<LevelKey, { color: string; bg: string; label: string }> = {
  critical: { color: "#C0453C", bg: "#FDEEEC", label: "Критично" },
  warning: { color: "#F79009", bg: "#FEF3E6", label: "Внимание" },
  info: { color: "#3B82F6", bg: "#EFF5FE", label: "Инфо" },
};

export function EventsScreen() {
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());

  const [search, setSearch] = useState("");
  const [levelFilter, setLevelFilter] = useState<LevelKey | "all">("all");
  const [page, setPage] = useState(1);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setIncidents(await api.dashboard.incidents({ limit: 200 }));
      setNow(new Date());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить события");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const rows = useMemo<EventRow[]>(() => incidents.map(toRow), [incidents]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows
      .filter((r) => levelFilter === "all" || r.level === levelFilter)
      .filter((r) => !q || r.title.toLowerCase().includes(q) || (r.who?.toLowerCase().includes(q) ?? false) || r.where.toLowerCase().includes(q));
  }, [rows, levelFilter, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageRows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const counts = useMemo(() => {
    const c = { critical: 0, warning: 0, info: 0 };
    for (const r of rows) c[r.level] += 1;
    return c;
  }, [rows]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      {/* Шапка */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24 }}>
        <div style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-0.025em" }}>События</div>
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

      {/* KPI: 4 карточки */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16 }}>
        <EventKpi icon="bell" iconBg="#EFF5FE" iconFg="#3B82F6" label="Всего за смену" value={String(rows.length)} note="событий" noteColor="#98A2B3" />
        <EventKpi icon="warn" iconBg="#FDEEEC" iconFg="#C0453C" label="Критичных" value={String(counts.critical)} note={counts.critical > 0 ? "требуют реакции" : "нет"} noteColor={counts.critical > 0 ? "#C0453C" : "#16A34A"} />
        <EventKpi icon="clock" iconBg="#FEF3E6" iconFg="#F79009" label="Предупреждений" value={String(counts.warning)} note="за смену" noteColor="#98A2B3" />
        <EventKpi icon="check" iconBg="#EAF7EF" iconFg="#16A34A" label="Информационных" value={String(counts.info)} note="за смену" noteColor="#98A2B3" />
      </div>

      {error && (
        <div style={{ background: "#FDEEEC", border: "1px solid #F3C9C5", borderRadius: 14, padding: "14px 18px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 14.5, color: "#C0453C" }}>{error}</span>
          <button onClick={() => void load()} style={{ background: "#fff", border: "1px solid #F3C9C5", color: "#C0453C", borderRadius: 9, padding: "7px 13px", fontSize: 13.5, fontWeight: 600 }}>Повторить</button>
        </div>
      )}

      {/* Таблица */}
      <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 16, overflow: "hidden" }}>
        {/* Фильтры */}
        <div style={{ padding: "18px 22px", display: "flex", flexDirection: "column", gap: 12, borderBottom: "1px solid #EFF1F4" }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, border: "1px solid #EAECF0", borderRadius: 11, padding: "10px 14px", fontSize: 14, color: "#475467" }}>
              <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="#475467" strokeWidth="1.6" strokeLinecap="round"><rect x="2.8" y="4" width="14.4" height="13.2" rx="3" /><path d="M6.4 2.4v3M13.6 2.4v3M2.8 8.2h14.4" /></svg>
              Сегодня, {now.toLocaleDateString("ru-RU")}
            </div>
            {/* Фильтр уровня */}
            <select value={levelFilter} onChange={(e) => { setLevelFilter(e.target.value as LevelKey | "all"); setPage(1); }} style={{ border: "1px solid #EAECF0", borderRadius: 11, padding: "10px 14px", fontSize: 14, color: "#475467", outline: "none", background: "#fff" }}>
              <option value="all">Уровень: Все</option>
              <option value="critical">Критичные</option>
              <option value="warning">Предупреждения</option>
              <option value="info">Информационные</option>
            </select>
            {(search || levelFilter !== "all") && (
              <div onClick={() => { setSearch(""); setLevelFilter("all"); setPage(1); }} style={{ border: "1px solid #EAECF0", borderRadius: 11, padding: "10px 16px", fontSize: 14, color: "#475467", cursor: "pointer" }}>Сбросить</div>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, border: "1px solid #EAECF0", borderRadius: 11, padding: "0 14px", width: 290, height: 40 }}>
            <svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="#98A2B3" strokeWidth="1.7" strokeLinecap="round"><circle cx="8" cy="8" r="5" /><path d="M11.8 11.8 15.4 15.4" /></svg>
            <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="Поиск по событиям..." style={{ border: "none", outline: "none", fontSize: 14, width: "100%", background: "transparent" }} />
          </div>
        </div>

        {/* Заголовок */}
        <div style={{ display: "grid", gridTemplateColumns: GRID, gap: 14, padding: "13px 22px", borderBottom: "1px solid #EFF1F4", background: "#FAFBFC", fontSize: 13, color: "#667085", fontWeight: 600 }}>
          <div>Время</div><div>Тип события</div><div>Уровень</div><div>Описание</div><div>Сотрудник</div><div>Станция / Изделие</div><div />
        </div>

        {loading ? (
          <div style={{ padding: 22, display: "flex", flexDirection: "column", gap: 10 }}>
            {[0, 1, 2].map((i) => <div key={i} className="animate-fl-pulse" style={{ height: 56, borderRadius: 10, background: "#F3F4F6" }} />)}
          </div>
        ) : pageRows.length === 0 ? (
          <div style={{ padding: "48px 22px", textAlign: "center" }}>
            <div style={{ fontSize: 15, fontWeight: 700 }}>{rows.length === 0 ? "За смену событий не было" : "Ничего не нашлось"}</div>
            <div style={{ fontSize: 13.5, color: "#98A2B3", marginTop: 5 }}>
              {rows.length === 0 ? "Watchdog не зафиксировал аномалий и ошибок." : "Измените фильтр или поиск."}
            </div>
          </div>
        ) : (
          pageRows.map((r) => <Row key={r.id} row={r} />)
        )}

        {/* Пагинация */}
        {!loading && filtered.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 22px" }}>
            <div style={{ fontSize: 13, color: "#98A2B3" }}>
              Показано {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, filtered.length)} из {filtered.length} событий
            </div>
            {totalPages > 1 && (
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <PageBtn disabled={safePage === 1} onClick={() => setPage(safePage - 1)} dir="prev" />
                {pageNumbers(safePage, totalPages).map((p, i) =>
                  p === "..." ? (
                    <div key={`e${i}`} style={{ fontSize: 13.5, color: "#98A2B3", padding: "0 4px" }}>...</div>
                  ) : (
                    <div key={p} onClick={() => setPage(p)} style={{ width: 32, height: 32, borderRadius: 9, background: p === safePage ? "#EAF7EF" : "#fff", color: p === safePage ? "#16A34A" : "#475467", border: p === safePage ? "none" : "1px solid #EAECF0", fontSize: 13.5, fontWeight: p === safePage ? 700 : 400, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>{p}</div>
                  ),
                )}
                <PageBtn disabled={safePage === totalPages} onClick={() => setPage(safePage + 1)} dir="next" />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// === Строка события ===

function Row({ row }: { row: EventRow }) {
  const [hover, setHover] = useState(false);
  const lm = LEVEL_META[row.level];
  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ display: "grid", gridTemplateColumns: GRID, gap: 14, padding: "15px 22px", borderBottom: "1px solid #F3F4F6", alignItems: "center", background: hover ? "#FBFCFD" : undefined }}
    >
      <div>
        <div style={{ fontSize: 14, fontWeight: 600 }}>{row.time}</div>
        <div style={{ fontSize: 12.5, color: "#98A2B3", marginTop: 3 }}>{row.date}</div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 26, height: 26, borderRadius: 13, background: lm.bg, display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>
          <div style={{ width: 11, height: 11, borderRadius: 3, background: lm.color }} />
        </div>
        <div style={{ fontSize: 14, color: "#101828" }}>{row.typeLabel}</div>
      </div>
      <div style={{ fontSize: 12.5, fontWeight: 600, color: lm.color, background: lm.bg, padding: "6px 11px", borderRadius: 8, justifySelf: "start" }}>{row.levelLabel}</div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600 }}>{row.title}</div>
        <div style={{ fontSize: 12.5, color: "#98A2B3", marginTop: 3 }}>{row.sub}</div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 11, minWidth: 0 }}>
        {row.who ? (
          <>
            <div style={{ width: 34, height: 34, borderRadius: 17, background: "#E7EDF3", color: "#475467", fontSize: 11.5, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>{initials(row.who)}</div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{row.who}</div>
            </div>
          </>
        ) : (
          <span style={{ fontSize: 13.5, color: "#C4CBD4" }}>—</span>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="#98A2B3" strokeWidth="1.6" strokeLinecap="round" style={{ flex: "0 0 auto" }}><path d="M10 17.4s5.4-4.6 5.4-8.4a5.4 5.4 0 1 0-10.8 0c0 3.8 5.4 8.4 5.4 8.4Z" /><circle cx="10" cy="9" r="1.9" /></svg>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600 }}>{row.where}</div>
          {row.whereSub && <div style={{ fontSize: 12, color: "#98A2B3", marginTop: 2 }}>{row.whereSub}</div>}
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", cursor: "pointer" }}>
        <svg width="17" height="17" viewBox="0 0 18 18" fill="#B9C0C9"><circle cx="4" cy="9" r="1.5" /><circle cx="9" cy="9" r="1.5" /><circle cx="14" cy="9" r="1.5" /></svg>
      </div>
    </div>
  );
}

function PageBtn({ disabled, onClick, dir }: { disabled: boolean; onClick: () => void; dir: "prev" | "next" }) {
  return (
    <div onClick={disabled ? undefined : onClick} style={{ width: 32, height: 32, border: "1px solid #EAECF0", borderRadius: 9, display: "flex", alignItems: "center", justifyContent: "center", cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.4 : 1 }}>
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#98A2B3" strokeWidth="1.7" strokeLinecap="round">
        {dir === "prev" ? <path d="M10 3.5 5.5 8 10 12.5" /> : <path d="M6 3.5 10.5 8 6 12.5" />}
      </svg>
    </div>
  );
}

function EventKpi({ icon, iconBg, iconFg, label, value, note, noteColor }: {
  icon: string; iconBg: string; iconFg: string; label: string; value: string; note: string; noteColor: string;
}) {
  const p = { width: 19, height: 19, viewBox: "0 0 20 20", fill: "none", stroke: iconFg, strokeWidth: 1.7, strokeLinecap: "round" as const };
  const icons: Record<string, React.ReactNode> = {
    bell: <svg {...p} strokeLinejoin="round"><path d="M5 8.4a5 5 0 0 1 10 0c0 3.2 1.2 4.4 1.2 4.4H3.8S5 11.6 5 8.4Z" /><path d="M8.4 15.6a1.8 1.8 0 0 0 3.2 0" /></svg>,
    warn: <svg {...p} strokeLinejoin="round"><path d="M10 3.2 18 16.6H2Z" /><path d="M10 8.2v3.4" /><path d="M10 14.2h.01" /></svg>,
    clock: <svg {...p}><circle cx="10" cy="10" r="7.4" /><path d="M10 5.6V10l3 2" /></svg>,
    check: <svg {...p} strokeLinejoin="round"><circle cx="10" cy="10" r="7.4" /><path d="M6.6 10.2 9 12.6 13.6 7.6" /></svg>,
  };
  return (
    <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 14, padding: "20px 22px", display: "flex", flexDirection: "column", gap: 11 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 13 }}>
        <div style={{ width: 44, height: 44, borderRadius: 22, background: iconBg, display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>{icons[icon]}</div>
        <div style={{ fontSize: 14, color: "#667085" }}>{label}</div>
      </div>
      <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-0.02em" }}>{value}</div>
      <div style={{ fontSize: 13, fontWeight: 600, color: noteColor }}>{note}</div>
    </div>
  );
}

// === Маппинг инцидента в строку ===

function toRow(inc: IncidentItem): EventRow {
  const d = new Date(inc.timestamp);
  const kind = typeof inc.details?.kind === "string" ? (inc.details.kind as string) : null;
  const isAnomaly = inc.event_type === "anomaly";

  // Уровень: ошибки и часть аномалий — критичны; норматив/пауза — предупреждение.
  let level: LevelKey = "info";
  if (inc.event_type === "error") level = "critical";
  else if (isAnomaly) {
    level = kind === "transit_stuck" || kind === "station_idle" ? "critical" : "warning";
  }

  const { typeLabel, title } = describe(inc, kind, isAnomaly);

  return {
    id: inc.id,
    time: d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }),
    date: d.toLocaleDateString("ru-RU"),
    typeLabel,
    level,
    levelLabel: LEVEL_META[level].label,
    title,
    sub: inc.part_id ? `Деталь ${inc.part_id}` : "—",
    who: null, // ФИО оператора нет в инциденте; появится, когда бэк отдаст shift→user
    where: inc.station_name,
    whereSub: "",
  };
}

function describe(inc: IncidentItem, kind: string | null, isAnomaly: boolean): { typeLabel: string; title: string } {
  if (isAnomaly) {
    const map: Record<string, { typeLabel: string; title: string }> = {
      norm_exceeded: { typeLabel: "Превышение норматива", title: "Операция превысила норматив времени" },
      pause_exceeded: { typeLabel: "Затянувшаяся пауза", title: "Пауза дольше допустимой" },
      station_idle: { typeLabel: "Простой станции", title: "Станция простаивает без операций" },
      transit_stuck: { typeLabel: "Застрявшая деталь", title: "Деталь не дошла до следующей станции" },
    };
    return kind && map[kind] ? map[kind] : { typeLabel: "Аномалия", title: "Зафиксирована аномалия" };
  }
  return { typeLabel: "Ошибка", title: "Ошибка на терминале станции" };
}

function pageNumbers(current: number, total: number): (number | "...")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const out: (number | "...")[] = [1];
  const from = Math.max(2, current - 1);
  const to = Math.min(total - 1, current + 1);
  if (from > 2) out.push("...");
  for (let i = from; i <= to; i++) out.push(i);
  if (to < total - 1) out.push("...");
  out.push(total);
  return out;
}
