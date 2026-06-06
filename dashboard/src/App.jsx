import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./contexts/AuthContext.jsx";
import Layout from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import Signup from "./pages/Signup.jsx";
import Landing from "./pages/Landing.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Campaigns from "./pages/Campaigns.jsx";
import CampaignDetail from "./pages/CampaignDetail.jsx";
import Contacts from "./pages/Contacts.jsx";
import Inbox from "./pages/Inbox.jsx";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center muted">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/landing" element={<Landing />} />
      <Route
        path="/"
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="campaigns" element={<Campaigns />} />
        <Route path="campaigns/:id" element={<CampaignDetail />} />
        <Route path="campaigns/:id/contacts" element={<Contacts />} />
        <Route path="campaigns/:id/inbox" element={<Inbox />} />
      </Route>
    </Routes>
  );
}
