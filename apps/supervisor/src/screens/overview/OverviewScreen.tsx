import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import type { IncidentItem, Line, StationSnapshot } from "@/api/types";
import { initials } from "@/components/ui-kit";

/**
 * «Обзор» — вёрстка 1:1 из дизайн-прототипа (Solvix Chronometry.dc.html,
 * блок isOverview). Живые данные: линии, операторы, инциденты. Метрики,
 * которых нет в системе (план, эффективность), — прочерками на своих местах.
 */

const GRID = "minmax(220px,1.5fr) 170px 110px 190px 150px 160px 170px 40px";

export function OverviewScreen() {
  const navigate = useNavigate();
  const [lines, setLines] = useState<Line[]>([]);
  const [stations, setStations] = useState<StationSnapshot[]>([]);
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [ls, sts, inc] = await Promise.all([
        api.lines.list(),
        api.dashboard.stations(),
        api.dashboard.incidents({ limit: 100 }),
      ]);
      setLines(ls);
      setStations(sts);
      setIncidents(inc);
      setNow(new Date());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить данные");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const operators = useMemo(
    () => stations.filter((s) => s.operator).map((s) => s.operator!.full_name),
    [stations],
  );

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return lines
      .map((line) => ({ line, status: deriveStatus(line) }))
      .filter(({ line }) => !q || line.name.toLowerCase().includes(q))
      .filter(({ status }) => statusFilter === "all" || status.key === statusFilter);
  }, [lines, search, statusFilter]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Шапка страницы — как в прототипе */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24 }}>
        <div style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-0.025em" }}>Обзор</div>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div
            style={{
              display: "flex", alignItems: "center", gap: 10, background: "#ffffff",
              border: "1px solid #EAECF0", borderRadius: 11, padding: "11px 15px",
              fontSize: 14.5, fontWeight: 600, cursor: "pointer",
            }}
          >
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="#475467" strokeWidth="1.6" strokeLinecap="round"><rect x="2.8" y="4" width="14.4" height="13.2" rx="3" /><path d="M6.4 2.4v3M13.6 2.4v3M2.8 8.2h14.4" /></svg>
            Смена: 08:00 – 20:00
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="#98A2B3" strokeWidth="1.8" strokeLinecap="round"><path d="M4 6.5 8 10.5 12 6.5" /></svg>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 12.5, color: "#98A2B3" }}>
            Обновлено: {now.toLocaleTimeString("ru-RU")}
            <div className="animate-fl-pulse" style={{ width: 7, height: 7, borderRadius: 4, background: "#16A34A" }} />
            <svg onClick={() => void load()} style={{ cursor: "pointer" }} width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="#16A34A" strokeWidth="1.6" strokeLinecap="round"><path d="M15.2 7.6A6.4 6.4 0 0 0 4.2 4.6L2.8 6" /><path d="M2.8 10.4a6.4 6.4 0 0 0 11 3l1.4-1.4" /><path d="M2.8 2.6V6h3.4M15.2 15.4V12h-3.4" /></svg>
          </div>
        </div>
      </div>

      {/* KPI — 5 карточек, вёрстка прототипа */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 16 }}>
        <Kpi icon="eff" iconBg="#EFF5FE" iconFg="#3B82F6" label="Эффективность" value="—" note="появится с планом смены" noteColor="#98A2B3" />
        <Kpi icon="box" iconBg="#F3EFFB" iconFg="#7C6FDD" label="Готово / план" value="—" unit="шт" note="появится с планом смены" noteColor="#98A2B3" />
        <Kpi icon="people" iconBg="#EAF7EF" iconFg="#16A34A" label="Сотрудников" value={String(operators.length)} note={`на ${stations.length} станциях`} noteColor="#16A34A" />
        <Kpi icon="warn" iconBg="#FEF3E6" iconFg="#F79009" label="Проблемы" value={String(incidents.length)} note={incidents.length > 0 ? "требуют внимания" : "всё спокойно"} noteColor={incidents.length > 0 ? "#F79009" : "#16A34A"} />
        <Kpi icon="clock" iconBg="#EFF5FE" iconFg="#3B82F6" label="Задержки" value="—" note="появится с топологией транзита" noteColor="#98A2B3" />
      </div>

      {error && (
        <div style={{ background: "#FDEEEC", border: "1px solid #F3C9C5", borderRadius: 14, padding: "16px 20px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 15, color: "#C0453C" }}>{error}</span>
          <button onClick={() => void load()} style={{ background: "#fff", border: "1px solid #F3C9C5", color: "#C0453C", borderRadius: 9, padding: "8px 14px", fontSize: 14, fontWeight: 600 }}>
            Повторить
          </button>
        </div>
      )}

      {/* Заголовок секции + поиск и фильтры */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 20 }}>
        <div style={{ fontSize: 21, fontWeight: 800, letterSpacing: "-0.02em" }}>Сборочные потоки</div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, padding: "0 14px", width: 250, height: 40 }}>
            <svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="#98A2B3" strokeWidth="1.7" strokeLinecap="round"><circle cx="8" cy="8" r="5" /><path d="M11.8 11.8 15.4 15.4" /></svg>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск изделия..."
              style={{ border: "none", outline: "none", fontSize: 14, width: "100%", background: "transparent" }}
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, padding: "0 14px", height: 40, fontSize: 14, color: "#475467", outline: "none" }}
          >
            <option value="all">Статус: Все</option>
            <option value="working">Работает</option>
            <option value="partial">Сниженный темп</option>
            <option value="stopped">Не запущена</option>
            <option value="unset">Не настроена</option>
          </select>
          <div title="Приоритет — появится с планом смены" style={{ display: "flex", alignItems: "center", gap: 10, background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, padding: "0 14px", height: 40, fontSize: 14, color: "#98A2B3", cursor: "default" }}>
            Приоритет: Все
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="#C4CBD4" strokeWidth="1.8" strokeLinecap="round"><path d="M4 6.5 8 10.5 12 6.5" /></svg>
          </div>
          <div title="Сортировка" style={{ width: 42, height: 40, background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>
            <svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="#475467" strokeWidth="1.6" strokeLinecap="round"><path d="M2.6 5.4h12.8M2.6 9h12.8M2.6 12.6h12.8" /><circle cx="6.4" cy="5.4" r="1.6" fill="#ffffff" /><circle cx="11.6" cy="9" r="1.6" fill="#ffffff" /><circle cx="7.4" cy="12.6" r="1.6" fill="#ffffff" /></svg>
          </div>
        </div>
      </div>

      {/* Таблица потоков — точная сетка прототипа */}
      <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 16, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: GRID, gap: 14, padding: "14px 24px", borderBottom: "1px solid #EFF1F4", background: "#FAFBFC", fontSize: 13, color: "#667085", fontWeight: 600 }}>
          <div>Изделие</div><div>Сотрудники</div><div>Операции</div><div>Готово / план</div><div>Эффективность</div><div>Проблемы</div><div>Статус</div><div />
        </div>

        {loading ? (
          <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 10 }}>
            {[0, 1].map((i) => (
              <div key={i} className="animate-fl-pulse" style={{ height: 72, borderRadius: 12, background: "#F3F4F6" }} />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div style={{ padding: "36px 24px", textAlign: "center" }}>
            <div style={{ fontSize: 15, fontWeight: 700 }}>{lines.length === 0 ? "Линий пока нет" : "Ничего не нашлось"}</div>
            <div style={{ fontSize: 13.5, color: "#98A2B3", marginTop: 5 }}>
              {lines.length === 0 ? "Линии заводятся при пусконаладке." : "Попробуйте изменить поиск или фильтр."}
            </div>
          </div>
        ) : (
          rows.map(({ line, status }) => (
            <FlowRow
              key={line.id}
              line={line}
              status={status}
              operators={operators}
              problems={incidents.length}
              onOpen={() => navigate(`/app/overview/${line.id}`)}
            />
          ))
        )}

        {!loading && (
          <div style={{ padding: "14px 24px", fontSize: 13.5, color: "#98A2B3" }}>
            Показано {rows.length} из {lines.length} потоков
          </div>
        )}
      </div>
    </div>
  );
}

