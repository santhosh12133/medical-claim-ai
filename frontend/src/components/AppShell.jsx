import { NavLink } from 'react-router-dom';

export function AppShell({ title, subtitle, roleLabel, children, navItems, actions }) {
  const isPortal = Boolean(roleLabel);

  return (
    <div className={`app-shell ${isPortal ? 'app-shell--portal' : 'app-shell--public'} ${roleLabel ? `app-shell--${roleLabel.toLowerCase()}` : ''}`}>
      {isPortal ? (
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">MC</div>
            <div>
              <strong>Medical Claim AI</strong>
              <span>Claims intelligence</span>
            </div>
          </div>

          <div className="sidebar-section-label">Workspace</div>
          <nav className="sidebar-nav" aria-label="Primary navigation">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `sidebar-link ${isActive ? 'sidebar-link--active' : ''}`}
              >
                <span className="sidebar-link__dot" aria-hidden="true" />
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="sidebar-footer">
            <div className="account-card">
              <div className="avatar">{roleLabel.slice(0, 1)}</div>
              <div>
                <strong>{roleLabel} Portal</strong>
                <span>Secure workspace</span>
              </div>
            </div>
            {actions}
          </div>
        </aside>
      ) : null}

      <div className="app-content">
        <header className="page-header">
          <div>
            <p className="eyebrow">{isPortal ? `${roleLabel} workspace` : 'Intelligent claims platform'}</p>
            <div className="workspace-title-row">
              <h1>{title}</h1>
              {roleLabel ? <span className="role-chip">{roleLabel}</span> : null}
            </div>
            {subtitle ? <p className="hero-copy">{subtitle}</p> : null}
          </div>
          {!isPortal && actions ? <div className="header-actions">{actions}</div> : null}
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
