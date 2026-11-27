import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { Navbar } from './components/layout/Navbar';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { PollsCatalogPage } from './pages/PollsCatalogPage';
import { PollCreatePage } from './pages/PollCreatePage';
import { PollVotePage } from './pages/PollVotePage';
import { PollResultsPage } from './pages/PollResultsPage';
import { ProfilePage } from './pages/ProfilePage';
import { AdminPanelPage } from './pages/AdminPanelPage';
import { ModerationPage } from './pages/ModerationPage';
import { requireAuth } from './routes/PrivateRoute';

const PollCreatePageProtected = requireAuth(PollCreatePage);
const ProfilePageProtected = requireAuth(ProfilePage);
const AdminPanelPageProtected = requireAuth(AdminPanelPage);
const ModerationPageProtected = requireAuth(ModerationPage);

const AppRouter = () => {
  const { isLoading } = useAuth();

  if (isLoading) {
    return null;
  }

  return (
    <BrowserRouter>
      <Navbar />
      <Routes>
        <Route path="/" element={<PollsCatalogPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/polls/create" element={<PollCreatePageProtected />} />
        <Route path="/polls/:slug" element={<PollVotePage />} />
        <Route path="/polls/:slug/results" element={<PollResultsPage />} />
        <Route path="/profile" element={<ProfilePageProtected />} />
        <Route path="/admin" element={<AdminPanelPageProtected />} />
        <Route path="/moderation" element={<ModerationPageProtected />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default function App() {
  return (
    <AuthProvider>
      <AppRouter />
    </AuthProvider>
  );
}
