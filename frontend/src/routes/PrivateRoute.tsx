import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import type { ComponentType } from 'react';

export const requireAuth = (Component: ComponentType) => {
  const AuthenticatedComponent = () => {
    const { isAuthenticated, isLoading } = useAuth();
    if (isLoading) return null;
    if (!isAuthenticated) return <Navigate to="/login" replace />;
    return <Component />;
  };
  return AuthenticatedComponent;
};