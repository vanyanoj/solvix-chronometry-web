import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout, PageHeader } from "@/components/layout/AppLayout";
import { AuthScreen } from "@/screens/auth/AuthScreen";
import { AssignmentsScreen } from "@/screens/assignments/AssignmentsScreen";
import { SettingsScreen } from "@/screens/settings/SettingsScreen";
import { OverviewScreen } from "@/screens/overview/OverviewScreen";
import { LineDetailScreen } from "@/screens/overview/LineDetailScreen";
import { EventsScreen } from "@/screens/events/EventsScreen";
import { PeopleScreen } from "@/screens/people/PeopleScreen";
import { AnalyticsScreen } from "@/screens/analytics/AnalyticsScreen";

/** Временная заглушка для разделов, которые ещё не собраны. */
function Stub({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <div
        className="rounded-[16px] bg-card px-6 py-16 text-center"
        style={{ border: "1px dashed #E4E7EB" }}
      >
        <div className="text-[16px] font-bold">Раздел в разработке</div>
        <p className="mx-auto mt-2 max-w-md text-[14.5px]" style={{ color: "#98A2B3" }}>
          Собираем по порядку. Следующие на очереди — «Обзор» с пирамидой станков
          в реальном времени и «События».
        </p>
      </div>
    </>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AuthScreen />} />
      <Route path="/app" element={<AppLayout />}>
        <Route index element={<Navigate to="/app/assignments" replace />} />
        <Route path="assignments" element={<AssignmentsScreen />} />
        <Route path="overview" element={<OverviewScreen />} />
        <Route path="overview/:lineId" element={<LineDetailScreen />} />
        <Route path="people" element={<PeopleScreen />} />
        <Route path="analytics" element={<AnalyticsScreen />} />
        <Route path="events" element={<EventsScreen />} />
        <Route path="settings" element={<SettingsScreen />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
