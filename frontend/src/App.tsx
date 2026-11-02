import { Link, Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import Dashboard from "./pages/Dashboard";
import ModulePage, { modules } from "./pages/ModulePage";
import Settings from "./pages/Settings";
export default function App() {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Dashboard />} />
          {(Object.keys(modules) as (keyof typeof modules)[]).map((module) => (
            <Route
              key={module}
              path={module}
              element={<ModulePage module={module} />}
            />
          ))}
          <Route path="settings" element={<Settings />} />
          <Route
            path="*"
            element={
              <div className="empty-state">
                <h1>Workspace not found</h1>
                <Link to="/">Return to Dashboard</Link>
              </div>
            }
          />
        </Route>
      </Routes>
    </>
  );
}
