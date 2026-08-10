import { NavLink, Outlet } from "react-router-dom";

// /admin's shell — a real left sidebar instead of the earlier top-tab
// layout, matching the same nav-on-the-left pattern the actual product uses
// (see components/Sidebar.tsx), so this reads as a real internal tool
// rather than a one-off report page.
export default function AdminLayout() {
  return (
    <div className="admin-layout">
      <nav className="admin-sidebar">
        <div className="admin-sidebar__title">SwishX Admin</div>
        <NavLink to="/admin" end className={({ isActive }) => `admin-sidebar__link ${isActive ? "admin-sidebar__link--active" : ""}`}>
          Dashboard
        </NavLink>
        <NavLink to="/admin/visitors" className={({ isActive }) => `admin-sidebar__link ${isActive ? "admin-sidebar__link--active" : ""}`}>
          Visitors
        </NavLink>
        <NavLink to="/admin/attempts" className={({ isActive }) => `admin-sidebar__link ${isActive ? "admin-sidebar__link--active" : ""}`}>
          Attempts log
        </NavLink>
      </nav>
      <div className="admin-content">
        <Outlet />
      </div>
    </div>
  );
}
