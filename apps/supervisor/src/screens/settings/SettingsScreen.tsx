import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/AppLayout";
import { PyramidView } from "@/components/PyramidView";
import { api, ApiError } from "@/api/client";
import type { Line, Process, StationSnapshot, Topology } from "@/api/types";
import { cn } from "@/lib/utils";

type Toast = { kind: "ok" | "err"; text: string } | null;

/** Пустая форма новой операции. */
const EMPTY_FORM = {
  input_type_1: "",
  input_type_2: "",
  output_type: "",
  station_hint: "",
  nominal_duration_sec: "",
  anomaly_threshold_pct: "30",
};

export function SettingsScreen() {
  const [lines, setLines] = useState<Line[]>([]);
  const [lineId, setLineId] = useState<string | null>(null);
  const [stations, setStations] = useState<StationSnapshot[]>([]);
  const [processes, setProcesses] = useState<Process[]>([]);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast>(null);

  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [submitting, setSubmitting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  /** Правка норматива по месту: id процесса → введённое значение. */
  const [editNorm, setEditNorm] = useState<{ id: string; value: string } | null>(null);
  const [topology, setTopology] = useState<Topology | null>(null);

  const stationName = useMemo(() => {
    const map = new Map(stations.map((s) => [s.id, s.name]));
    return (id: string | null) => (id ? (map.get(id) ?? "(удалён)") : "—");
  }, [stations]);

  // Линии и станки — один раз.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [ls, sts] = await Promise.all([api.lines.list(), api.dashboard.stations()]);
        if (cancelled) return;
        setLines(ls);
        setStations(sts);
        if (ls.length > 0) setLineId(ls[0].id);
        else {
          setLoading(false);
          setLoadError("В системе нет ни одной линии. Добавьте линию сидом или через БД.");
        }
      } catch (e) {
        if (!cancelled) {
          setLoading(false);
          setLoadError(e instanceof ApiError ? e.message : "Не удалось загрузить данные");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const loadProcesses = useCallback(async (line: string) => {
    setLoading(true);
    setLoadError(null);
    try {
      const [procs, topo] = await Promise.all([
        api.processes.list({ line_id: line, limit: 500 }),
        api.processes.topology(line),
      ]);
      setProcesses(procs);
      setTopology(topo);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Не удалось загрузить справочник");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (lineId) void loadProcesses(lineId);
  }, [lineId, loadProcesses]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const canSubmit =
    !!lineId &&
    form.input_type_1.trim() &&
    form.input_type_2.trim() &&
    form.output_type.trim() &&
    form.station_hint &&
    Number(form.nominal_duration_sec) > 0 &&
    !submitting;

  const submit = async () => {
    if (!canSubmit || !lineId) return;
    setSubmitting(true);
    try {
      await api.processes.create({
        line_id: lineId,
        input_type_1: form.input_type_1.trim(),
        input_type_2: form.input_type_2.trim(),
        output_type: form.output_type.trim(),
        station_hint: form.station_hint,
        nominal_duration_sec: Number(form.nominal_duration_sec),
        anomaly_threshold_pct: Number(form.anomaly_threshold_pct) || 30,
      });
      setToast({ kind: "ok", text: "Операция добавлена в справочник" });
      setForm({ ...EMPTY_FORM });
      await loadProcesses(lineId);
    } catch (e) {
      setToast({ kind: "err", text: e instanceof ApiError ? e.message : "Не удалось добавить" });
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.processes.remove(id);
      setToast({ kind: "ok", text: "Операция удалена" });
      setConfirmDelete(null);
      if (lineId) await loadProcesses(lineId);
    } catch (e) {
      setToast({ kind: "err", text: e instanceof ApiError ? e.message : "Не удалось удалить" });
    }
  };

  const saveNorm = async () => {
    if (!editNorm) return;
    const value = Number(editNorm.value);
    if (!(value > 0)) {
      setEditNorm(null);
      return;
    }
    try {
      await api.processes.update(editNorm.id, { nominal_duration_sec: value });
      setToast({ kind: "ok", text: "Норматив обновлён" });
      if (lineId) await loadProcesses(lineId);
    } catch (e) {
      setToast({ kind: "err", text: e instanceof ApiError ? e.message : "Не удалось обновить" });
    } finally {
      setEditNorm(null);
    }
  };

  const fmtDuration = (sec: number) => {
    if (sec < 60) return `${sec} сек`;
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return s ? `${m} мин ${s} сек` : `${m} мин`;
  };

  return (
    <>
      <PageHeader title="Настройки" />

      {/* Вкладки раздела — пока активны только Справочники */}
      <div className="mb-6 flex gap-1 border-b" style={{ borderColor: "var(--fl-line-soft)" }}>
        {["Общие", "Справочники", "Оборудование", "Безопасность"].map((tab) => {
          const active = tab === "Справочники";
          return (
            <div
              key={tab}
              className={cn(
                "px-4 pb-3 pt-1 text-[14.5px] font-semibold",
                active
                  ? "border-b-2 border-brand text-brand"
                  : "cursor-default text-[#98A2B3]",
              )}
              style={active ? { marginBottom: -1 } : undefined}
            >
              {tab}
            </div>
          );
        })}
      </div>

      {toast && (
        <div
          className="mb-5 animate-fl-fade rounded-[14px] px-5 py-4 text-[15px]"
          style={{
            background: toast.kind === "ok" ? "var(--fl-ok-soft)" : "var(--fl-danger-soft)",
            border: `1px solid ${toast.kind === "ok" ? "#CDEBD9" : "#F3C9C5"}`,
            color: toast.kind === "ok" ? "#12833C" : "var(--fl-danger)",
          }}
        >
          {toast.text}
        </div>
      )}

      {loadError && (
        <div
          className="mb-5 rounded-[14px] px-5 py-4 text-[15px]"
          style={{
            background: "var(--fl-danger-soft)",
            border: "1px solid #F3C9C5",
            color: "var(--fl-danger)",
          }}
        >
          {loadError}
        </div>
      )}

      <section
        className="rounded-[16px] bg-card p-6"
        style={{ border: "1px solid var(--fl-line-soft)" }}
      >
        <div className="mb-1 flex items-center justify-between gap-4">
          <div>
            <h2 className="text-[18px] font-extrabold" style={{ letterSpacing: "-0.02em" }}>
              Справочник процессов
            </h2>
            <p className="mt-1 text-[13.5px]" style={{ color: "#98A2B3" }}>
              Документация технолога: какая пара деталей собирается в какую, на каком
              станке и за сколько. Пирамида на «Обзоре» строится из этих строк.
            </p>
          </div>

          {lines.length > 1 && (
            <select
              value={lineId ?? ""}
              onChange={(e) => setLineId(e.target.value)}
              className="h-10 rounded-[10px] border bg-white px-3 text-[14px] outline-none focus:border-brand"
              style={{ borderColor: "#E4E7EB" }}
            >
              {lines.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Форма добавления */}
        <div
          className="mb-5 mt-4 rounded-[12px] p-4"
          style={{ background: "#F9FAFB", border: "1px solid #EDEFF2" }}
        >
          <div className="grid items-end gap-3" style={{ gridTemplateColumns: "1fr 1fr 1fr 1.3fr 1fr 1fr auto" }}>
            <Field label="Вход 1">
              <input
                value={form.input_type_1}
                onChange={(e) => setForm({ ...form, input_type_1: e.target.value })}
                placeholder="A"
                className="h-10 w-full rounded-[9px] border bg-white px-3 text-[14px] outline-none focus:border-brand"
                style={{ borderColor: "#E4E7EB" }}
              />
            </Field>
            <Field label="Вход 2">
              <input
                value={form.input_type_2}
                onChange={(e) => setForm({ ...form, input_type_2: e.target.value })}
                placeholder="B"
                className="h-10 w-full rounded-[9px] border bg-white px-3 text-[14px] outline-none focus:border-brand"
                style={{ borderColor: "#E4E7EB" }}
              />
            </Field>
            <Field label="Выход">
              <input
                value={form.output_type}
                onChange={(e) => setForm({ ...form, output_type: e.target.value })}
                placeholder="C"
                className="h-10 w-full rounded-[9px] border bg-white px-3 text-[14px] outline-none focus:border-brand"
                style={{ borderColor: "#E4E7EB" }}
              />
            </Field>
            <Field label="Станок">
              <select
                value={form.station_hint}
                onChange={(e) => setForm({ ...form, station_hint: e.target.value })}
                className="h-10 w-full rounded-[9px] border bg-white px-3 text-[14px] outline-none focus:border-brand"
                style={{ borderColor: "#E4E7EB" }}
              >
                <option value="">Выберите…</option>
                {stations.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Норматив, сек">
              <input
                type="number"
                min={1}
                value={form.nominal_duration_sec}
                onChange={(e) => setForm({ ...form, nominal_duration_sec: e.target.value })}
                placeholder="120"
                className="h-10 w-full rounded-[9px] border bg-white px-3 text-[14px] outline-none focus:border-brand"
                style={{ borderColor: "#E4E7EB" }}
              />
            </Field>
            <Field label="Порог, %">
              <input
                type="number"
                min={0}
                max={500}
                value={form.anomaly_threshold_pct}
                onChange={(e) => setForm({ ...form, anomaly_threshold_pct: e.target.value })}
                className="h-10 w-full rounded-[9px] border bg-white px-3 text-[14px] outline-none focus:border-brand"
                style={{ borderColor: "#E4E7EB" }}
              />
            </Field>
            <button
              onClick={() => void submit()}
              disabled={!canSubmit}
              className="h-10 whitespace-nowrap rounded-[9px] bg-primary px-4 text-[14px] font-semibold text-primary-foreground transition-colors hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submitting ? "Добавляем…" : "Добавить"}
            </button>
          </div>
          <p className="mt-2.5 text-[12.5px]" style={{ color: "#98A2B3" }}>
            Порог — на сколько процентов операция может превысить норматив, прежде чем
            система отметит аномалию.
          </p>
        </div>

        {/* Таблица */}
        {loading ? (
          <div className="flex flex-col gap-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="animate-fl-pulse rounded-[10px]" style={{ height: 52, background: "#F3F4F6" }} />
            ))}
          </div>
        ) : processes.length === 0 ? (
          <div
            className="rounded-[12px] px-5 py-10 text-center"
            style={{ background: "#FAFBFC", border: "1px dashed #E4E7EB" }}
          >
            <div className="text-[15px] font-bold">Справочник пуст</div>
            <p className="mx-auto mt-1 max-w-md text-[13.5px]" style={{ color: "#98A2B3" }}>
              Добавьте первую операцию формой выше — например «A + B → C, Станок 1,
              120 сек». Из этих строк соберётся пирамида линии.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[14px]">
              <thead>
                <tr className="text-left text-[12.5px]" style={{ color: "#98A2B3" }}>
                  <th className="pb-2.5 pr-4 font-semibold">Операция</th>
                  <th className="pb-2.5 pr-4 font-semibold">Станок</th>
                  <th className="pb-2.5 pr-4 font-semibold">Норматив</th>
                  <th className="pb-2.5 pr-4 font-semibold">Порог</th>
                  <th className="pb-2.5 pr-4 font-semibold">Действует с</th>
                  <th className="pb-2.5 font-semibold" />
                </tr>
              </thead>
              <tbody>
                {processes.map((p) => (
                  <tr key={p.id} className="border-t" style={{ borderColor: "var(--fl-line-soft)" }}>
                    <td className="py-3 pr-4">
                      <span className="font-bold">{p.input_type_1}</span>
                      <span style={{ color: "#98A2B3" }}> + </span>
                      <span className="font-bold">{p.input_type_2}</span>
                      <span style={{ color: "#16A34A" }}> → </span>
                      <span className="font-bold">{p.output_type}</span>
                    </td>
                    <td className="py-3 pr-4">{stationName(p.station_hint)}</td>
                    <td className="py-3 pr-4">
                      {editNorm?.id === p.id ? (
                        <input
                          autoFocus
                          type="number"
                          min={1}
                          value={editNorm.value}
                          onChange={(e) => setEditNorm({ id: p.id, value: e.target.value })}
                          onBlur={() => void saveNorm()}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") void saveNorm();
                            if (e.key === "Escape") setEditNorm(null);
                          }}
                          className="h-8 w-24 rounded-[7px] border bg-white px-2 text-[13.5px] outline-none focus:border-brand"
                          style={{ borderColor: "var(--fl-brand)" }}
                        />
                      ) : (
                        <button
                          onClick={() =>
                            setEditNorm({ id: p.id, value: String(p.nominal_duration_sec) })
                          }
                          title="Изменить норматив"
                          className="rounded-[6px] px-1.5 py-0.5 transition-colors hover:bg-[#F3F4F6]"
                        >
                          {fmtDuration(p.nominal_duration_sec)}
                        </button>
                      )}
                    </td>
                    <td className="py-3 pr-4" style={{ color: "#667085" }}>
                      +{p.anomaly_threshold_pct}%
                    </td>
                    <td className="py-3 pr-4 text-[13px]" style={{ color: "#98A2B3" }}>
                      {new Date(p.valid_from).toLocaleDateString("ru-RU")}
                    </td>
                    <td className="py-3 text-right">
                      {confirmDelete === p.id ? (
                        <span className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => void remove(p.id)}
                            className="rounded-[7px] px-2.5 py-1 text-[12.5px] font-semibold text-white"
                            style={{ background: "var(--fl-danger)" }}
                          >
                            Удалить
                          </button>
                          <button
                            onClick={() => setConfirmDelete(null)}
                            className="rounded-[7px] border px-2.5 py-1 text-[12.5px] font-semibold"
                            style={{ borderColor: "#E4E7EB", color: "#667085" }}
                          >
                            Отмена
                          </button>
                        </span>
                      ) : (
                        <button
                          onClick={() => setConfirmDelete(p.id)}
                          title="Удалить операцию"
                          className="rounded-[7px] p-1.5 transition-colors hover:bg-[#FDEEEC]"
                        >
                          <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="#98A2B3" strokeWidth="1.6" strokeLinecap="round">
                            <path d="M3.5 5.5h13M8 5.5V4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1.5M5.5 5.5 6.3 16a1 1 0 0 0 1 .9h5.4a1 1 0 0 0 1-.9l.8-10.5" />
                          </svg>
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Предпросмотр пирамиды — перестраивается при каждом изменении справочника */}
      {topology && (
        <section
          className="mt-5 rounded-[16px] bg-card p-6"
          style={{ border: "1px solid var(--fl-line-soft)" }}
        >
          <h2 className="text-[18px] font-extrabold" style={{ letterSpacing: "-0.02em" }}>
            Предпросмотр пирамиды
          </h2>
          <p className="mb-4 mt-1 text-[13.5px]" style={{ color: "#98A2B3" }}>
            Собирается автоматически из строк справочника. Так линия будет выглядеть
            на «Обзоре».
          </p>

          {topology.warnings.length > 0 && (
            <div
              className="mb-4 rounded-[12px] px-4 py-3"
              style={{ background: "var(--fl-warn-soft)", border: "1px solid #F5DDB8" }}
            >
              {topology.warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2 py-0.5 text-[13.5px]" style={{ color: "#854F0B" }}>
                  <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="#BA7517" strokeWidth="1.7" strokeLinecap="round" className="mt-0.5 shrink-0">
                    <path d="M10 3 2.5 16.5h15L10 3Z" strokeLinejoin="round" />
                    <path d="M10 8.5v3.5M10 14.6v.2" />
                  </svg>
                  {w}
                </div>
              ))}
            </div>
          )}

          <PyramidView topology={topology} compact />
        </section>
      )}
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12.5px] font-semibold" style={{ color: "#667085" }}>
        {label}
      </span>
      {children}
    </label>
  );
}
