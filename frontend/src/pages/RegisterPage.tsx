import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { authApi } from '../api/services';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Alert } from '../components/ui/Alert';
import { Card } from '../components/ui/Card';
import { ArrowRight } from 'lucide-react';

export const RegisterPage = () => {
  const [email, setEmail] = useState('');
  const [nickname, setNickname] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const result = await authApi.register({ email, nickname, password });
      login(result.access, result.refresh, result.profile);
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка регистрации.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-container">
        <Card className="auth-card">
          <div className="auth-header">
            <div className="auth-icon">
              <User size={32} />
            </div>
            <h1>Регистрация</h1>
            <p className="auth-subtitle">Создайте новую учётную запись</p>
          </div>

          {error && (
            <Alert variant="error" title="Ошибка">
              {error}
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="auth-form">
            <Input
              label="Никнейм"
              placeholder="ivanov"
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              required
            />
            <Input
              label="Email"
              type="email"
              placeholder="user@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <Input
              label="Пароль"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <Button type="submit" className="auth-submit-btn" loading={loading} disabled={loading} fullWidth>
              Зарегистрироваться <ArrowRight size={18} />
            </Button>
          </form>

          <div className="auth-footer">
            Уже есть учётная запись?{' '}
            <Link to="/login" className="auth-link">Войти</Link>
          </div>
        </Card>
      </div>
    </div>
  );
};