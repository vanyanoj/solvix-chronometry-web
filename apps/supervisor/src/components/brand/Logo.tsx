import { cn } from "@/lib/utils";

interface LogoMarkProps {
  size?: number;
  className?: string;
}

/** Значок Solvix — тёмно-синий квадрат с золотой стрелкой хронометра. */
export function LogoMark({ size = 34, className }: LogoMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      className={cn("shrink-0", className)}
      aria-hidden
    >
      <rect x="1" y="1" width="38" height="38" rx="12" fill="#1E2A44" />
      <circle cx="20" cy="20" r="11.5" stroke="#C9A54E" strokeWidth="1" />
      <g stroke="#ffffff" strokeWidth="1.6" strokeLinecap="round">
        <path d="M20 6.6v3" />
        <path d="M33.4 20h-3" />
        <path d="M20 33.4v-3" />
        <path d="M6.6 20h3" />
      </g>
      <path d="M20 20V13" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" />
      <path d="M20 20l5 3" stroke="#D8B25C" strokeWidth="2" strokeLinecap="round" />
      <circle cx="20" cy="20" r="1.7" fill="#D8B25C" />
    </svg>
  );
}

interface LogoProps {
  markSize?: number;
  wordmarkSize?: number;
  className?: string;
}

/** Логотип целиком: значок + «Solvix / CHRONOMETRY». */
export function Logo({ markSize = 42, wordmarkSize = 30, className }: LogoProps) {
  return (
    <div className={cn("flex items-center gap-3.5", className)}>
      <LogoMark size={markSize} />
      <div className="flex flex-col gap-1">
        <span
          className="font-extrabold leading-none text-ink"
          style={{ fontSize: wordmarkSize, letterSpacing: "-0.03em" }}
        >
          Solvix
        </span>
        <span
          className="font-semibold uppercase"
          style={{
            fontSize: wordmarkSize * 0.4,
            letterSpacing: "0.24em",
            color: "#7C8AA5",
          }}
        >
          Chronometry
        </span>
      </div>
    </div>
  );
}
