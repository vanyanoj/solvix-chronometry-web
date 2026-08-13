import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/api/client";
import type { IncidentItem } from "@/api/types";

/**
 * «Аналитика» — вёрстка по прототипу (блок isAnalytics).
 *
 * Раздел почти целиком про метрики, которых в системе пока нет: эффективность,
 * выпуск, план. Поэтому графики показаны структурно с пустым состоянием и
 * честной подписью. Единственная живая панель — распределение инцидентов по
 * типам (данные watchdog есть уже сейчас).
 */

const PERIODS = ["Смена", "День", "Неделя", "Месяц"] as const;

export function AnalyticsScreen() {
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("Смена");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setIncidents(await api.dashboard.incidents({ limit: 200 }));
      setNow(new Date());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить аналитику");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  // Живое: распределение инцидентов по видам аномалий.
  const breakdown = useMemo(() => {
    const map: Record<string, number> = {};
    for (const inc of incidents) {
      const key = inc.event_type === "error" ? "error" : (typeof inc.details?.kind === "string" ? (inc.details.kind as string) : "anomaly");
      map[key] = (map[key] ?? 0) + 1;
    }
    const labels: Record<string, { label: string; color: string }> = {
      norm_exceeded: { label: "Превышение норматива", color: "#F79009" },
      pause_exceeded: { label: "Затянувшаяся пауза", color: "#F79009" },
      station_idle: { label: "Простой станции", color: "#C0453C" },
      transit_stuck: { label: "Застрявшая деталь", color: "#C0453C" },
      error: { label: "Ошибки терминала", color: "#C0453C" },
      anomaly: { label: "Прочие аномалии", color: "#98A2B3" },
    };
    const total = incidents.length || 1;
    return Object.entries(map)
      .map(([k, count]) => ({ key: k, ...(labels[k] ?? { label: k, color: "#98A2B3" }), count, pct: Math.round((count / total) * 100) }))
      .sort((a, b) => b.count - a.count);
  }, [incidents]);

  // Живое: проблемы по часам смены (08:00–20:00).
  const byHour = useMemo(() => {
    const hours = Array.from({ length: 13 }, (_, i) => 8 + i); // 8..20
    const counts = new Map(hours.map((h) => [h, 0]));
    for (const inc of incidents) {
      const h = new Date(inc.timestamp).getHours();
      if (counts.has(h)) counts.set(h, (counts.get(h) ?? 0) + 1);
    }
    const max = Math.max(1, ...counts.values());
    return hours.map((h) => ({ hour: h, count: counts.get(h) ?? 0, ratio: (counts.get(h) ?? 0) / max }));
  }, [incidents]);

  // Живое: топ станций по числу проблем.
  const topStations = useMemo(() => {
    const map = new Map<string, number>();
    for (const inc of incidents) map.set(inc.station_name, (map.get(inc.station_name) ?? 0) + 1);
    const max = Math.max(1, ...map.values());
    return [...map.entries()]
      .map(([name, count]) => ({ name, count, ratio: count / max }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6);
  }, [incidents]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      {/* Шапка */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24 }}>
        <div style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-0.025em" }}>Аналитика</div>
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

      {/* Плашка: что живое, что ждёт план */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, background: "#EFF5FE", border: "1px solid #D5E6FB", borderRadius: 12, padding: "13px 16px" }}>
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="#3B82F6" strokeWidth="1.7" strokeLinecap="round"><circle cx="10" cy="10" r="7.4" /><path d="M10 9.2v4.2" /><path d="M10 6.6h.01" /></svg>
        <div style={{ fontSize: 13.5, color: "#1E4E82" }}>
          Аналитика по проблемам — на живых данных watchdog. Метрики выработки (эффективность, выпуск, план) появятся, когда в системе будет план смены.
        </div>
      </div>

      {/* KPI */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 16 }}>
        <AnalyticsKpi icon="eff" iconBg="#EFF5FE" iconFg="#3B82F6" label="Ср. эффективность" value="—" note="появится с планом" />
        <AnalyticsKpi icon="box" iconBg="#F3EFFB" iconFg="#7C6FDD" label="Выпуск за смену" value="—" unit="шт" note="появится с планом" />
        <AnalyticsKpi icon="perf" iconBg="#EAF7EF" iconFg="#16A34A" label="Производительность" value="—" note="появится с планом" />
        <AnalyticsKpi icon="warn" iconBg="#FEF3E6" iconFg="#F79009" label="Проблем за смену" value={String(incidents.length)} note="по данным watchdog" live />
        <AnalyticsKpi icon="clock" iconBg="#EFF5FE" iconFg="#3B82F6" label="Ср. простой" value="—" note="появится с учётом времени" />
      </div>

      {error && (
        <div style={{ background: "#FDEEEC", border: "1px solid #F3C9C5", borderRadius: 14, padding: "14px 18px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 14.5, color: "#C0453C" }}>{error}</span>
          <button onClick={() => void load()} style={{ background: "#fff", border: "1px solid #F3C9C5", color: "#C0453C", borderRadius: 9, padding: "7px 13px", fontSize: 13.5, fontWeight: 600 }}>Повторить</button>
        </div>
      )}

      {/* Фильтры периода */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, padding: "11px 15px", fontSize: 14, color: "#475467" }}>
          <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="#475467" strokeWidth="1.6" strokeLinecap="round"><rect x="2.8" y="4" width="14.4" height="13.2" rx="3" /><path d="M6.4 2.4v3M13.6 2.4v3M2.8 8.2h14.4" /></svg>
          Сегодня, {now.toLocaleDateString("ru-RU")}
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4, background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 11, padding: 4 }}>
          {PERIODS.map((p) => (
            <div key={p} onClick={() => setPeriod(p)} style={{ fontSize: 14, fontWeight: 600, padding: "8px 18px", borderRadius: 8, cursor: "pointer", background: p === period ? "#EAF7EF" : "transparent", color: p === period ? "#16A34A" : "#475467" }}>{p}</div>
          ))}
        </div>
      </div>

      {/* Живые графики: проблемы по часам + топ станций */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
        {/* Проблемы по часам */}
        <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 16, padding: "20px 22px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontSize: 15.5, fontWeight: 700 }}>Проблемы по часам</div>
            <div style={{ fontSize: 13, color: "#667085" }}>смена 08:00–20:00</div>
          </div>
          {loading ? (
            <div className="animate-fl-pulse" style={{ height: 170, borderRadius: 10, background: "#F3F4F6", marginTop: 16 }} />
          ) : incidents.length === 0 ? (
            <EmptyChart text="За смену проблем не было" />
          ) : (
            <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 170, marginTop: 16 }}>
              {byHour.map((b) => (
                <div key={b.hour} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                  <div style={{ fontSize: 11, color: b.count > 0 ? "#667085" : "#C4CBD4", fontWeight: 600 }}>{b.count || ""}</div>
                  <div title={`${b.hour}:00 — ${b.count}`} style={{ width: "100%", height: Math.max(3, b.ratio * 128), borderRadius: "4px 4px 0 0", background: b.count > 0 ? "#F79009" : "#EEF0F3", transition: "height .3s" }} />
                  <div style={{ fontSize: 10, color: "#98A2B3" }}>{b.hour}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Топ проблемных станций */}
        <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 16, padding: "20px 22px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontSize: 15.5, fontWeight: 700 }}>Проблемные станции</div>
            <div style={{ fontSize: 13, color: "#667085" }}>топ по числу проблем</div>
          </div>
          {loading ? (
            <div className="animate-fl-pulse" style={{ height: 170, borderRadius: 10, background: "#F3F4F6", marginTop: 16 }} />
          ) : topStations.length === 0 ? (
            <EmptyChart text="Проблемных станций нет" />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 18 }}>
              {topStations.map((s) => (
                <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 130, fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", flex: "0 0 auto" }} title={s.name}>{s.name}</div>
                  <div style={{ flex: 1, height: 20, borderRadius: 5, background: "#F0F1F4", overflow: "hidden" }}>
                    <div style={{ width: `${Math.max(6, s.ratio * 100)}%`, height: 20, borderRadius: 5, background: "#E0857A", transition: "width .3s" }} />
                  </div>
                  <div style={{ width: 24, textAlign: "right", fontSize: 13.5, fontWeight: 700, flex: "0 0 auto" }}>{s.count}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Живая панель: распределение проблем */}
      <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 16, padding: "20px 22px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div style={{ fontSize: 15.5, fontWeight: 700 }}>Распределение проблем по типам</div>
          <div style={{ fontSize: 13, color: "#667085" }}>Всего: <span style={{ color: "#101828", fontWeight: 700 }}>{incidents.length}</span></div>
        </div>

        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {[0, 1, 2].map((i) => <div key={i} className="animate-fl-pulse" style={{ height: 40, borderRadius: 8, background: "#F3F4F6" }} />)}
          </div>
        ) : breakdown.length === 0 ? (
          <div style={{ padding: "40px 0", textAlign: "center" }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: "#16A34A" }}>Проблем за смену нет</div>
            <div style={{ fontSize: 13.5, color: "#98A2B3", marginTop: 5 }}>Watchdog не зафиксировал аномалий и ошибок.</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {breakdown.map((b) => (
              <div key={b.key}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 13.5, color: "#475467" }}>
                    <div style={{ width: 9, height: 9, borderRadius: 3, background: b.color }} />
                    {b.label}
                  </div>
                  <div style={{ fontSize: 13.5, color: "#667085" }}>
                    <span style={{ fontWeight: 700, color: "#101828" }}>{b.count}</span> · {b.pct}%
                  </div>
                </div>
                <div style={{ height: 8, borderRadius: 4, background: "#F0F1F4", overflow: "hidden" }}>
                  <div style={{ width: `${b.pct}%`, height: 8, borderRadius: 4, background: b.color }} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyChart({ text }: { text: string }) {
  return (
    <div style={{ height: 170, marginTop: 16, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 10, background: "#FAFBFC", border: "1px dashed #E4E7EB" }}>
      <div style={{ fontSize: 13.5, color: "#16A34A", fontWeight: 600 }}>{text}</div>
    </div>
  );
}

function AnalyticsKpi({ icon, iconBg, iconFg, label, value, unit, note, live }: {
  icon: string; iconBg: string; iconFg: string; label: string; value: string; unit?: string; note: string; live?: boolean;
}) {
  const dim = value === "—";
  const p = { width: 19, height: 19, viewBox: "0 0 20 20", fill: "none", stroke: iconFg, strokeWidth: 1.7, strokeLinecap: "round" as const };
  const icons: Record<string, React.ReactNode> = {
    eff: <svg {...p} strokeLinejoin="round"><path d="M3 13.6 7.6 8.8l3 2.7L17 5" /><path d="M12.6 5H17v4.4" /></svg>,
    box: <svg {...p} strokeLinejoin="round"><path d="M10 2.6 16.6 6v8L10 17.4 3.4 14V6Z" /><path d="M3.4 6 10 9.6 16.6 6M10 9.6v7.8" /></svg>,
    perf: <svg {...p}><path d="M3.4 14.6a7.6 7.6 0 1 1 13.2 0" /><path d="M10 14.2 13.4 8" /></svg>,
    warn: <svg {...p} strokeLinejoin="round"><path d="M10 3.2 18 16.6H2Z" /><path d="M10 8.2v3.4" /><path d="M10 14.2h.01" /></svg>,
    clock: <svg {...p}><circle cx="10" cy="10" r="7.4" /><path d="M10 5.6V10l3 2" /></svg>,
  };
  return (
    <div style={{ background: "#ffffff", border: "1px solid #EAECF0", borderRadius: 14, padding: "18px 20px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ width: 40, height: 40, borderRadius: 11, background: iconBg, display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>{icons[icon]}</div>
        <div style={{ fontSize: 13.5, color: "#667085" }}>{label}</div>
      </div>
      <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: "-0.02em", color: dim ? "#C4CBD4" : undefined }}>
        {value}{unit && <span style={{ fontSize: 15, fontWeight: 600, color: dim ? "#C4CBD4" : "#667085" }}> {unit}</span>}
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: live ? "#16A34A" : "#98A2B3" }}>{note}</div>
    </div>
  );
}
