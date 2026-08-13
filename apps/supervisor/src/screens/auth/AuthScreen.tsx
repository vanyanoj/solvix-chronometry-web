import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Logo } from "@/components/brand/Logo";
import { useAuth } from "@/api/AuthContext";
import { useNfcAuth } from "./useNfcAuth";

function HelpIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 20 20" fill="none" stroke="#98A2B3" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="10" cy="10" r="7.6" />
      <path d="M8.2 8a1.9 1.9 0 1 1 2.5 1.8c-.5.2-.7.6-.7 1.1v.3" />
      <circle cx="10" cy="13.8" r=".8" fill="#98A2B3" stroke="none" />
    </svg>
  );
}

function KeyIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="#98A2B3" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="7" cy="10" r="3.4" />
      <path d="M10.4 10H17M14.6 10v2.6M16.6 10v2" />
    </svg>
  );
}

function StatusIcon({ color }: { color: string }) {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round">
      <path d="M6.6 13.4a4.8 4.8 0 0 1 0-6.8" />
      <path d="M13.4 6.6a4.8 4.8 0 0 1 0 6.8" />
      <circle cx="10" cy="10" r="1.6" fill={color} stroke="none" />
    </svg>
  );
}

export function AuthScreen() {
  const navigate = useNavigate();
  const { user, loading } = useAuth();
  const { view, busy, simulateBadge, submitCode } = useNfcAuth();

  const [codeMode, setCodeMode] = useState(false);
  const [code, setCode] = useState("");

  // Успешный вход — уводим в рабочее пространство.
  useEffect(() => {
    if (user) navigate("/app/assignments", { replace: true });
  }, [user, navigate]);

  if (loading) return null;
  if (user) return <Navigate to="/app/assignments" replace />;

  return (
    <div className="flex min-h-screen flex-col bg-background" style={{ padding: "34px 44px 44px" }}>
      <div className="flex justify-end">
        <div className="flex cursor-pointer items-center gap-2.5 text-[15px]" style={{ color: "#667085" }}>
          <HelpIcon />
          Помощь
        </div>
      </div>

      <div className="flex flex-1 flex-col items-center gap-[34px] pt-2.5">
        <Logo markSize={42} wordmarkSize={30} />

        <div className="flex flex-col items-center gap-3 text-center">
          <div className="font-extrabold" style={{ fontSize: 38, letterSpacing: "-0.03em", lineHeight: 1.15 }}>
            Авторизация старшего по смене
          </div>
          <div className="text-[17px]" style={{ color: "#667085" }}>
            Приложите бейдж к считывателю для входа в систему
          </div>
        </div>

        <div
          className="flex w-[660px] max-w-full flex-col items-center gap-[34px]"
          style={{
            background: "#FBFCFC",
            border: "1px solid #EEF0F3",
            borderRadius: 24,
            padding: "44px 60px 40px",
          }}
        >
          {/* Зона считывания. Клик = симуляция поднесения бейджа. */}
          <div
            onClick={busy ? undefined : simulateBadge}
            className="relative flex items-center justify-center"
            style={{ width: 330, height: 330, cursor: busy ? "default" : "pointer" }}
          >
            <div className="absolute" style={{ width: 250, height: 250, borderRadius: 125, background: "#EAF7EF" }} />
            <div className="absolute" style={{ width: 330, height: 330, borderRadius: 165, border: "1px solid #E7EAEE" }} />
            {!busy && (
              <div
                className="absolute animate-fl-ring"
                style={{ width: 290, height: 290, borderRadius: 145, border: "1px solid #16A34A" }}
              />
            )}
            <svg
              width="62"
              height="42"
              viewBox="0 0 62 42"
              fill="none"
              stroke="#16A34A"
              strokeWidth="7"
              strokeLinecap="round"
              className="absolute"
              style={{ top: 6 }}
            >
              <path d="M6 20a34 34 0 0 1 50 0" />
              <path d="M18 31a18 18 0 0 1 26 0" />
              <circle cx="31" cy="39" r="1" strokeWidth="8" />
            </svg>

            <div
              className="relative flex flex-col items-center"
              style={{
                width: 152,
                height: 214,
                borderRadius: 16,
                background: "#ffffff",
                boxShadow: "0 12px 30px rgba(16,24,40,0.09)",
                paddingTop: 22,
                gap: 20,
                marginTop: 34,
              }}
            >
              <div
                className="absolute"
                style={{ top: -12, width: 22, height: 22, borderRadius: 6, border: "3px solid #E4E7EB", background: "#F6F7F9" }}
              />
              <div style={{ width: 30, height: 7, borderRadius: 4, background: "#E4E7EB" }} />
              <div className="flex flex-col items-center" style={{ gap: 2 }}>
                <div style={{ width: 38, height: 38, borderRadius: 19, border: "2.5px solid #C4CBD4" }} />
                <div
                  style={{ width: 60, height: 30, borderRadius: "30px 30px 0 0", border: "2.5px solid #C4CBD4", borderBottom: "none" }}
                />
              </div>
              <div className="flex flex-col items-center" style={{ gap: 8, paddingTop: 6 }}>
                <div style={{ width: 84, height: 7, borderRadius: 4, background: "#E4E7EB" }} />
                <div style={{ width: 56, height: 7, borderRadius: 4, background: "#EDEFF2" }} />
              </div>
            </div>
          </div>

          {/* Статус считывателя */}
          <div
            className="flex w-full items-center gap-4"
            style={{ background: "#ffffff", border: "1px solid #EDEFF2", borderRadius: 14, padding: "18px 22px" }}
          >
            <div
              className="flex shrink-0 items-center justify-center transition-colors"
              style={{ width: 42, height: 42, borderRadius: 21, background: view.iconBg }}
            >
              <StatusIcon color={view.color} />
            </div>
            <div>
              <div className="text-[16px] font-bold" style={{ letterSpacing: "-0.01em" }}>
                {view.title}
              </div>
              <div className="mt-[3px] text-[14px]" style={{ color: "#667085" }}>
                {view.hint}
              </div>
            </div>
          </div>

          {/* Запасной путь — ввод кода вручную */}
          {codeMode && (
            <div className="w-full animate-fl-fade">
              <div className="mb-2 text-[13.5px] font-semibold" style={{ color: "#667085" }}>
                Код доступа
              </div>
              <div className="flex gap-2.5">
                <input
                  autoFocus
                  type="password"
                  value={code}
                  disabled={busy}
                  onChange={(e) => setCode(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void submitCode(code);
                  }}
                  placeholder="Введите код"
                  className="h-11 flex-1 rounded-[10px] border px-3.5 text-[15px] outline-none transition-colors focus:border-brand disabled:opacity-60"
                  style={{ borderColor: "#E4E7EB", background: "#ffffff" }}
                />
                <button
                  onClick={() => void submitCode(code)}
                  disabled={busy || !code.trim()}
                  className="h-11 rounded-[10px] bg-primary px-5 text-[15px] font-semibold text-primary-foreground transition-colors hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-45"
                >
                  Войти
                </button>
              </div>
            </div>
          )}
        </div>

        <button
          onClick={() => setCodeMode((v) => !v)}
          className="flex cursor-pointer items-center gap-2.5 text-[15px] transition-colors hover:text-foreground"
          style={{ color: "#667085", background: "none", border: "none" }}
        >
          <KeyIcon />
          {codeMode ? "Войти по бейджу" : "Войти по коду"}
        </button>
      </div>
    </div>
  );
}
