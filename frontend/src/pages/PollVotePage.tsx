import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { pollsApi } from '../api/services';
import type { PollDetail } from '../api/types';
import { Button } from '../components/ui/Button';
import { Radio } from '../components/ui/Radio';
import { Card } from '../components/ui/Card';
import { Alert } from '../components/ui/Alert';
import { Spinner } from '../components/ui/Spinner';
import { Badge } from '../components/ui/Badge';
import { useAuth } from '../contexts/AuthContext';
import { ChevronRight } from 'lucide-react';

export const PollVotePage = () => {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuth();
  const [poll, setPoll] = useState<PollDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [voting, setVoting] = useState(false);
  const [hasVoted, setHasVoted] = useState(false);
  const [canVote, setCanVote] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [selections, setSelections] = useState<Record<number, number[]>>({});

  const fetchPoll = useCallback(async () => {
    if (!slug) return;
    try {
      setLoading(true);
      const data = await pollsApi.get(slug);
      setPoll(data);
      setCanVote(data.can_vote ?? false);
      setHasVoted(data.has_voted ?? false);
      const initial: Record<number, number[]> = {};
      data.questions.forEach((q: { id: number }) => {
        initial[q.id] = data.my_answers?.find((a: { question_id: number }) => a.question_id === q.id)?.option_ids || [];
      });
      setSelections(initial);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки опроса');
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    fetchPoll();
  }, [fetchPoll]);

  const handleSelectionChange = (questionId: number, value: string | number) => {
    const ids = Array.isArray(value) ? value : [value];
    setSelections((prev) => ({ ...prev, [questionId]: ids as number[] }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setVoting(true);
    try {
      const answers = Object.entries(selections).map(([questionId, optionIds]) => ({
        question_id: parseInt(questionId),
        option_ids: optionIds,
      }));
      await pollsApi.vote(slug!, { answers });
      setSubmitted(true);
      setHasVoted(true);
      fetchPoll();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка голосования');
    } finally {
      setVoting(false);
    }
  };

  if (loading) {
    return (
      <div className="poll-vote-page">
        <div className="poll-vote-container">
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="poll-vote-page">
        <div className="poll-vote-container">
          <Alert variant="error" title="Ошибка">{error}</Alert>
          <Button onClick={fetchPoll}>Попробовать снова</Button>
        </div>
      </div>
    );
  }

  if (!poll) return null;

  const accessModeLabel = poll.access_mode === 'anonymous' ? 'Анонимный' : 'Только для зарегистрированных';

  return (
    <div className="poll-vote-page">
      <div className="poll-vote-container">
        <div className="poll-vote-header">
          <div className="poll-vote-meta">
            <Badge variant={poll.status === 'active' ? 'success' : 'danger'}>
              {poll.status === 'active' ? 'Активен' : 'Завершён'}
            </Badge>
            <Badge variant="info">{accessModeLabel}</Badge>
          </div>
          <h1>{poll.title}</h1>
          {poll.description && <p className="poll-vote-description">{poll.description}</p>}
        </div>

        {submitted ? (
          <div className="poll-vote-success">
            <Card>
              <h3>Спасибо за участие!</h3>
              <p>Ваш ответ был учтён.</p>
              <Button onClick={() => navigate(`/polls/${poll.slug}/results`)}>
                Посмотреть результаты <ChevronRight size={18} />
              </Button>
            </Card>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="poll-vote-form">
            {!isAuthenticated && poll.access_mode === 'registered' ? (
              <Alert variant="warning" title="Требуется вход">
                Для участия в этом опросе необходимо войти в систему.
              </Alert>
            ) : !canVote ? (
              <Alert variant="info" title="Голосование недоступно">
                {hasVoted
                  ? 'Вы уже участвовали в этом опросе.'
                  : 'Вы не можете участвовать в этом опросе.'}
              </Alert>
            ) : (
              poll.questions.map((question) => (
                <Card key={question.id} className="question-card">
                  <h3 className="question-title">{question.text}</h3>
                  <Radio
                    options={question.options.map((opt) => ({
                      value: opt.id,
                      label: opt.text,
                    }))}
                    value={selections[question.id]?.[0] || null}
                    onChange={(val) => handleSelectionChange(question.id, val)}
                  />
                  {question.type === 'multiple' && (
                    <p className="question-hint">
                      Выберите от {question.min_choices} до {question.max_choices} вариантов
                    </p>
                  )}
                </Card>
              ))
            )}
            {canVote && isAuthenticated && poll.access_mode !== 'registered' && (
              <Button type="submit" variant="primary" loading={voting} disabled={voting || !canVote} fullWidth>
                Голосовать
              </Button>
            )}
          </form>
        )}
      </div>
    </div>
  );
};
