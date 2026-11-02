import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Menu, X, Sprout, ChevronRight } from "lucide-react";
import { navigation } from "../navigation";
export default function Shell() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const title =
    navigation.find(
      (item) =>
        item.path === location.pathname ||
        (item.path !== "/" && location.pathname.startsWith(item.path + "/")),
    )?.title ?? "Workspace";
  return (
    <div className="shell">
      <aside
        className={open ? "sidebar open" : "sidebar"}
        id="primary-navigation"
      >
        <div className="brand">
          <span className="brand-icon">
            <Sprout size={25} />
          </span>
          <div>
            Cultivatinator<small>CULTIVATION MANAGEMENT</small>
          </div>
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Primary navigation">
          {navigation.map(({ path, title, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              onClick={() => setOpen(false)}
            >
              <Icon size={19} aria-hidden="true" />
              <span>{title}</span>
              <ChevronRight className="nav-arrow" size={14} />
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="status-dot" />
          Single-user workspace
          <small>Milestone 2A / Culture Library</small>
        </div>
      </aside>
      {open && (
        <button
          className="menu-backdrop"
          aria-label="Dismiss navigation"
          onClick={() => setOpen(false)}
        />
      )}
      <div className="workspace">
        <div className="topbar">
          <button
            className="menu-button"
            aria-label={open ? "Close navigation" : "Open navigation"}
            aria-expanded={open}
            aria-controls="primary-navigation"
            onClick={() => setOpen(!open)}
          >
            {open ? <X /> : <Menu />}
          </button>
          <span>
            Workspace <ChevronRight size={13} /> <strong>{title}</strong>
          </span>
          <span className="private-label">PRIVATE WORKSPACE</span>
        </div>
        <main id="main-content">
          <Outlet />
        </main>
        <footer className="workspace-footer">
          <span>Cultivatinator</span>
          <span>Culture Library · Private single-user workspace</span>
        </footer>
      </div>
    </div>
  );
}
