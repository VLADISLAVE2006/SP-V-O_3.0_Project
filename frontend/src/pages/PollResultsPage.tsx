import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { pollsApi } from '../api/services';
import type { PollDetail, QuestionResult } from '../api/types';
import { Card } from '../components/ui/Card';
import { Alert } from '../components/ui/Alert';
import { Spinner } from '../components/ui/Spinner';
import { Badge } from '../components/ui/Badge';
import { useAuth } from '../contexts/AuthContext';
import { ChevronLeft } from 'lucide-react';

export const PollResultsPage = () => {
  const { slug } = useParams();
  const [poll, setPoll] = useState<PollDetail | null>(null);
  const [results, setResults] = useState<{ total_responses: number; questions: QuestionResult[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshInterval, setRefreshInterval] = useState<ReturnType<typeof setInterval> | null>(null);

  const fetchPoll = useCallback(async () => {
    if (!slug) return;
    try {
      setLoading(true);
      const data = await pollsApi.get(slug);
      setPoll(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки опроса');
    }
  }, [slug]);

  const fetchResults = useCallback(async () => {
    if (!slug) return;
    try {
      const data = await pollsApi.results(slug);
      setResults(data);
    } catch (err: any) {
      if (err.response?.status !== 403) {
        setError(err.response?.data?.detail || 'Ошибка загрузки результатов');
      }
    }
  }, [slug]);

  useEffect(() => {
    fetchPoll();
    fetchResults();
    setRefreshInterval(
      setInterval(fetchResults, 3000)
    );
    return () => {
      if (refreshInterval) clearInterval(refreshInterval);
    };
  }, [slug, fetchPoll, fetchResults, refreshInterval]);

  if (loading) {
    return (
      <div className="poll-results-page">
        <div className="poll-results-container">
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="poll-results-page">
        <div className="poll-results-container">
          <Alert variant="error" title="Ошибка">{error}</Alert>
        </div>
      </div>
    );
  }

  if (!poll) return null;

  const total = results?.total_responses || 0;

  return (
    <div className="poll-results-page">
      <div className="poll-results-container">
        <div className="poll-results-header">
          <Link to={`/polls/${poll.slug}`} className="results-back">
            <ChevronLeft size={18} /> Назад к опросу
          </Link>
          <div className="poll-results-meta">
            <Badge variant={poll.status === 'active' ? 'success' : 'danger'}>
              {poll.status === 'active' ? 'Активен' : 'Завершён'}
            </Badge>
            <Badge variant="info">Ответов: {total}</Badge>
          </div>
          <h1>{poll.title}</h1>
        </div>

        <div className="results-grid">
          {results?.questions.map((question) => (
            <Card key={question.id} className="result-question-card">
              <h3 className="result-question-title">{question.text}</h3>
              <div className="result-options">
                {question.options.map((option) => (
                  <div key={option.id} className="result-option-row">
                    <span className="result-option-text">{option.text}</span>
                    <div className="result-progress-container">
                      <div
                        className="result-progress-bar"
                        style={{ width: `${option.percent}%` }}
                      ></div>
                    </div>
                    <span className="result-option-count">
                      {option.votes} ({option.percent.toFixed(1)}%)
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
};