// === KPI карточка (вёрстка прототипа) ===

function Kpi({
  icon, iconBg, iconFg, label, value, unit, note, noteColor, bar,
}: {
  icon: "eff" | "box" | "people" | "warn" | "clock";
  iconBg: string;
  iconFg: string;
  label: string;
  value: string;
  unit?: string;
  note?: string;
  noteColor?: string;
  bar?: number;
}) {
  const dim = value === "—";
  return (
    <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 14, padding: "18px 20px", display: "flex", flexDirection: "column", gap: 11 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ width: 40, height: 40, borderRadius: 11, background: iconBg, display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>
          <KpiIcon kind={icon} color={iconFg} />
        </div>
        <div style={{ fontSize: 13.5, color: "#667085" }}>{label}</div>
      </div>
      <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: "-0.02em", color: dim ? "#C4CBD4" : undefined }}>
        {value}
        {unit && <span style={{ fontSize: 15, fontWeight: 600, color: dim ? "#C4CBD4" : "#667085" }}> {unit}</span>}
      </div>
      {bar !== undefined && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ flex: 1, height: 7, borderRadius: 4, background: "#F0F1F4", overflow: "hidden" }}>
            <div style={{ width: `${bar}%`, height: 7, borderRadius: 4, background: "#16A34A" }} />
          </div>
          <div style={{ fontSize: 12.5, color: "#667085" }}>{bar}%</div>
        </div>
      )}
      {note && <div style={{ fontSize: 13, fontWeight: 600, color: noteColor ?? "#98A2B3" }}>{note}</div>}
    </div>
  );
}

