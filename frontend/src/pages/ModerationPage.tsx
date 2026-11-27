import { useState, useEffect } from 'react';
import { Card } from '../components/ui/Card';
import { Alert } from '../components/ui/Alert';
import { Spinner } from '../components/ui/Spinner';
import { MessageSquare } from 'lucide-react';
import { reportsApi } from '../api/services';

export const ModerationPage = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reports, setReports] = useState<any[]>([]);

  useEffect(() => {
    const fetchReports = async () => {
      try {
        const data = await reportsApi.list();
        setReports(data.items || []);
        setLoading(false);
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Ошибка загрузки жалоб');
        setLoading(false);
      }
    };

    fetchReports();
  }, []);

  if (loading) {
    return (
      <div className="moderation-page">
        <div className="moderation-container">
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="moderation-page">
        <div className="moderation-container">
          <Alert variant="error" title="Ошибка">{error}</Alert>
        </div>
      </div>
    );
  }

  return (
    <div className="moderation-page">
      <div className="moderation-container">
        <div className="moderation-header">
          <div className="moderation-icon">
            <MessageSquare size={32} />
          </div>
          <h1>Модерация</h1>
          <p>Рассмотрение жалоб и управление контентом</p>
        </div>

        {reports.length === 0 ? (
          <Card className="moderation-card">
            <div className="moderation-empty">
              <p>Жалобы не найдены</p>
            </div>
          </Card>
        ) : (
          <Card className="moderation-card">
            <div className="moderation-reports">
              {reports.map((report) => (
                <div
                  key={report.id}
                  className="report-item"
                >
                  <div className="report-info">
                    <span className="report-poll-slug">
                      Poll: {report.poll_slug || '—'}
                    </span>
                    <span className="report-comment-id">
                      Comment: {report.comment_id || '—'}
                    </span>
                  </div>
                  <div className="report-meta">
                    <span className="report-status">
                      {report.status}: {report.reviewed_at || '—'}
                    </span>
                    <span className="report-created">
                      created: {report.created_at || '—'}
                    </span>
                  </div>
                  <div className="report-actions">
                    <button
                      className="btn-review"
                      onClick={() => {}}
                    >
                      Рассмотреть
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
};