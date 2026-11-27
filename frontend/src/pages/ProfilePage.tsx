import { useState, useEffect } from 'react';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Card } from '../components/ui/Card';
import { Alert } from '../components/ui/Alert';
import { Spinner } from '../components/ui/Spinner';
import { Avatar } from '../components/ui/Avatar';
import { Badge } from '../components/ui/Badge';
import { useAuth } from '../contexts/AuthContext';
import { usersApi } from '../api/services';

export const ProfilePage = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [nickname, setNickname] = useState('');
  const [saving, setSaving] = useState(false);
  const { user, isAuthenticated } = useAuth();

  useEffect(() => {
    if (user) {
      setNickname(user.nickname);
    }
    setLoading(false);
  }, [user]);

  const handleSave = async () => {
    if (!nickname) {
      setError('Введите никнейм');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const data = await usersApi.updateNickname({ nickname });
      setNickname(data.nickname);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка сохранения никнейма');
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      // Fetch profile data on mount
      usersApi.getProfile(user?.id || 0).then(
        (data) => setNickname(data.nickname),
        (err) =>
          setError(err.response?.data?.detail || 'Ошибка загрузки профиля'),
      );
    }
  }, [isAuthenticated]);

  if (loading) {
    return (
      <div className='profile-page'>
        <div className='profile-container'>
          <Spinner size='lg' />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className='profile-page'>
        <div className='profile-container'>
          <Alert variant='error' title='Ошибка'>
            {error}
          </Alert>
        </div>
      </div>
    );
  }

  return (
    <div className='profile-page'>
      <div className='profile-container'>
        <div className='profile-header'>
          <h1>Профиль</h1>
        </div>

        {error && (
          <Alert variant='error' title='Ошибка'>
            {error}
          </Alert>
        )}

        <Card className='profile-card'>
          <div className='profile-info'>
            <Avatar size='lg' />
            <div className='profile-details'>
              <h2 className='profile-name'>{nickname || 'Пользователь'}</h2>
              <Badge variant='secondary'>user</Badge>
              <p className='profile-email'>
                {user?.email || 'email@example.com'}
              </p>
              <div className='profile-stats'>
                <span>Опросов: {user?.polls_count || 0}</span>
                <span>Предупреждений: {user?.warnings_count || 0}</span>
              </div>
            </div>
          </div>
        </Card>

        <Card className='profile-settings-card'>
          <h3 className='card-title'>Изменение никнейма</h3>
          <Input
            label='Новый никнейм'
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
          />
          <Button
            onClick={handleSave}
            disabled={!nickname || saving}
            loading={saving}
          >
            Сохранить
          </Button>
        </Card>
      </div>
    </div>
  );
};