function KpiIcon({ kind, color }: { kind: string; color: string }) {
  const p = { width: 19, height: 19, viewBox: "0 0 20 20", fill: "none", stroke: color, strokeWidth: 1.7, strokeLinecap: "round" as const };
  switch (kind) {
    case "eff":
      return <svg {...p} strokeLinejoin="round"><path d="M3 13.6 7.6 8.8l3 2.7L17 5" /><path d="M12.6 5H17v4.4" /></svg>;
    case "box":
      return <svg {...p} strokeLinejoin="round"><path d="M10 2.6 16.6 6v8L10 17.4 3.4 14V6Z" /><path d="M3.4 6 10 9.6 16.6 6M10 9.6v7.8" /></svg>;
    case "people":
      return <svg {...p}><circle cx="8" cy="7.2" r="2.8" /><path d="M2.8 16.4c0-2.9 2.3-4.8 5.2-4.8s5.2 1.9 5.2 4.8" /><path d="M14.2 5.2a2.6 2.6 0 0 1 0 5" /><path d="M15.4 11.9c1.5.5 2.4 1.8 2.4 3.6" /></svg>;
    case "warn":
      return <svg {...p} strokeLinejoin="round"><path d="M10 3.2 18 16.6H2Z" /><path d="M10 8.2v3.4" /><path d="M10 14.2h.01" /></svg>;
    default:
      return <svg {...p}><circle cx="10" cy="10" r="7.4" /><path d="M10 5.6V10l3 2" /></svg>;
  }
}

// === Строка потока ===

interface RowStatus { key: string; label: string; fg: string; bg: string }

