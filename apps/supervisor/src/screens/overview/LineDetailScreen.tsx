import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import type { IncidentItem, StationSnapshot, Topology, TopologyNode } from "@/api/types";
import { initials } from "@/components/ui-kit";

/**
 * «Обзор дерева» — вёрстка 1:1 из дизайн-прототипа (блок isTree).
 * Канва: SVG-рёбра + HTML-карточки станций с абсолютным позиционированием,
 * подписи уровней слева, зум, легенда. Правая панель 344px с border-left.
 *
 * Живое: топология, операторы, последние события, инциденты.
 * Заглушки до плана смены: готово/план, эффективность, транзит, очередь.
 */

// Геометрия канвы (из прототипа: базовый уровень — вертикальные карточки,
// верхние — горизонтальные).
const BASE_W = 118;
const BASE_H = 140;
const UP_W = 210;
const UP_H = 96;
const LEVEL_GAP = 76;
const PAD_Y = 20;
const GAP_X = 22;

type NodeStatus = "working" | "scanning" | "paused" | "idle" | "error" | "empty";

const STATUS: Record<NodeStatus, { dot: string; label: string; bg: string }> = {
  working: { dot: "#16A34A", label: "Работает", bg: "#EAF7EF" },
  scanning: { dot: "#3B82F6", label: "Сканирование", bg: "#EFF5FE" },
  paused: { dot: "#F79009", label: "Пауза", bg: "#FEF3E6" },
  idle: { dot: "#98A2B3", label: "Простой", bg: "#F1F3F6" },
  error: { dot: "#C0453C", label: "Проблема", bg: "#FDEEEC" },
  empty: { dot: "#C4CBD4", label: "Не назначен", bg: "#F6F7F9" },
};

function deriveStatus(snap: StationSnapshot | undefined): NodeStatus {
  if (!snap || !snap.operator) return "empty";
  const t = snap.last_event?.type;
  if (!t) return "idle";
  switch (t) {
    case "start": return "working";
    case "scan_in": case "scan_out": return "scanning";
    case "break_start": return "paused";
    case "error": case "anomaly": case "interrupted": return "error";
    default: return "idle";
  }
}

