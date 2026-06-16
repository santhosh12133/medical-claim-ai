import { useEffect, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { AppShell } from '../components/AppShell';
import { SectionCard } from '../components/SectionCard';

export function LoginPage() {
  const navigate = useNavigate();
  const { user, loading, signIn } = useAuth();
  const [email, setEmail] = useState('employee@demo.com');
  const [password, setPassword] = useState('employee123');
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
      setMessage('Login successful');
      navigate(signedInUser.role === 'admin' ? '/admin/dashboard' : '/employee/dashboard', { replace: true });
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Login failed');
    }
  };

  if (user) {
    return <Navigate to={user.role === 'admin' ? '/admin/dashboard' : '/employee/dashboard'} replace />;
  }

  return (
    <AppShell title="Claims workflow foundation" subtitle="Sign in to access employee or admin pages." navItems={[]}>
      <SectionCard title="Login" subtitle="Employee or admin access">
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
          <p className="hint">Demo users: employee@demo.com / employee123 and admin@demo.com / admin123</p>
        </form>
      </SectionCard>
    </AppShell>
  );
}
