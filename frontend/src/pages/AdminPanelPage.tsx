import { useState, useEffect } from 'react';
import { Card } from '../components/ui/Card';
import { Alert } from '../components/ui/Alert';
import { Spinner } from '../components/ui/Spinner';
import { Shield, List } from 'lucide-react';
import { adminApi } from '../api/services';

export const AdminPanelPage = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [users, setUsers] = useState<any[]>([]);

  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const data = await adminApi.listUsers();
        setUsers(data.items || []);
        setLoading(false);
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Ошибка загрузки пользователей');
        setLoading(false);
      }
    };

    fetchUsers();
  }, []);

  if (loading) {
    return (
      <div className="admin-page">
        <div className="admin-container">
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="admin-page">
        <div className="admin-container">
          <Alert variant="error" title="Ошибка">{error}</Alert>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-container">
        <div className="admin-header">
          <div className="admin-icon">
            <Shield size={32} />
          </div>
          <h1>Админ-панель</h1>
          <p>Управление пользователями и ролями</p>
        </div>

        {error && <Alert variant="error" title="Ошибка">{error}</Alert>}

        <Card className="admin-card">
          <div className="admin-section">
            <div className="section-header">
              <List size={20} />
              <h2>Пользователи</h2>
            </div>

            {users.length === 0 ? (
              <div className="admin-empty">
                <p>Пользователи не найдены</p>
              </div>
            ) : (
              <div className="admin-users-list">
                {users.map((user) => (
                  <div
                    key={user.id}
                    className="admin-user-row"
                  >
                    <span className="admin-user-id">{user.id}</span>
                    <span className="admin-user-nickname">{user.nickname}</span>
                    <span className="admin-user-role">
                      <Badge variant={user.role === 'admin' ? 'danger' : 'secondary'}>
                        {user.role}
                      </Badge>
                    </span>
                    <div className="admin-user-actions">
                      <button className="btn-small">Бан</button>
                      <button className="btn-small">Снять бан</button>
                      <button className="btn-small">Изменить роль</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
};