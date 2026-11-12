import { Navigate, Route, Routes } from "react-router-dom";
import { Spinner } from "./components/ui";
import { useAuth } from "./hooks/useAuth";
import { AppLayout } from "./layouts/AppLayout";
import { CampaignDetail, Campaigns } from "./pages/Campaigns";
import { Clients } from "./pages/Clients";
import { Costs } from "./pages/Costs";
import { CreatorDetail } from "./pages/CreatorDetail";
import { Creators } from "./pages/Creators";
import { Discover } from "./pages/Discover";
import { Login } from "./pages/Login";
import { Outreach } from "./pages/Outreach";
import { Overview } from "./pages/Overview";
import { Partnerships } from "./pages/Partnerships";
import { Reports } from "./pages/Reports";
import { Settings } from "./pages/Settings";

export function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-8"><Spinner /></div>;
  if (!user) return <Login />;

  if (user.role === "client") {
    // Client portal: only their own campaign shortlists.
    return (
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Campaigns />} />
          <Route path="/campaigns/:id" element={<CampaignDetail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    );
  }
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Overview />} />
        <Route path="/discover" element={<Discover />} />
        <Route path="/creators" element={<Creators />} />
        <Route path="/creators/:id" element={<CreatorDetail />} />
        <Route path="/review" element={<Creators key="review" review />} />
        <Route path="/campaigns" element={<Campaigns />} />
        <Route path="/campaigns/:id" element={<CampaignDetail />} />
        <Route path="/clients" element={<Clients />} />
        <Route path="/outreach" element={<Outreach />} />
        <Route path="/partnerships" element={<Partnerships />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/costs" element={<Costs />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
