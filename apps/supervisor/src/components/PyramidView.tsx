import { useMemo } from "react";
import type { StationSnapshot, Topology, TopologyNode } from "@/api/types";
import { initials } from "@/components/ui-kit";

/**
 * Пирамида сборки по макету «Обзор дерева».
 *
 * Карточка станка: аватар оператора, имя, станция, статус-точка, «готово/план»
 * (пока прочерк — до плана смены). Линии со стрелками вверх, маркеры деталей
 * на рёбрах, легенда снизу. Укладка по уровням — Решение №88.
 *
 * Статус узла выводится из последнего события станка (снимок dashboard);
 * реалтайм-обновление добавится блоком WebSocket.
 */

const NODE_W = 172;
const NODE_H = 96;
const LEVEL_GAP = 84;
const PAD = 28;

export type NodeStatus = "working" | "scanning" | "paused" | "idle" | "error" | "empty";

export const STATUS_META: Record<NodeStatus, { dot: string; label: string }> = {
  working: { dot: "#16A34A", label: "Работает" },
  scanning: { dot: "#3B82F6", label: "Сканирование" },
  paused: { dot: "#F79009", label: "Пауза" },
  idle: { dot: "#98A2B3", label: "Простой" },
  error: { dot: "#C0453C", label: "Проблема" },
  empty: { dot: "#C4CBD4", label: "Не назначен" },
};

export function deriveNodeStatus(snap: StationSnapshot | undefined): NodeStatus {
  if (!snap || !snap.operator) return "empty";
  const t = snap.last_event?.type;
  if (!t) return "idle";
  switch (t) {
    case "start":
      return "working";
    case "scan_in":
    case "scan_out":
      return "scanning";
    case "break_start":
      return "paused";
    case "error":
    case "anomaly":
    case "interrupted":
      return "error";
    default:
      return "idle";
  }
}

interface PyramidViewProps {
  topology: Topology;
  /** Снимки станков для статусов/операторов; без них — скелет схемы. */
  stationById?: Map<string, StationSnapshot>;
  compact?: boolean;
  selectedId?: string | null;
  onNodeClick?: (node: TopologyNode) => void;
}

