import { Navigate, Route, Routes } from "react-router-dom";
import { PipecatClientAudio, PipecatClientProvider } from "@pipecat-ai/client-react";
import Landing from "./pages/Landing";
import DashboardRoute from "./pages/DashboardRoute";
import MeetRoute from "./pages/MeetRoute";
import AdminLayout from "./pages/admin/AdminLayout";
import AdminDashboard from "./pages/admin/AdminDashboard";
import AdminVisitors from "./pages/admin/AdminVisitors";
import AdminVisitorDetail from "./pages/admin/AdminVisitorDetail";
import AdminAttempts from "./pages/admin/AdminAttempts";
import DocsHome from "./pages/docs/DocsHome";
import DocsRoute from "./pages/docs/DocsRoute";
import { pipecatClient } from "./lib/pipecatClient";

export default function App() {
  return (
    <PipecatClientProvider client={pipecatClient}>
      {/* Renders the actual <audio> element that plays the bot's TTS speech —
          without this, voice replies are received but never played back. */}
      <PipecatClientAudio />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/demo/dashboard" element={<DashboardRoute />} />
        <Route path="/demo/meet" element={<MeetRoute />} />
        {/* Public, no visitor gate — reachable directly, and crawlable.
            /docs is the Knowledge Base hub; /docs/api/* is the ported API
            reference content (a future /docs/product/* section is where
            Gourab's product docs will land later). */}
        <Route path="/docs" element={<DocsHome />} />
        <Route path="/docs/api" element={<DocsRoute />} />
        <Route path="/docs/api/*" element={<DocsRoute />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<AdminDashboard />} />
          <Route path="visitors" element={<AdminVisitors />} />
          <Route path="visitors/:email" element={<AdminVisitorDetail />} />
          <Route path="attempts" element={<AdminAttempts />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </PipecatClientProvider>
  );
}
