import { useEffect, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { AppShell } from '../components/AppShell';
import { SectionCard } from '../components/SectionCard';

// No credentials are compiled into the bundle. For local demos, pre-fill the form from a git-ignored
// frontend/.env.local, e.g. VITE_DEMO_EMPLOYEE_EMAIL / VITE_DEMO_EMPLOYEE_PASSWORD (and ADMIN equivalents).
const env = import.meta.env;
const DEFAULT_CREDENTIALS = {
  employee: { email: env.VITE_DEMO_EMPLOYEE_EMAIL || '', password: env.VITE_DEMO_EMPLOYEE_PASSWORD || '' },
  admin: { email: env.VITE_DEMO_ADMIN_EMAIL || '', password: env.VITE_DEMO_ADMIN_PASSWORD || '' },
};

export function RoleLoginPage({ role, title, subtitle }) {
  const navigate = useNavigate();
  const { user, loading, signIn } = useAuth();
  const defaults = DEFAULT_CREDENTIALS[role];
  const [email, setEmail] = useState(defaults.email);
  const [password, setPassword] = useState(defaults.password);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (user) {
      navigate(user.role === 'admin' ? '/admin/dashboard' : '/employee/dashboard', { replace: true });
    }
  }, [navigate, user]);

  const onSubmit = async (event) => {
    event.preventDefault();
    try {
      const signedInUser = await signIn(email, password);
      if (signedInUser.role !== role) {
        setMessage(`Please use the ${role} account for this page.`);
        return;
      }

      setMessage('Login successful');
      navigate(role === 'admin' ? '/admin/dashboard' : '/employee/dashboard', { replace: true });
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Login failed');
    }
  };

  if (user) {
    return <Navigate to={user.role === 'admin' ? '/admin/dashboard' : '/employee/dashboard'} replace />;
  }

  return (
    <AppShell title="Medical Claim AI" subtitle={subtitle} navItems={[]}>
      <SectionCard title={title} subtitle="Separate login page">
        <form className="stack" onSubmit={onSubmit}>
          <label>
            Email
            <input value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <button type="submit">Sign in</button>
          {loading ? <p className="hint">Restoring session...</p> : null}
          {message ? <p className="status-text">{message}</p> : null}
          <p className="hint">Demo accounts are created with backend/scripts/seed_demo_users.py (see README).</p>
        </form>
      </SectionCard>
    </AppShell>
  );
}