export function PyramidView({
  topology,
  stationById,
  compact = false,
  selectedId,
  onNodeClick,
}: PyramidViewProps) {
  const scale = compact ? 0.8 : 1;
  const nodeW = NODE_W * scale;
  const nodeH = (stationById ? NODE_H : 64) * scale;
  const levelGap = LEVEL_GAP * scale;

  const layout = useMemo(() => {
    const byLevel = new Map<number, TopologyNode[]>();
    for (const node of topology.nodes) {
      const bucket = byLevel.get(node.level) ?? [];
      bucket.push(node);
      byLevel.set(node.level, bucket);
    }
    const maxPerLevel = Math.max(1, ...[...byLevel.values()].map((v) => v.length));
    const width = Math.max(maxPerLevel * (nodeW + 26) + PAD * 2, compact ? 460 : 660);
    const height = (topology.max_level + 1) * (nodeH + levelGap) - levelGap + PAD * 2;

    const positions = new Map<string, { x: number; y: number }>();
    const levels: { level: number; y: number; count: number }[] = [];
    for (const [level, nodes] of byLevel) {
      const slot = width / (nodes.length + 1);
      const y = height - PAD - nodeH / 2 - level * (nodeH + levelGap);
      levels.push({ level, y, count: nodes.length });
      nodes.forEach((node, i) => {
        positions.set(node.station_id, { x: slot * (i + 1), y });
      });
    }
    return { width, height, positions, levels };
  }, [topology, nodeW, nodeH, levelGap, compact]);

  if (topology.nodes.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-[12px] px-6 py-12 text-center text-[14px]"
        style={{ background: "#FAFBFC", border: "1px dashed #E4E7EB", color: "#98A2B3" }}
      >
        Пирамида появится, когда в справочнике будут операции с указанными станками
      </div>
    );
  }

  const { width, height, positions, levels } = layout;

  return (
    <div>
      <div className="overflow-x-auto">
        <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ maxWidth: width, display: "block", margin: "0 auto" }}>
          <defs>
            <marker id="pyr-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M2 1L8 5L2 9" fill="none" stroke="#C4CBD4" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </marker>
          </defs>

          {/* Подписи уровней слева (только в полном режиме) */}
          {!compact &&
            levels.map(({ level, y, count }) => (
              <g key={level}>
                <text x={8} y={y - 6} style={{ fontSize: 12, fontWeight: 700, fill: "#667085" }}>
                  Уровень {level + 1}
                </text>
                <text x={8} y={y + 10} style={{ fontSize: 11, fill: "#98A2B3" }}>
                  {count} {plural(count, "станция", "станции", "станций")}
                </text>
              </g>
            ))}

          {/* Рёбра + маркеры деталей */}
          {topology.nodes.map((node) =>
            node.fed_by.map((sourceId) => {
              const from = positions.get(sourceId);
              const to = positions.get(node.station_id);
              if (!from || !to) return null;
              const startY = from.y - nodeH / 2;
              const endY = to.y + nodeH / 2 + 6;
              const midY = (startY + endY) / 2;
              // Маркер детали — на середине ребра.
              const mx = (from.x + to.x) / 2;
              return (
                <g key={`${sourceId}-${node.station_id}`}>
                  <path
                    d={`M ${from.x} ${startY} C ${from.x} ${midY}, ${to.x} ${midY}, ${to.x} ${endY}`}
                    fill="none"
                    stroke="#D8DDE5"
                    strokeWidth={1.5}
                    markerEnd="url(#pyr-arrow)"
                  />
                  {!compact && <PartMarker x={mx} y={midY} color="#C4CBD4" />}
                </g>
              );
            }),
          )}

          {/* Карточки станков */}
          {topology.nodes.map((node) => {
            const pos = positions.get(node.station_id);
            if (!pos) return null;
            const snap = stationById?.get(node.station_id);
            const status = deriveNodeStatus(snap);
            const selected = selectedId === node.station_id;
            return (
              <NodeCard
                key={node.station_id}
                node={node}
                snap={snap}
                status={status}
                x={pos.x}
                y={pos.y}
                w={nodeW}
                h={nodeH}
                rich={!!stationById}
                selected={selected}
                onClick={onNodeClick ? () => onNodeClick(node) : undefined}
              />
            );
          })}
        </svg>
      </div>

      {/* Легенда (полный режим) */}
      {!compact && stationById && (
        <div
          className="mt-4 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 rounded-[12px] px-4 py-3"
          style={{ border: "1px solid var(--fl-line-soft)" }}
        >
          {(Object.keys(STATUS_META) as NodeStatus[]).map((key) => (
            <span key={key} className="flex items-center gap-2 text-[12.5px]" style={{ color: "#667085" }}>
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: STATUS_META[key].dot }} />
              {STATUS_META[key].label}
            </span>
          ))}
        </div>
      )}

      {/* Со склада / выход линии */}
      <div className="mt-3 flex flex-wrap items-center justify-center gap-x-6 gap-y-1 text-[12.5px]" style={{ color: "#98A2B3" }}>
        {topology.base_part_types.length > 0 && (
          <span>
            Со склада: <b style={{ color: "#667085" }}>{topology.base_part_types.join(", ")}</b>
          </span>
        )}
        {topology.final_output_types.length > 0 && (
          <span>
            Выход линии: <b style={{ color: "#16A34A" }}>{topology.final_output_types.join(", ")}</b>
          </span>
        )}
      </div>
    </div>
  );
}

