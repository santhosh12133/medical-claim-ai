import { NavLink } from 'react-router-dom';

export function AppShell({ title, subtitle, roleLabel, children, navItems, actions }) {
  return (
    <div className={`app-shell ${roleLabel ? `app-shell--${roleLabel.toLowerCase()}` : ''}`}>
      <header className="topbar">
        <div className="topbar-copy">
          <p className="eyebrow">Medical Claim AI</p>
          <div className="workspace-title-row">
            <h1>{title}</h1>
            {roleLabel ? <span className="role-chip">{roleLabel}</span> : null}
          </div>
          {subtitle ? <p className="hero-copy">{subtitle}</p> : null}
        </div>
        <nav className="nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-button ${item.variant === 'ghost' ? 'secondary' : ''} ${isActive ? 'nav-button--active' : ''}`.trim()}
            >
              {item.label}
            </NavLink>
          ))}
          {actions}
        </nav>
      </header>
      <main>{children}</main>
    </div>
  );
}