function FlowRow({
  line, status, operators, problems, onOpen,
}: {
  line: Line; status: RowStatus; operators: string[]; problems: number; onOpen: () => void;
}) {
  const [hover, setHover] = useState(false);
  const shown = operators.slice(0, 3);
  const more = operators.length - shown.length;

  return (
    <div
      onClick={onOpen}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "grid", gridTemplateColumns: GRID, gap: 14, padding: "18px 24px",
        borderBottom: "1px solid #F3F4F6", alignItems: "center", cursor: "pointer",
        background: hover ? "#FBFCFD" : undefined,
      }}
    >
      {/* Изделие */}
      <div style={{ display: "flex", alignItems: "center", gap: 13, minWidth: 0 }}>
        <div style={{ width: 40, height: 40, borderRadius: 11, background: "#EFF5FE", display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#3B82F6" strokeWidth="1.6" strokeLinejoin="round"><path d="M10 2.6 16.6 6v8L10 17.4 3.4 14V6Z" /><path d="M3.4 6 10 9.6 16.6 6M10 9.6v7.8" /></svg>
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 15.5, fontWeight: 700, letterSpacing: "-0.01em", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{line.name}</div>
          <div style={{ fontSize: 12.5, color: "#98A2B3", marginTop: 2 }}>
            {line.has_topology ? `Станций: ${line.station_count}` : "Схема сборки не настроена"}
          </div>
        </div>
      </div>

      {/* Сотрудники — аватары внахлёст, как в прототипе */}
      <div style={{ display: "flex", alignItems: "center", paddingLeft: 8 }}>
        {shown.length === 0 ? (
          <span style={{ fontSize: 13.5, color: "#C4CBD4" }}>—</span>
        ) : (
          <>
            {shown.map((name, i) => (
              <div key={i} title={name} style={{ width: 34, height: 34, borderRadius: 17, background: "#E7EDF3", border: "2px solid #ffffff", marginLeft: -8, fontSize: 11.5, fontWeight: 700, color: "#475467", display: "flex", alignItems: "center", justifyContent: "center" }}>
                {initials(name)}
              </div>
            ))}
            {more > 0 && (
              <div style={{ width: 34, height: 34, borderRadius: 17, background: "#F1F3F6", border: "2px solid #ffffff", marginLeft: -8, fontSize: 11.5, fontWeight: 700, color: "#667085", display: "flex", alignItems: "center", justifyContent: "center" }}>
                +{more}
              </div>
            )}
          </>
        )}
      </div>

      {/* Операции */}
      <div style={{ fontSize: 15, fontWeight: 600 }}>{line.process_count}</div>

      {/* Готово / план — заглушка */}
      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        <div style={{ fontSize: 14.5, fontWeight: 600, color: "#C4CBD4" }}>
          — / — <span style={{ color: "#C4CBD4", fontWeight: 500 }}>шт</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <div style={{ flex: 1, height: 7, borderRadius: 4, background: "#F0F1F4" }} />
          <div style={{ fontSize: 12.5, color: "#C4CBD4", width: 34, textAlign: "right" }}>—%</div>
        </div>
      </div>

      {/* Эффективность — заглушка */}
      <div>
        <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: "-0.01em", color: "#C4CBD4" }}>—</div>
        <div style={{ fontSize: 13, fontWeight: 600, color: "#C4CBD4", marginTop: 3 }}>нет данных</div>
      </div>

      {/* Проблемы */}
      <div>
        <div style={{ fontSize: 16, fontWeight: 700, color: problems > 0 ? undefined : "#C4CBD4" }}>{problems}</div>
        <div style={{ fontSize: 13, fontWeight: 600, color: problems > 0 ? "#F79009" : "#98A2B3", marginTop: 3 }}>
          {problems > 0 ? "Требует внимания" : "Нет проблем"}
        </div>
      </div>

      {/* Статус */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13.5, fontWeight: 600, color: status.fg, background: status.bg, padding: "7px 13px", borderRadius: 9, justifySelf: "start" }}>
        <div style={{ width: 7, height: 7, borderRadius: 4, background: status.fg }} />
        {status.label}
      </div>

      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="#98A2B3" strokeWidth="1.7" strokeLinecap="round" style={{ justifySelf: "end" }}><path d="M6.6 4 11.6 9l-5 5" /></svg>
    </div>
  );
}

function deriveStatus(line: Line): RowStatus {
  if (line.station_count === 0 || !line.has_topology) {
    return { key: "unset", label: "Не настроена", fg: "#98A2B3", bg: "#F1F3F6" };
  }
  if (line.active_station_count === 0) {
    return { key: "stopped", label: "Не запущена", fg: "#98A2B3", bg: "#F1F3F6" };
  }
  if (line.active_station_count < line.station_count) {
    return { key: "partial", label: "Сниженный темп", fg: "#F79009", bg: "#FEF3E6" };
  }
  return { key: "working", label: "Работает", fg: "#16A34A", bg: "#EAF7EF" };
}
