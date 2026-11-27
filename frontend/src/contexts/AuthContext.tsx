import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react';
import { saveTokens, clearTokens } from '../api/client';
import { authApi } from '../api/services';
import type { Profile } from '../api/types';

interface AuthContextType {
  user: Profile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (access: string, refresh: string, profile: Profile) => void;
  logout: () => void;
  setTokens: (access: string, refresh: string) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<Profile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Check for existing tokens on load
    const stored = localStorage.getItem('polls_tokens');
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        if (parsed.access && parsed.refresh) {
          // We have tokens but need to fetch profile
          authApi.me()
            .then(setUser)
            .catch(() => {
              clearTokens();
              setUser(null);
            })
            .finally(() => setIsLoading(false));
          return;
        }
      } catch {
        // ignore
      }
    }
    setIsLoading(false);
  }, []);

  const handleLogout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const login = useCallback((access: string, refresh: string, profile: Profile) => {
    saveTokens({ access, refresh });
    setUser(profile);
  }, []);

  const setTokens = useCallback((access: string, refresh: string) => {
    saveTokens({ access, refresh });
  }, []);

  const logout = useCallback(() => {
    authApi.logout().catch(() => {
      // ignore errors on logout
    });
    handleLogout();
  }, [handleLogout]);

  const value = {
    user,
    isAuthenticated: !!user,
    isLoading,
    login,
    logout,
    setTokens,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};