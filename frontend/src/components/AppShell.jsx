import { NavLink, Outlet } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { BrandMark, Icon } from './Icon';

const ROLE_NAMES = { admin: 'Claims reviewer', employee: 'Employee' };

function initials(name) {
  return String(name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('');
}

/** Signed-in frame: sidebar navigation (a top bar on small screens) and the page. */
export function AppShell({ navItems }) {
  const { user, signOut } = useAuth();

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className="sidebar">
        <div className="sidebar__brand">
          <BrandMark />
          <span>Medical Claim AI</span>
        </div>

        <nav className="sidebar__nav" aria-label="Main">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to}
              className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}>
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.count ? <span className="nav-link__count">{item.count}</span> : null}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__user">
          <span className="avatar" aria-hidden="true">{initials(user?.full_name)}</span>
          <div className="sidebar__who">
            <strong>{user?.full_name}</strong>
            <span>{ROLE_NAMES[user?.role] || user?.role}</span>
          </div>
          <button type="button" className="icon-button" onClick={signOut} aria-label="Sign out" title="Sign out">
            <Icon name="signout" />
          </button>
        </div>
      </aside>

      <main id="main" className="workspace" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
