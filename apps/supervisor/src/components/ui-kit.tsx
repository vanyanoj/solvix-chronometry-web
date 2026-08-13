import { cn } from "@/lib/utils";

/**
 * Общие блоки макета FlowLine: KPI-карточки, аватары.
 * Данные, которых нет в системе, отображаются прочерком — карточка на месте,
 * метрика подключится, когда появится в бэке.
 */

// === KPI ===

export interface KpiItem {
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  /** null → показываем прочерк (данных в системе пока нет). */
  value: string | null;
  /** Подпись под значением: тренд, уточнение. Цвет задаётся subColor. */
  sub?: string | null;
  subColor?: string;
}

export function KpiBar({ items }: { items: KpiItem[] }) {
  return (
    <div
      className="mb-6 grid gap-4"
      style={{ gridTemplateColumns: `repeat(${items.length}, 1fr)` }}
    >
      {items.map((item, i) => (
        <div
          key={i}
          className="flex items-start gap-3.5 rounded-[14px] bg-card px-5 py-4"
          style={{ border: "1px solid var(--fl-line-soft)" }}
        >
          <span
            className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px]"
            style={{ background: item.iconBg }}
          >
            {item.icon}
          </span>
          <span className="min-w-0">
            <span className="block text-[13px]" style={{ color: "#667085" }}>
              {item.label}
            </span>
            <span
              className="block text-[24px] font-extrabold leading-tight"
              style={{ letterSpacing: "-0.02em", color: item.value ? undefined : "#C4CBD4" }}
            >
              {item.value ?? "—"}
            </span>
            {item.sub && (
              <span className="block text-[12.5px]" style={{ color: item.subColor ?? "#98A2B3" }}>
                {item.sub}
              </span>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}

// === Иконки KPI (в стиле макета) ===

const S = { width: 19, height: 19, viewBox: "0 0 20 20", fill: "none", strokeWidth: 1.7, strokeLinecap: "round" } as const;

export const KpiIcons = {
  efficiency: (
    <svg {...S} stroke="var(--fl-info)" strokeLinejoin="round">
      <path d="M3 13.5 8 8.5l3 3 6-6.5" />
      <path d="M13 5h4v4" />
    </svg>
  ),
  plan: (
    <svg {...S} stroke="#7C6FDD" strokeLinejoin="round">
      <path d="M10 2.5 3 6v8l7 3.5L17 14V6l-7-3.5Z" />
      <path d="M3 6l7 3.5L17 6M10 9.5v8" />
    </svg>
  ),
  people: (
    <svg {...S} stroke="var(--fl-ok)">
      <circle cx="8" cy="7.2" r="2.8" />
      <path d="M2.8 16.4c0-2.9 2.3-4.8 5.2-4.8s5.2 1.9 5.2 4.8" />
      <path d="M14.2 5.2a2.6 2.6 0 0 1 0 5M15.4 11.9c1.5.5 2.4 1.8 2.4 3.6" />
    </svg>
  ),
  problems: (
    <svg {...S} stroke="var(--fl-warn)" strokeLinejoin="round">
      <path d="M10 3 2.5 16.5h15L10 3Z" />
      <path d="M10 8.5v3.5M10 14.6v.2" />
    </svg>
  ),
  delays: (
    <svg {...S} stroke="var(--fl-info)">
      <circle cx="10" cy="10" r="7.4" />
      <path d="M10 5.8V10l2.8 2" />
    </svg>
  ),
} as const;

// === Аватары ===

const AVATAR_PALETTE = [
  "#E7EDF3", "#EAF7EF", "#FEF3E6", "#EFF5FE", "#F3EFFB", "#FBEAF0",
];
const AVATAR_TEXT = [
  "#475467", "#12833C", "#854F0B", "#185FA5", "#534AB7", "#993556",
];

function hashName(name: string): number {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h;
}

export function initials(fullName: string): string {
  return fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

export function Avatar({
  name,
  size = 32,
  className,
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  const idx = hashName(name) % AVATAR_PALETTE.length;
  return (
    <span
      className={cn("flex shrink-0 items-center justify-center rounded-full font-bold", className)}
      style={{
        width: size,
        height: size,
        background: AVATAR_PALETTE[idx],
        color: AVATAR_TEXT[idx],
        fontSize: size * 0.36,
      }}
      title={name}
    >
      {initials(name)}
    </span>
  );
}

/** Стек аватаров как в макете: три кружка внахлёст + счётчик «+N». */
export function AvatarStack({
  names,
  max = 3,
  size = 30,
}: {
  names: string[];
  max?: number;
  size?: number;
}) {
  const shown = names.slice(0, max);
  const rest = names.length - shown.length;
  if (names.length === 0) {
    return (
      <span className="text-[13.5px]" style={{ color: "#C4CBD4" }}>
        —
      </span>
    );
  }
  return (
    <span className="flex items-center">
      {shown.map((n, i) => (
        <Avatar
          key={i}
          name={n}
          size={size}
          className={i > 0 ? "" : ""}
          // рамка, чтобы кружки читались внахлёст
        />
      )).map((el, i) => (
        <span key={i} style={{ marginLeft: i === 0 ? 0 : -8, zIndex: max - i, position: "relative" }}>
          <span style={{ display: "inline-flex", borderRadius: "50%", boxShadow: "0 0 0 2px #fff" }}>{el}</span>
        </span>
      ))}
      {rest > 0 && (
        <span
          className="flex items-center justify-center rounded-full text-[11.5px] font-bold"
          style={{
            width: size,
            height: size,
            marginLeft: -8,
            background: "#F3F4F6",
            color: "#667085",
            boxShadow: "0 0 0 2px #fff",
            position: "relative",
          }}
        >
          +{rest}
        </span>
      )}
    </span>
  );
}

// === Прогресс-бар «готово / план» ===

export function ProgressBar({
  value,
  color = "var(--fl-ok)",
  height = 6,
}: {
  /** 0..100, null — данных нет. */
  value: number | null;
  color?: string;
  height?: number;
}) {
  return (
    <span
      className="block w-full overflow-hidden rounded-full"
      style={{ height, background: "#EFF1F4" }}
    >
      {value !== null && (
        <span
          className="block h-full rounded-full transition-all"
          style={{ width: `${Math.min(100, Math.max(0, value))}%`, background: color }}
        />
      )}
    </span>
  );
}
