import { NavLink, useNavigate } from "react-router-dom";
import { LogoMark } from "@/components/brand/Logo";
import { useAuth } from "@/api/AuthContext";
import { cn } from "@/lib/utils";

const ICON = { width: 19, height: 19, viewBox: "0 0 20 20", strokeWidth: 1.6 } as const;

const NAV = [
  {
    to: "/app/assignments",
    label: "Назначения",
    icon: (
      <svg {...ICON} fill="none" stroke="currentColor" strokeLinecap="round" className="shrink-0">
        <rect x="2.8" y="4" width="14.4" height="13.2" rx="3" />
        <path d="M6.4 2.4v3M13.6 2.4v3M2.8 8.2h14.4" />
      </svg>
    ),
  },
  {
    to: "/app/overview",
    label: "Обзор",
    icon: (
      <svg {...ICON} fill="currentColor" className="shrink-0">
        <rect x="2.6" y="2.6" width="6.2" height="6.2" rx="1.8" />
        <rect x="11.2" y="2.6" width="6.2" height="6.2" rx="1.8" />
        <rect x="2.6" y="11.2" width="6.2" height="6.2" rx="1.8" />
        <rect x="11.2" y="11.2" width="6.2" height="6.2" rx="1.8" />
      </svg>
    ),
  },
  {
    to: "/app/people",
    label: "Сотрудники",
    icon: (
      <svg {...ICON} fill="none" stroke="currentColor" strokeLinecap="round" className="shrink-0">
        <circle cx="8" cy="7.2" r="2.8" />
        <path d="M2.8 16.4c0-2.9 2.3-4.8 5.2-4.8s5.2 1.9 5.2 4.8" />
        <path d="M14.2 5.2a2.6 2.6 0 0 1 0 5" />
        <path d="M15.4 11.9c1.5.5 2.4 1.8 2.4 3.6" />
      </svg>
    ),
  },
  {
    to: "/app/analytics",
    label: "Аналитика",
    icon: (
      <svg {...ICON} fill="none" stroke="currentColor" strokeLinecap="round" className="shrink-0">
        <rect x="2.6" y="2.8" width="14.8" height="14.4" rx="3.4" />
        <path d="M6.6 13.4V9.6M10 13.4V6.8M13.4 13.4v-2.6" />
      </svg>
    ),
  },
  {
    to: "/app/events",
    label: "События",
    icon: (
      <svg {...ICON} fill="none" stroke="currentColor" strokeLinecap="round" className="shrink-0">
        <path d="M5 8.4a5 5 0 0 1 10 0c0 3.2 1.2 4.4 1.2 4.4H3.8S5 11.6 5 8.4Z" />
        <path d="M8.4 15.6a1.8 1.8 0 0 0 3.2 0" />
      </svg>
    ),
  },
  {
    to: "/app/settings",
    label: "Настройки",
    icon: (
      <svg {...ICON} fill="none" stroke="currentColor" strokeLinecap="round" className="shrink-0">
        <circle cx="10" cy="10" r="2.9" />
        <path d="M10 2.4v2.2M10 15.4v2.2M2.4 10h2.2M15.4 10h2.2M4.6 4.6l1.6 1.6M13.8 13.8l1.6 1.6M15.4 4.6l-1.6 1.6M6.2 13.8l-1.6 1.6" />
      </svg>
    ),
  },
] as const;

/** Инициалы для аватара: «Алексей Иванов» → «АИ». */
function initials(fullName: string): string {
  return fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

interface SidebarProps {
  expanded: boolean;
  onToggle: () => void;
  /** Счётчик непросмотренных инцидентов на пункте «События». */
  eventsBadge?: number;
}

export function Sidebar({ expanded, onToggle, eventsBadge }: SidebarProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/", { replace: true });
  };

  return (
    <aside
      className="sticky top-0 flex h-screen shrink-0 flex-col justify-between bg-card transition-[width] duration-200"
      style={{
        width: expanded ? 232 : 74,
        borderRight: "1px solid var(--fl-line-soft)",
        padding: "26px 14px 18px",
      }}
    >
      <div className="flex min-w-0 flex-col gap-[26px]">
        {/* Логотип */}
        <div className="flex items-center gap-[11px] px-2">
          <LogoMark size={34} />
          {expanded && (
            <div className="flex min-w-0 flex-col gap-0.5">
              <div
                className="whitespace-nowrap font-extrabold leading-none text-ink"
                style={{ fontSize: 19, letterSpacing: "-0.025em" }}
              >
                Solvix
              </div>
              <div
                className="whitespace-nowrap font-semibold uppercase"
                style={{ fontSize: 9.5, letterSpacing: "0.2em", color: "#7C8AA5" }}
              >
                Chronometry
              </div>
            </div>
          )}
        </div>

        {/* Навигация */}
        <nav className="flex flex-col gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              title={item.label}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-[13px] whitespace-nowrap rounded-[11px] px-3 py-[11px] text-[15px] font-semibold transition-colors",
                  isActive
                    ? "bg-brand-soft text-brand"
                    : "text-[#475467] hover:bg-[#F6F7F9]",
                )
              }
            >
              {item.icon}
              {expanded && (
                <>
                  <span className="flex-1">{item.label}</span>
                  {item.label === "События" && !!eventsBadge && (
                    <span
                      className="flex items-center justify-center rounded-full text-white"
                      style={{
                        background: "#EF4444",
                        fontSize: 11.5,
                        fontWeight: 700,
                        minWidth: 21,
                        height: 21,
                        padding: "0 6px",
                      }}
                    >
                      {eventsBadge}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </div>

      {/* Низ: пользователь + сворачивание */}
      <div className="flex flex-col gap-3.5">
        <div style={{ height: 1, background: "var(--fl-line-soft)" }} />
        <div className="flex min-w-0 items-center gap-[11px] px-1.5 py-0.5">
          <div
            className="flex shrink-0 items-center justify-center rounded-full"
            style={{ width: 34, height: 34, background: "#E7EDF3", color: "#475467", fontSize: 12.5, fontWeight: 700 }}
          >
            {user ? initials(user.full_name) : "—"}
          </div>
          {expanded && (
            <>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[14px] font-bold">{user?.full_name ?? "—"}</div>
                <div className="whitespace-nowrap text-[12.5px]" style={{ color: "#98A2B3" }}>
                  Старший смены
                </div>
              </div>
              <button
                onClick={handleLogout}
                title="Выйти"
                className="shrink-0 rounded-md p-1 transition-colors hover:bg-[#F6F7F9]"
              >
                <svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="#98A2B3" strokeWidth="1.6" strokeLinecap="round">
                  <path d="M7 15H4a1.5 1.5 0 0 1-1.5-1.5v-9A1.5 1.5 0 0 1 4 3h3" />
                  <path d="M11.5 12 15 9l-3.5-3M15 9H7" />
                </svg>
              </button>
            </>
          )}
        </div>

        <button
          onClick={onToggle}
          className="flex items-center gap-3 whitespace-nowrap rounded-[10px] px-3 py-2.5 text-[14px] transition-colors hover:bg-[#F6F7F9]"
          style={{ color: "#667085" }}
        >
          <svg
            width="17"
            height="17"
            viewBox="0 0 18 18"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            className="shrink-0 transition-transform"
            style={{ transform: expanded ? "none" : "rotate(180deg)" }}
          >
            <path d="M15 9H3" />
            <path d="M7 5 3 9l4 4" />
          </svg>
          {expanded && <span>Свернуть меню</span>}
        </button>
      </div>
    </aside>
  );
}
