import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { api } from '../api';
import { AppShell } from '../components/AppShell';

export const OPEN_STATUSES = new Set(['Pending', 'Pending Review', 'Needs Attention', 'Processing']);

export function AdminLayout() {
  const location = useLocation();
  const [waiting, setWaiting] = useState(0);

  // Refresh the queue count whenever the reviewer moves between pages.
  useEffect(() => {
    api.get('/claims')
      .then((response) => setWaiting(response.data.filter((claim) => OPEN_STATUSES.has(claim.status)).length))
      .catch(() => setWaiting(0));
  }, [location.pathname]);

  return (
    <AppShell navItems={[
      { label: 'Overview', to: '/admin/dashboard', icon: 'overview' },
      { label: 'Review queue', to: '/admin/review', icon: 'queue', count: waiting },
      { label: 'All claims', to: '/admin/claims', icon: 'table' },
      { label: 'Policies', to: '/admin/policies', icon: 'policies' },
      { label: 'Coverage questions', to: '/admin/assistant', icon: 'assistant' },
    ]} />
  );
}