/** Куб-маркер детали на ребре, как в макете. */
function PartMarker({ x, y, color }: { x: number; y: number; color: string }) {
  const s = 7;
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect x={-s} y={-s} width={s * 2} height={s * 2} rx={3} fill="#fff" stroke={color} strokeWidth={1.3} />
      <path d={`M ${-s} ${-s / 3} L 0 ${s / 3} L ${s} ${-s / 3}`} fill="none" stroke={color} strokeWidth={1} />
      <path d={`M 0 ${s / 3} V ${s}`} fill="none" stroke={color} strokeWidth={1} />
    </g>
  );
}

function NodeCard({
  node,
  snap,
  status,
  x,
  y,
  w,
  h,
  rich,
  selected,
  onClick,
}: {
  node: TopologyNode;
  snap: StationSnapshot | undefined;
  status: NodeStatus;
  x: number;
  y: number;
  w: number;
  h: number;
  rich: boolean;
  selected: boolean;
  onClick?: () => void;
}) {
  const left = x - w / 2;
  const top = y - h / 2;
  const operator = snap?.operator?.full_name ?? null;

  if (!rich) {
    // Компактная карточка предпросмотра (настройки): имя + операция.
    return (
      <g onClick={onClick} style={{ cursor: onClick ? "pointer" : "default" }}>
        <rect x={left} y={top} width={w} height={h} rx={12} fill="#fff" stroke={selected ? "#16A34A" : "#E4E7EB"} strokeWidth={selected ? 1.6 : 1} />
        <text x={x} y={y - 7} textAnchor="middle" style={{ fontSize: 13.5, fontWeight: 700, fill: "#101828" }}>
          {node.station_name}
        </text>
        <text x={x} y={y + 12} textAnchor="middle" style={{ fontSize: 11.5, fill: "#98A2B3" }}>
          {node.input_types.join(" + ")} → {node.output_types.join(", ")}
        </text>
      </g>
    );
  }

  // Богатая карточка макета: аватар, имя, станция, статус-точка, готово/план.
  const avatarR = 15;
  const avatarCx = left + 24;
  const avatarCy = top + 26;
  return (
    <g onClick={onClick} style={{ cursor: onClick ? "pointer" : "default" }}>
      <rect
        x={left}
        y={top}
        width={w}
        height={h}
        rx={14}
        fill="#fff"
        stroke={selected ? "#16A34A" : "#E4E7EB"}
        strokeWidth={selected ? 1.8 : 1}
      />
      {/* Аватар */}
      <circle cx={avatarCx} cy={avatarCy} r={avatarR} fill={operator ? "#E7EDF3" : "#F3F4F6"} />
      <text x={avatarCx} y={avatarCy + 4} textAnchor="middle" style={{ fontSize: 11, fontWeight: 700, fill: operator ? "#475467" : "#C4CBD4" }}>
        {operator ? initials(operator) : "—"}
      </text>
      {/* Имя оператора / нет назначения */}
      <text x={avatarCx + avatarR + 9} y={avatarCy - 3} style={{ fontSize: 13, fontWeight: 700, fill: operator ? "#101828" : "#98A2B3" }}>
        {operator ? shortName(operator) : "Не назначен"}
      </text>
      {/* Станция */}
      <text x={avatarCx + avatarR + 9} y={avatarCy + 13} style={{ fontSize: 11.5, fill: "#98A2B3" }}>
        {node.station_name}
      </text>
      {/* Статус-точка в углу */}
      <circle cx={left + w - 14} cy={top + 14} r={4.5} fill={STATUS_META[status].dot} />
      {/* Готово / план — заглушка до плана смены */}
      <g transform={`translate(${left + 12}, ${top + h - 26})`}>
        <svg width="13" height="13" viewBox="0 0 20 20" fill="none" stroke="#98A2B3" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 2.5 3 6v8l7 3.5L17 14V6l-7-3.5Z" />
        </svg>
        <text x={19} y={11} style={{ fontSize: 12, fontWeight: 700, fill: "#C4CBD4" }}>
          — / —
        </text>
      </g>
    </g>
  );
}

function shortName(fullName: string): string {
  const [last, first] = fullName.split(/\s+/);
  return first ? `${last} ${first[0]}.` : last;
}

function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}
