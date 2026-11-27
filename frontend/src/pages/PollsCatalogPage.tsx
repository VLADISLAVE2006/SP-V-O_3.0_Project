import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { pollsApi } from '../api/services';
import type { PollSummary } from '../api/types';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Spinner } from '../components/ui/Spinner';
import { Alert } from '../components/ui/Alert';
import { useAuth } from '../contexts/AuthContext';
import { List, Calendar, Users } from 'lucide-react';

const STATUS_OPTIONS = [
  { value: '', label: 'Все статусы' },
  { value: 'active', label: 'Активные' },
  { value: 'finished', label: 'Завершённые' },
];

const SORT_OPTIONS = [
  { value: 'new', label: 'Новые' },
  { value: 'popular', label: 'Популярные' },
];

export const PollsCatalogPage = () => {
  const [polls, setPolls] = useState<PollSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [sort, setSort] = useState('new');
  const { isAuthenticated } = useAuth();

  const LIMIT = 10;

  const fetchPolls = async (reset = false) => {
    try {
      setLoading(true);
      const params: any = {
        limit: LIMIT,
        offset: reset ? 0 : offset,
      };
      if (q) params.q = q;
      if (status) params.status = status;
      if (sort) params.sort = sort;

      const data = await pollsApi.list(params);
      if (reset) {
        setPolls(data.items || []);
        setOffset(data.items?.length ?? 0);
      } else {
        setPolls((prev) => [...prev, ...(data.items || [])]);
        setOffset((prev) => prev + (data.items?.length ?? 0));
      }
      setHasMore(data.has_more ?? false);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки опросов');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPolls(true);
  }, [q, status, sort]);

  const loadMore = () => {
    if (!hasMore || loading) return;
    fetchPolls(false);
  };

  return (
    <div className='catalog-page'>
      <div className='catalog-container'>
        <div className='catalog-header'>
          <div className='catalog-title-section'>
            <h1>Опросы</h1>
            <p>Выберите опрос для участия или просмотра результатов</p>
          </div>

          {isAuthenticated && (
            <Link to='/polls/create'>
              <Button variant='primary'>Создать опрос</Button>
            </Link>
          )}
        </div>

        <div className='catalog-filters'>
          <Input
            label='Поиск'
            placeholder='Поиск по названию...'
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <Select
            label='Статус'
            options={STATUS_OPTIONS}
            value={status || ''}
            onChange={(e) => setStatus((e.target as HTMLSelectElement).value)}
          />
          <Select
            label='Сортировка'
            options={SORT_OPTIONS}
            value={sort}
            onChange={(e) => setSort((e.target as HTMLSelectElement).value)}
          />
        </div>

        {error && (
          <Alert variant='error' title='Ошибка'>
            {error}
          </Alert>
        )}

        <div className='catalog-grid'>
          {loading && !polls.length ? (
            <div className='catalog-loading'>
              <Spinner size='lg' />
            </div>
          ) : polls.length === 0 ? (
            <div className='catalog-empty'>
              <p>Опросы не найдены</p>
            </div>
          ) : (
            polls.map((poll) => (
              <Card key={poll.id} className='poll-card'>
                <div className='poll-card-header'>
                  <Link to={`/polls/${poll.slug}`}>
                    <h3 className='poll-card-title'>{poll.title}</h3>
                  </Link>
                  <Badge
                    variant={
                      poll.status === 'active'
                        ? 'success'
                        : poll.status === 'finished'
                          ? 'danger'
                          : 'secondary'
                    }
                  >
                    {poll.status === 'active'
                      ? 'Активен'
                      : poll.status === 'finished'
                        ? 'Завершён'
                        : 'Черновик'}
                  </Badge>
                </div>
                {poll.description && (
                  <p className='poll-card-description'>{poll.description}</p>
                )}
                <div className='poll-card-meta'>
                  <span className='poll-card-meta-item'>
                    <Calendar size={14} />
                    {poll.author.nickname}
                  </span>
                  <span className='poll-card-meta-item'>
                    <Users size={14} />
                    {poll.responses_count} ответов
                  </span>
                </div>
              </Card>
            ))
          )}
        </div>

        {hasMore && !loading && (
          <div className='catalog-load-more'>
            <Button variant='outline' onClick={loadMore} fullWidth>
              Загрузить ещё
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};
