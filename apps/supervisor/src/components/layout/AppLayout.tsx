import { useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { useAuth } from "@/api/AuthContext";

/** Шапка страницы: заголовок слева, окно смены и статус обновления справа. */
export function PageHeader({ title, right }: { title: string; right?: React.ReactNode }) {
  const now = new Date().toLocaleTimeString("ru-RU", { hour12: false });
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <h1 className="text-[32px] font-extrabold" style={{ letterSpacing: "-0.03em" }}>
        {title}
      </h1>
      <div className="flex items-center gap-4">
        {right}
        <div
          className="flex items-center gap-2.5 rounded-[12px] bg-card px-4 py-2.5"
          style={{ border: "1px solid var(--fl-line-soft)" }}
        >
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="var(--fl-brand)" strokeWidth="1.6" strokeLinecap="round">
            <rect x="2.8" y="4" width="14.4" height="13.2" rx="3" />
            <path d="M6.4 2.4v3M13.6 2.4v3M2.8 8.2h14.4" />
          </svg>
          <span className="text-[14.5px] font-semibold">Смена: 08:00 – 20:00</span>
        </div>
        <div className="flex items-center gap-2 text-[12.5px]" style={{ color: "#98A2B3" }}>
          <span>Обновлено: {now}</span>
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: "var(--fl-ok)" }} />
        </div>
      </div>
    </div>
  );
}

export function AppLayout() {
  const { user, loading } = useAuth();
  const [expanded, setExpanded] = useState(true);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-[15px] text-muted-foreground">
        Загрузка…
      </div>
    );
  }

  // Не авторизован — на экран входа.
  if (!user) return <Navigate to="/" replace />;

  return (
    <div className="flex min-h-screen items-stretch bg-background">
      <Sidebar expanded={expanded} onToggle={() => setExpanded((v) => !v)} />
      <main className="min-w-0 flex-1" style={{ padding: "30px 34px 40px" }}>
        <Outlet />
      </main>
    </div>
  );
}
