import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { Button } from '../ui/Button';
import { Avatar } from '../ui/Avatar';
import { Badge } from '../ui/Badge';
import { LogOut, User, List, Shield, MessageSquare } from 'lucide-react';

export const Navbar = () => {
  const { user, isAuthenticated, isLoading, logout } = useAuth();
  const location = useLocation();

  const navItems = [
    { path: '/', label: 'Опросы', icon: List },
    { path: '/polls/create', label: 'Создать опрос', icon: List },
    { path: '/profile', label: 'Профиль', icon: User },
  ];

  const adminItems = [
    { path: '/admin', label: 'Админ-панель', icon: Shield },
    { path: '/moderation', label: 'Модерация', icon: MessageSquare },
  ];

  if (isLoading) {
    return null;
  }

  const isAuthRoute = location.pathname.startsWith('/login') || location.pathname.startsWith('/register');

  return (
    <nav className="navbar">
      <div className="navbar-container">
        <div className="navbar-brand">
          <Link to="/" className="navbar-logo">
            <span className="logo-text">Опросы</span>
          </Link>
        </div>

        <div className="navbar-nav">
          {isAuthenticated && (
            <>
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`navbar-link ${
                    location.pathname === item.path ? 'navbar-link-active' : ''
                  }`}
                >
                  <item.icon size={18} />
                  {item.label}
                </Link>
              ))}
              {user?.role === 'admin' && (
                <>
                  {adminItems.map((item) => (
                    <Link
                      key={item.path}
                      to={item.path}
                      className={`navbar-link ${
                        location.pathname === item.path || location.pathname.startsWith(item.path.replace('/admin', '')) ? 'navbar-link-active' : ''
                      }`}
                    >
                      <item.icon size={18} />
                      {item.label}
                    </Link>
                  ))}
                </>
              )}
            </>
          )}
        </div>

        <div className="navbar-actions">
          {isAuthenticated ? (
            <div className="navbar-user">
              <button
                type="button"
                onClick={logout}
                className="navbar-logout"
                title="Выйти"
              >
                <LogOut size={18} />
              </button>
              <div className="navbar-user-info">
                <div className="navbar-user-nickname">{user?.nickname}</div>
                <div className="navbar-user-role">
                  <Badge variant={user?.role === 'admin' ? 'danger' : 'secondary'}>
                    {user?.role}
                  </Badge>
                </div>
                <Avatar src={user?.avatar_url || null} alt={user?.nickname || ''} size="sm" />
              </div>
            </div>
          ) : !isAuthRoute && (
            <>
              <Link to="/login" className="navbar-link navbar-link-text">Войти</Link>
              <Link to="/register" className="navbar-link-text">
                <Button variant="outline" size="sm">Регистрация</Button>
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
};