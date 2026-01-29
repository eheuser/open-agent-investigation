import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useParams } from 'react-router-dom';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import InvestigationDetail from './routes/InvestigationDetail';
import Login from './pages/Login';
import Settings from './pages/Settings';
import Playbooks from './pages/Playbooks';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { JobsProvider } from './contexts/JobsContext';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isLoading } = useAuth();

  // Wait for auth check to complete before redirecting
  if (isLoading) {
    return <div>Loading...</div>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

// Create a context for sidebar state
const SidebarContext = React.createContext<{ isOpen: boolean }>({ isOpen: true });
export const useSidebar = () => React.useContext(SidebarContext);

const InvestigationWrapper: React.FC = () => {
  return <InvestigationDetail />;
};

function App() {
  // Default to open on desktop, closed on mobile
  const [sidebarOpen, setSidebarOpen] = React.useState(() => {
    if (typeof window !== 'undefined') {
      return window.innerWidth >= 1024; // lg breakpoint
    }
    return true;
  });

  return (
    <Router>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <JobsProvider>
                  <SidebarContext.Provider value={{ isOpen: sidebarOpen }}>
                    <div className="flex h-screen bg-white dark:bg-gray-900">
                      {/* Left sidebar - collapsible */}
                      <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

                                                                                                                                                  {/* Central content area */}
                      <section className="flex-1 overflow-hidden">
                                                <Routes>
                          <Route path="/" element={<Dashboard />} />
                          <Route
                            path="/investigation/:id"
                            element={<InvestigationWrapper />}
                          />
                          <Route path="/settings" element={<Settings />} />
                          <Route path="/playbooks" element={<Playbooks />} />
                        </Routes>
                      </section>
                    </div>
                  </SidebarContext.Provider>
                </JobsProvider>
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </Router>
  );
}

export default App;