export function LineDetailScreen() {
  const { lineId } = useParams<{ lineId: string }>();
  const [topology, setTopology] = useState<Topology | null>(null);
  const [stations, setStations] = useState<StationSnapshot[]>([]);
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<TopologyNode | null>(null);
  const [zoom, setZoom] = useState(1);
  const [showLegend, setShowLegend] = useState(true);
  const [now, setNow] = useState(() => new Date());

  const load = useCallback(async () => {
    if (!lineId) return;
    setLoading(true);
    setError(null);
    try {
      const [topo, sts, inc] = await Promise.all([
        api.processes.topology(lineId),
        api.dashboard.stations(),
        api.dashboard.incidents({ limit: 50 }),
      ]);
      setTopology(topo);
      setStations(sts);
      setIncidents(inc);
      setNow(new Date());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить линию");
    } finally {
      setLoading(false);
    }
  }, [lineId]);

  useEffect(() => { void load(); }, [load]);

  const stationById = useMemo(() => new Map(stations.map((s) => [s.id, s])), [stations]);
  /** Инциденты только этой линии: по станкам из топологии. */
  const lineIncidents = useMemo(() => {
    if (!topology) return incidents;
    const ids = new Set(topology.nodes.map((n) => n.station_id));
    return incidents.filter((i) => ids.has(i.station_id));
  }, [incidents, topology]);
  const operatorCount = useMemo(
    () => topology?.nodes.filter((n) => stationById.get(n.station_id)?.operator).length ?? 0,
    [topology, stationById],
  );
  const running = operatorCount > 0;

  return (
    // Вырываемся из паддинга AppLayout: макет дерева — full-bleed с панелью справа.
    <div style={{ margin: "-30px -34px -40px", display: "flex", alignItems: "stretch", minHeight: "100vh" }}>
      {/* Основная колонка */}
      <div style={{ flex: 1, minWidth: 0, padding: "26px 30px 34px", display: "flex", flexDirection: "column", gap: 20 }}>
        {/* Шапка */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 24 }}>
          <div>
            <Link to="/app/overview" style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 14.5, color: "#667085", textDecoration: "none" }}>
              <svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M15 9H3" /><path d="M7 5 3 9l4 4" /></svg>
              Назад к обзору
            </Link>
            <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 12 }}>
              <div style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-0.025em" }}>{topology?.line_name ?? "Линия"}</div>
              <div style={{ fontSize: 13.5, fontWeight: 600, color: running ? "#16A34A" : "#98A2B3", background: running ? "#EAF7EF" : "#F1F3F6", padding: "7px 13px", borderRadius: 9 }}>
                {running ? "В работе" : "Не запущена"}
              </div>
            </div>
            <div style={{ fontSize: 14, color: "#667085", marginTop: 8 }}>
              Финальная сборка
              {topology && topology.final_output_types.length > 0 && <> &nbsp;•&nbsp; Выход: {topology.final_output_types.join(", ")}</>}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, padding: "11px 15px", fontSize: 14.5, fontWeight: 600, cursor: "pointer" }}>
              <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="#475467" strokeWidth="1.6" strokeLinecap="round"><rect x="2.8" y="4" width="14.4" height="13.2" rx="3" /><path d="M6.4 2.4v3M13.6 2.4v3M2.8 8.2h14.4" /></svg>
              Смена: 08:00 – 20:00
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="#98A2B3" strokeWidth="1.8" strokeLinecap="round"><path d="M4 6.5 8 10.5 12 6.5" /></svg>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 12.5, color: "#98A2B3" }}>
              Обновлено: {now.toLocaleTimeString("ru-RU")}
              <div className="animate-fl-pulse" style={{ width: 7, height: 7, borderRadius: 4, background: "#16A34A" }} />
            </div>
          </div>
        </div>

        {/* KPI линии — компактнее, чем на Обзоре (по прототипу) */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 14 }}>
          <TreeKpi icon="box" iconBg="#F3EFFB" iconFg="#7C6FDD" label="Готово / план" value="—" unit="шт" note="появится с планом смены" noteColor="#98A2B3" />
          <TreeKpi icon="eff" iconBg="#EFF5FE" iconFg="#3B82F6" label="Эффективность" value="—" note="появится с планом смены" noteColor="#98A2B3" />
          <TreeKpi icon="people" iconBg="#EAF7EF" iconFg="#16A34A" label="Сотрудников" value={topology ? `${operatorCount} / ${topology.nodes.length}` : "—"} note={topology && operatorCount < topology.nodes.length ? `${topology.nodes.length - operatorCount} станций свободно` : "все станции заняты"} noteColor="#16A34A" />
          <TreeKpi icon="warn" iconBg="#FEF3E6" iconFg="#F79009" label="Проблемы" value={String(lineIncidents.length)} note={lineIncidents.length > 0 ? "требуют внимания" : "всё спокойно"} noteColor={lineIncidents.length > 0 ? "#F79009" : "#16A34A"} />
          <TreeKpi icon="clock" iconBg="#EFF5FE" iconFg="#3B82F6" label="Задержки" value="—" note="появится с топологией" noteColor="#98A2B3" />
        </div>

        {error && (
          <div style={{ background: "#FDEEEC", border: "1px solid #F3C9C5", borderRadius: 14, padding: "14px 18px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 14.5, color: "#C0453C" }}>{error}</span>
            <button onClick={() => void load()} style={{ background: "#fff", border: "1px solid #F3C9C5", color: "#C0453C", borderRadius: 9, padding: "7px 13px", fontSize: 13.5, fontWeight: 600 }}>Повторить</button>
          </div>
        )}

        {/* Тулбар: легенда + зум */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10 }}>
          <div onClick={() => setShowLegend((v) => !v)} style={{ display: "flex", alignItems: "center", gap: 9, background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, padding: "9px 14px", fontSize: 14, color: "#475467", cursor: "pointer" }}>
            <svg width="16" height="16" viewBox="0 0 18 18" fill="none" stroke="#98A2B3" strokeWidth="1.6" strokeLinecap="round"><circle cx="9" cy="9" r="6.6" /><path d="M9 8.2v4" /><circle cx="9" cy="5.9" r=".8" fill="#98A2B3" stroke="none" /></svg>
            Легенда
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 4, background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, padding: "5px 8px" }}>
            <div onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.1).toFixed(1)))} style={{ width: 30, height: 30, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", fontSize: 17, color: "#475467" }}>−</div>
            <div style={{ fontSize: 14, fontWeight: 600, width: 52, textAlign: "center" }}>{Math.round(zoom * 100)}%</div>
            <div onClick={() => setZoom((z) => Math.min(1.5, +(z + 0.1).toFixed(1)))} style={{ width: 30, height: 30, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", fontSize: 17, color: "#475467" }}>+</div>
          </div>
          <div onClick={() => setZoom(1)} title="Вписать" style={{ width: 42, height: 42, background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>
            <svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="#475467" strokeWidth="1.6" strokeLinecap="round"><path d="M6.6 2.6H2.6v4M11.4 2.6h4v4M11.4 15.4h4v-4M6.6 15.4h-4v-4" /></svg>
          </div>
        </div>

        {/* Канва дерева */}
        <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 16, padding: "24px 14px 24px 102px", overflow: "auto" }}>
          {loading ? (
            <div className="animate-fl-pulse" style={{ height: 360, borderRadius: 12, background: "#F3F4F6" }} />
          ) : topology && topology.nodes.length > 0 ? (
            <TreeCanvas
              topology={topology}
              stationById={stationById}
              zoom={zoom}
              selectedId={selected?.station_id ?? null}
              onPick={(n) => setSelected(selected?.station_id === n.station_id ? null : n)}
            />
          ) : (
            <div style={{ padding: "48px 20px", textAlign: "center", color: "#98A2B3", fontSize: 14 }}>
              Схема появится, когда в справочнике будут операции с указанными станками
              {topology?.warnings.map((w, i) => (
                <div key={i} style={{ marginTop: 8, fontSize: 13, color: "#B4740A" }}>{w}</div>
              ))}
            </div>
          )}
        </div>

        {/* Легенда */}
        {showLegend && (
          <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 14, padding: "15px 22px", display: "flex", flexWrap: "wrap", gap: 28, alignItems: "center" }}>
            {(Object.keys(STATUS) as NodeStatus[]).map((key) => (
              <div key={key} style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 13.5, color: "#475467" }}>
                <div style={{ width: 22, height: 22, borderRadius: 11, background: STATUS[key].bg, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <div style={{ width: 8, height: 8, borderRadius: 4, background: STATUS[key].dot }} />
                </div>
                {STATUS[key].label}
              </div>
            ))}
            <div style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 13.5, color: "#475467" }}>
              <div style={{ display: "flex", gap: 3 }}>
                <div style={{ width: 10, height: 10, borderRadius: 3, background: "#E06A62" }} />
                <div style={{ width: 10, height: 10, borderRadius: 3, background: "#E06A62", opacity: 0.55 }} />
              </div>
              Очередь на линии
            </div>
            <div style={{ fontSize: 13, color: "#98A2B3", marginLeft: "auto" }}>Кликните станцию — её карточка справа</div>
          </div>
        )}
      </div>

      {/* Правая панель — 344px, border-left, как в прототипе */}
      {selected && (
        <NodePanel
          node={selected}
          snap={stationById.get(selected.station_id)}
          topology={topology!}
          incidents={lineIncidents.filter((i) => i.station_id === selected.station_id)}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

// === KPI дерева (компактная карточка прототипа) ===

function TreeKpi({ icon, iconBg, iconFg, label, value, unit, note, noteColor }: {
  icon: string; iconBg: string; iconFg: string; label: string; value: string; unit?: string; note?: string; noteColor?: string;
}) {
  const dim = value === "—";
  const p = { width: 17, height: 17, viewBox: "0 0 20 20", fill: "none", stroke: iconFg, strokeWidth: 1.7, strokeLinecap: "round" as const };
  const icons: Record<string, React.ReactNode> = {
    eff: <svg {...p} strokeLinejoin="round"><path d="M3 13.6 7.6 8.8l3 2.7L17 5" /><path d="M12.6 5H17v4.4" /></svg>,
    box: <svg {...p} strokeLinejoin="round"><path d="M10 2.6 16.6 6v8L10 17.4 3.4 14V6Z" /><path d="M3.4 6 10 9.6 16.6 6M10 9.6v7.8" /></svg>,
    people: <svg {...p}><circle cx="8" cy="7.2" r="2.8" /><path d="M2.8 16.4c0-2.9 2.3-4.8 5.2-4.8s5.2 1.9 5.2 4.8" /><path d="M14.2 5.2a2.6 2.6 0 0 1 0 5" /><path d="M15.4 11.9c1.5.5 2.4 1.8 2.4 3.6" /></svg>,
    warn: <svg {...p} strokeLinejoin="round"><path d="M10 3.2 18 16.6H2Z" /><path d="M10 8.2v3.4" /><path d="M10 14.2h.01" /></svg>,
    clock: <svg {...p}><circle cx="10" cy="10" r="7.4" /><path d="M10 5.6V10l3 2" /></svg>,
  };
  return (
    <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 14, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 9 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
        <div style={{ width: 36, height: 36, borderRadius: 10, background: iconBg, display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>{icons[icon]}</div>
        <div style={{ fontSize: 13, color: "#667085" }}>{label}</div>
      </div>
      <div style={{ fontSize: 23, fontWeight: 800, letterSpacing: "-0.02em", color: dim ? "#C4CBD4" : undefined }}>
        {value}{unit && <span style={{ fontSize: 14, fontWeight: 600, color: dim ? "#C4CBD4" : "#667085" }}> {unit}</span>}
      </div>
      {note && <div style={{ fontSize: 12.5, fontWeight: 600, color: noteColor ?? "#98A2B3" }}>{note}</div>}
    </div>
  );
}

// === Канва: SVG-рёбра + HTML-карточки, как в прототипе ===

function TreeCanvas({
  topology, stationById, zoom, selectedId, onPick,
}: {
  topology: Topology;
  stationById: Map<string, StationSnapshot>;
  zoom: number;
  selectedId: string | null;
  onPick: (n: TopologyNode) => void;
}) {
  const layout = useMemo(() => {
    const byLevel = new Map<number, TopologyNode[]>();
    for (const n of topology.nodes) {
      const arr = byLevel.get(n.level) ?? [];
      arr.push(n);
      byLevel.set(n.level, arr);
    }
    const levels = [...byLevel.keys()].sort((a, b) => a - b);

    // Ширина: по самому «широкому» уровню.
    let width = 560;
    for (const lvl of levels) {
      const count = byLevel.get(lvl)!.length;
      const w = lvl === 0 ? BASE_W : UP_W;
      width = Math.max(width, count * (w + GAP_X) + 40);
    }

    // Высота: базовый уровень внизу.
    const heightOf = (lvl: number) => (lvl === 0 ? BASE_H : UP_H);
    let height = PAD_Y * 2;
    for (const lvl of levels) height += heightOf(lvl);
    height += (levels.length - 1) * LEVEL_GAP;

    // Позиции: y снизу вверх.
    const rect = new Map<string, { x: number; y: number; w: number; h: number }>();
    const levelMeta: { y: number; name: string; sub: string }[] = [];
    let yCursor = height - PAD_Y;
    for (const lvl of levels) {
      const nodes = byLevel.get(lvl)!;
      const w = lvl === 0 ? BASE_W : UP_W;
      const h = heightOf(lvl);
      yCursor -= h;
      const slot = width / (nodes.length + 1);
      nodes.forEach((n, i) => {
        rect.set(n.station_id, { x: slot * (i + 1) - w / 2, y: yCursor, w, h });
      });
      levelMeta.push({
        y: yCursor + h / 2 - 16,
        name: `Уровень ${lvl + 1}`,
        sub: `${nodes.length} ${plural(nodes.length, "станция", "станции", "станций")}`,
      });
      yCursor -= LEVEL_GAP;
    }

    return { width, height, rect, levelMeta };
  }, [topology]);

  const { width, height, rect, levelMeta } = layout;

  return (
    <div style={{ position: "relative", width: width * zoom, height: height * zoom }}>
      <div style={{ position: "relative", width, height, transform: `scale(${zoom})`, transformOrigin: "top left" }}>
        {/* Рёбра */}
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ position: "absolute", inset: 0 }} fill="none">
          {topology.nodes.flatMap((n) =>
            n.fed_by.map((src) => {
              const from = rect.get(src);
              const to = rect.get(n.station_id);
              if (!from || !to) return null;
              const x1 = from.x + from.w / 2;
              const y1 = from.y;
              const x2 = to.x + to.w / 2;
              const y2 = to.y + to.h;
              const midY = (y1 + y2) / 2;
              return (
                <path
                  key={`${src}-${n.station_id}`}
                  d={`M ${x1} ${y1} L ${x1} ${midY} L ${x2} ${midY} L ${x2} ${y2}`}
                  stroke="#CBD2DC"
                  strokeWidth={1.6}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              );
            }),
          )}
        </svg>

        {/* Подписи уровней слева (в зоне padding-left:102px канвы) */}
        {levelMeta.map((l, i) => (
          <div key={i} style={{ position: "absolute", left: -90, top: l.y, width: 82, textAlign: "right" }}>
            <div style={{ fontSize: 13.5, fontWeight: 700, color: "#475467" }}>{l.name}</div>
            <div style={{ fontSize: 12.5, color: "#98A2B3", marginTop: 3 }}>{l.sub}</div>
          </div>
        ))}

        {/* Карточки */}
        {topology.nodes.map((n) => {
          const r = rect.get(n.station_id);
          if (!r) return null;
          const snap = stationById.get(n.station_id);
          const status = deriveStatus(snap);
          const sel = selectedId === n.station_id;
          const operator = snap?.operator?.full_name ?? null;
          const border = sel ? "#16A34A" : STATUS[status].dot === "#C0453C" ? "#F3C9C5" : "#E7EAEE";

          if (n.level === 0) {
            // Вертикальная карточка базового уровня
            return (
              <div
                key={n.station_id}
                onClick={() => onPick(n)}
                style={{
                  position: "absolute", left: r.x, top: r.y, width: r.w, height: r.h,
                  background: "#ffffff", border: `1.5px solid ${border}`, borderRadius: 14,
                  padding: "12px 8px", display: "flex", flexDirection: "column", alignItems: "center",
                  justifyContent: "center", gap: 6, cursor: "pointer",
                  boxShadow: "0 1px 3px rgba(16,24,40,0.05)",
                }}
              >
                <div style={{ position: "relative" }}>
                  <div style={{ width: 38, height: 38, borderRadius: 19, background: operator ? "#E7EDF3" : "#F1F3F6", color: operator ? "#475467" : "#C4CBD4", fontSize: 12.5, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center" }}>
                    {operator ? initials(operator) : "—"}
                  </div>
                  <div style={{ position: "absolute", right: -2, top: 0, width: 9, height: 9, borderRadius: 5, background: STATUS[status].dot, border: "1.5px solid #ffffff" }} />
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, textAlign: "center", lineHeight: 1.25, maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {operator ? shortName(operator) : "Не назначен"}
                </div>
                <div style={{ fontSize: 12, color: "#98A2B3", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "100%" }}>{n.station_name}</div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#C4CBD4" }}>— / —</div>
              </div>
            );
          }

          // Горизонтальная карточка верхних уровней
          return (
            <div
              key={n.station_id}
              onClick={() => onPick(n)}
              style={{
                position: "absolute", left: r.x, top: r.y, width: r.w, height: r.h,
                background: "#ffffff", border: `1.5px solid ${border}`, borderRadius: 14,
                padding: "12px 14px", display: "flex", flexDirection: "column",
                justifyContent: "center", gap: 10, cursor: "pointer",
                boxShadow: "0 1px 3px rgba(16,24,40,0.05)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 32, height: 32, borderRadius: 16, background: operator ? "#E7EDF3" : "#F1F3F6", color: operator ? "#475467" : "#C4CBD4", fontSize: 11.5, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>
                  {operator ? initials(operator) : "—"}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14.5, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {operator ? shortName(operator) : "Не назначен"}
                  </div>
                  <div style={{ fontSize: 12.5, color: "#98A2B3", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{n.station_name}</div>
                </div>
                <div style={{ width: 8, height: 8, borderRadius: 4, background: STATUS[status].dot, flex: "0 0 auto" }} />
              </div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, fontSize: 13.5, fontWeight: 600, color: "#C4CBD4" }}>
                <svg width="15" height="15" viewBox="0 0 18 18" fill="none" stroke="#C4CBD4" strokeWidth="1.6" strokeLinecap="round"><circle cx="9" cy="6.6" r="2.6" /><path d="M4 14.6c0-2.6 2.2-4.2 5-4.2s5 1.6 5 4.2" /></svg>
                — / —
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// === Правая панель станции (branch showNode прототипа) ===

function NodePanel({
  node, snap, topology, incidents, onClose,
}: {
  node: TopologyNode;
  snap: StationSnapshot | undefined;
  topology: Topology;
  incidents: IncidentItem[];
  onClose: () => void;
}) {
  const status = deriveStatus(snap);
  const meta = STATUS[status];
  const operator = snap?.operator?.full_name ?? null;
  const upTo = node.feeds_into
    .map((id) => topology.nodes.find((n) => n.station_id === id)?.station_name)
    .filter(Boolean)
    .join(", ");

  return (
    <div style={{ width: 344, flex: "0 0 auto", background: "#ffffff", borderLeft: "1px solid #EDEFF2", padding: "26px 24px", display: "flex", flexDirection: "column", gap: 22 }} className="animate-fl-fade">
      {/* Шапка */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <div>
          <div style={{ fontSize: 21, fontWeight: 800, letterSpacing: "-0.02em" }}>{operator ?? "Не назначен"}</div>
          <div style={{ fontSize: 13.5, color: "#667085", marginTop: 6 }}>{node.station_name} &nbsp;•&nbsp; Уровень {node.level + 1}</div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 600, color: meta.dot, background: meta.bg, padding: "6px 12px", borderRadius: 8, marginTop: 10, width: "fit-content" }}>
            <div style={{ width: 7, height: 7, borderRadius: 4, background: meta.dot }} />{meta.label}
          </div>
        </div>
        <div onClick={onClose} style={{ width: 28, height: 28, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flex: "0 0 auto" }}>
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="#98A2B3" strokeWidth="1.7" strokeLinecap="round"><path d="M4 4l8 8M12 4l-8 8" /></svg>
        </div>
      </div>

      {/* Текущее задание */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>Текущее задание</div>
        <div style={{ border: "1px solid #EAECF0", borderRadius: 13, padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontSize: 15, fontWeight: 700 }}>{node.input_types.join(" + ")} → {node.output_types.join(", ")}</div>
            {snap?.last_event?.part_id && (
              <div style={{ fontSize: 12.5, fontWeight: 600, color: "#3B82F6", background: "#EFF5FE", padding: "5px 10px", borderRadius: 7 }}>{snap.last_event.part_id}</div>
            )}
          </div>
          <RowKV k="План" v="— шт" dim />
          <RowKV k="Готово" v="— шт (—%)" dim />
          <div style={{ height: 7, borderRadius: 4, background: "#F0F1F4" }} />
        </div>
      </div>

      {/* Передача вверх */}
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{ fontSize: 15, fontWeight: 700, paddingBottom: 10 }}>Передача вверх</div>
        <RowLine k="Кому" v={upTo || "Выход линии"} />
        <RowLine k="Деталь" v={node.output_types.join(", ")} />
        <RowLine k="Ожидаемое время" v="—" dim last />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingTop: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <div style={{ width: 22, height: 22, borderRadius: 11, background: "#F1F3F6", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="#98A2B3" strokeWidth="1.8" strokeLinejoin="round"><path d="M10 2.6 16.6 6v8L10 17.4 3.4 14V6Z" /><path d="M3.4 6 10 9.6 16.6 6M10 9.6v7.8" /></svg>
            </div>
            <div style={{ fontSize: 13.5, color: "#98A2B3" }}>Деталь в пути — данных пока нет</div>
          </div>
        </div>
        <div style={{ height: 4, borderRadius: 2, background: "#EAF7EF", marginTop: 10 }} />
      </div>

      {/* Очередь на вход */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ fontSize: 15, fontWeight: 700 }}>Очередь на вход</div>
          <div style={{ fontSize: 12.5, fontWeight: 600, color: "#98A2B3", background: "#F1F3F6", padding: "5px 10px", borderRadius: 7 }}>—</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 22, height: 22, borderRadius: 11, background: "#F1F3F6", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="#98A2B3" strokeWidth="1.8" strokeLinejoin="round"><path d="M10 2.6 16.6 6v8L10 17.4 3.4 14V6Z" /><path d="M3.4 6 10 9.6 16.6 6M10 9.6v7.8" /></svg>
          </div>
          <div style={{ fontSize: 13.5, color: "#475467" }}>Появится с отслеживанием транзита</div>
        </div>
      </div>

      {/* События */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>События</div>
        {snap?.last_event && (
          <EventCard color="#3B82F6" bg="#F7FAFF" title={eventLabel(snap.last_event.type)} text={snap.last_event.part_id ? `Деталь ${snap.last_event.part_id}` : node.station_name} time={fmtTime(snap.last_event.at)} />
        )}
        {incidents.slice(0, 3).map((inc) => (
          <EventCard
            key={inc.id}
            color="#C0453C"
            bg="#FDF3F2"
            title={inc.event_type === "anomaly" ? anomalyLabel(inc.details) : "Ошибка"}
            text={inc.part_id ? `Деталь ${inc.part_id}` : inc.station_name}
            time={fmtTime(inc.timestamp)}
          />
        ))}
        {!snap?.last_event && incidents.length === 0 && (
          <div style={{ fontSize: 13.5, color: "#C4CBD4" }}>За смену событий не было</div>
        )}
      </div>

      {/* История передач */}
      <div style={{ border: "1px solid #EAECF0", borderRadius: 12, padding: "14px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "default", opacity: 0.6 }} title="Появится с отслеживанием транзита">
        <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, fontWeight: 600, color: "#475467" }}>
          <svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="#98A2B3" strokeWidth="1.6" strokeLinecap="round"><circle cx="9" cy="9" r="6.6" /><path d="M9 5.4V9l2.6 1.8" /></svg>
          История передач
        </div>
        <svg width="16" height="16" viewBox="0 0 18 18" fill="none" stroke="#98A2B3" strokeWidth="1.7" strokeLinecap="round"><path d="M6.6 4 11.6 9l-5 5" /></svg>
      </div>
    </div>
  );
}

// === Мелочи ===

function RowKV({ k, v, dim }: { k: string; v: string; dim?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <div style={{ fontSize: 13.5, color: "#667085" }}>{k}</div>
      <div style={{ fontSize: 13.5, fontWeight: 600, color: dim ? "#C4CBD4" : undefined }}>{v}</div>
    </div>
  );
}

function RowLine({ k, v, dim, last }: { k: string; v: string; dim?: boolean; last?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: last ? "none" : "1px solid #F3F4F6" }}>
      <div style={{ fontSize: 13.5, color: "#667085" }}>{k}</div>
      <div style={{ fontSize: 13.5, fontWeight: 600, textAlign: "right", color: dim ? "#C4CBD4" : undefined }}>{v}</div>
    </div>
  );
}

function EventCard({ color, bg, title, text, time }: { color: string; bg: string; title: string; text: string; time: string }) {
  return (
    <div style={{ background: bg, borderRadius: 11, padding: "12px 14px", display: "flex", justifyContent: "space-between", gap: 12 }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 7, height: 7, borderRadius: 4, background: color }} />
          <div style={{ fontSize: 13.5, fontWeight: 600, color }}>{title}</div>
        </div>
        <div style={{ fontSize: 12.5, color: "#667085", marginTop: 5 }}>{text}</div>
      </div>
      <div style={{ fontSize: 12.5, color: "#98A2B3", flex: "0 0 auto" }}>{time}</div>
    </div>
  );
}

function shortName(fullName: string): string {
  const [last, first] = fullName.split(/\s+/);
  return first ? `${last} ${first[0]}.` : last;
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

function eventLabel(type: string): string {
  const map: Record<string, string> = {
    scan_in: "Скан входящей", start: "Старт операции", stop: "Стоп",
    scan_out: "Скан исходящей", break_start: "Начало паузы", break_end: "Конец паузы",
    error: "Ошибка", interrupted: "Операция прервана", anomaly: "Аномалия",
  };
  return map[type] ?? type;
}

function anomalyLabel(details: Record<string, unknown> | null): string {
  const kind = details?.kind;
  const map: Record<string, string> = {
    norm_exceeded: "Превышен норматив", pause_exceeded: "Затянулась пауза",
    station_idle: "Простой станции", transit_stuck: "Деталь застряла",
  };
  return typeof kind === "string" ? (map[kind] ?? "Аномалия") : "Аномалия";
}

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}
