import { createContext, useContext, useEffect, useState } from 'react';

import { api, TOKEN_KEY, USER_KEY } from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = window.localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }

    api
      .get('/auth/me')
      .then((response) => {
        setUser(response.data);
        window.localStorage.setItem(USER_KEY, JSON.stringify(response.data));
      })
      .catch(() => {
        window.localStorage.removeItem(TOKEN_KEY);
        window.localStorage.removeItem(USER_KEY);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const signIn = async (email, password) => {
    const response = await api.post('/auth/login', { email, password });
    window.localStorage.setItem(TOKEN_KEY, response.data.access_token);
    const profileResponse = await api.get('/auth/me');
    window.localStorage.setItem(USER_KEY, JSON.stringify(profileResponse.data));
    setUser(profileResponse.data);
    return profileResponse.data;
  };

  const signOut = () => {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
    setUser(null);
  };

  return <AuthContext.Provider value={{ user, loading, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return context;
}
