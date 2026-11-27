import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { pollsApi } from '../api/services';
import type { PollInputRequest, QuestionInputRequest, QuestionType, OptionInputRequest } from '../api/types';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Textarea } from '../components/ui/Textarea';
import { Card } from '../components/ui/Card';
import { Alert } from '../components/ui/Alert';
import { Plus, Trash2 } from 'lucide-react';

const QUESTION_TYPE_LABELS: Record<QuestionType, string> = {
  single: 'Один вариант',
  multiple: 'Несколько вариантов',
  scale: 'Шкала от 1 до 5',
};

const INITIAL_QUESTION: QuestionInputRequest = {
  text: '',
  type: 'single',
  min_choices: 1,
  max_choices: 1,
  options: [],
};

const INITIAL_OPTION: OptionInputRequest = { text: '' };

export const PollCreatePage = () => {
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [accessMode, setAccessMode] = useState<'anonymous' | 'registered'>('anonymous');
  const [visibility, setVisibility] = useState<'public' | 'link'>('public');
  const [allowRevote, setAllowRevote] = useState(false);
  const [commentsEnabled, setCommentsEnabled] = useState(true);
  const [questions, setQuestions] = useState<QuestionInputRequest[]>([INITIAL_QUESTION]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const addQuestion = useCallback(() => {
    setQuestions((prev) => [...prev, { ...INITIAL_QUESTION }]);
  }, []);

  const removeQuestion = useCallback((index: number) => {
    setQuestions((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const updateQuestion = useCallback((index: number, field: keyof QuestionInputRequest, value: any) => {
    setQuestions((prev) =>
      prev.map((q, i) => (i === index ? { ...q, [field]: value } : q))
    );
  }, []);

  const addOption = useCallback((questionIndex: number) => {
    setQuestions((prev) =>
      prev.map((q, i) =>
        i === questionIndex ? { ...q, options: [...(q.options || []), { ...INITIAL_OPTION }] } : q
      )
    );
  }, []);

  const removeOption = useCallback((questionIndex: number, optionIndex: number) => {
    setQuestions((prev) =>
      prev.map((q, i) =>
        i === questionIndex
          ? { ...q, options: (q.options || []).filter((_, oi) => oi !== optionIndex) }
          : q
      )
    );
  }, []);

  const updateOption = useCallback((questionIndex: number, optionIndex: number, value: string) => {
    setQuestions((prev) =>
      prev.map((q, i) => {
        if (i !== questionIndex) return q;
        const options = [...(q.options || [])];
        options[optionIndex] = { ...options[optionIndex], text: value };
        return { ...q, options };
      })
    );
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const payload: PollInputRequest = {
        title,
        description: description || null,
        access_mode: accessMode,
        visibility,
        allow_revote: allowRevote,
        comments_enabled: commentsEnabled,
        questions: questions.map((q) => ({
          text: q.text,
          type: q.type,
          min_choices: q.type === 'multiple' ? (q.min_choices || 1) : 1,
          max_choices: q.type === 'multiple' ? (q.max_choices || 1) : 1,
          options:
            q.type === 'scale'
              ? undefined
              : (q.options || []).filter((o) => o.text.trim()).map((o) => ({ text: o.text })),
        })),
      };
      const poll = await pollsApi.create(payload);
      navigate(`/polls/${poll.slug}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка создания опроса');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="poll-create-page">
      <div className="poll-create-container">
        <div className="poll-create-header">
          <h1>Создание опроса</h1>
          <p>Настройте опрос, добавьте вопросы и варианты ответов</p>
        </div>

        {error && <Alert variant="error" title="Ошибка">{error}</Alert>}

        <form onSubmit={handleSubmit} className="poll-create-form">
          <Card className="poll-settings-card">
            <h3 className="card-title">Основные настройки</h3>
            <div className="settings-grid">
              <Input
                label="Название опроса *"
                placeholder="Какие занятия интереснее?"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
              <Textarea
                label="Описание"
                placeholder="Краткое описание опроса..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
              <Select
                label="Режим доступа"
                options={[
                  { value: 'anonymous', label: 'Анонимный (для всех)' },
                  { value: 'registered', label: 'Только для зарегистрированных' },
                ]}
                value={accessMode}
                onChange={(e) => setAccessMode((e.target as HTMLSelectElement).value as 'anonymous' | 'registered')}
              />
              <Select
                label="Видимость"
                options={[
                  { value: 'public', label: 'Публичный (в каталоге)' },
                  { value: 'link', label: 'По ссылке (скрыт из каталога)' },
                ]}
                value={visibility}
                onChange={(e) => setVisibility((e.target as HTMLSelectElement).value as 'public' | 'link')}
              />
            </div>
            <div className="settings-toggle">
              <label className="toggle-label">
                <input
                  type="checkbox"
                  checked={allowRevote}
                  onChange={(e) => setAllowRevote(e.target.checked)}
                />
                Разрешить повторное голосование
              </label>
              <label className="toggle-label">
                <input
                  type="checkbox"
                  checked={commentsEnabled}
                  onChange={(e) => setCommentsEnabled(e.target.checked)}
                />
                Включить комментарии
              </label>
            </div>
          </Card>

          <Card className="poll-questions-card">
            <div className="card-header-flex">
              <h3 className="card-title">Вопросы</h3>
              <Button type="button" variant="outline" size="sm" onClick={addQuestion} fullWidth>
                <Plus size={14} /> Добавить вопрос
              </Button>
            </div>

            {questions.map((question, qIndex) => (
              <div key={qIndex} className="question-builder">
                <div className="question-header">
                  <span className="question-number">Вопрос {qIndex + 1}</span>
                  <Button
                    type="button"
                    variant="danger"
                    size="sm"
                    onClick={() => removeQuestion(qIndex)}
                    disabled={questions.length === 1}
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
                <Input
                  label="Текст вопроса *"
                  placeholder="Введите вопрос..."
                  value={question.text}
                  onChange={(e) => updateQuestion(qIndex, 'text', e.target.value)}
                  required
                />
                <Select
                  label="Тип вопроса"
                  options={[
                    { value: 'single', label: QUESTION_TYPE_LABELS.single },
                    { value: 'multiple', label: QUESTION_TYPE_LABELS.multiple },
                    { value: 'scale', label: QUESTION_TYPE_LABELS.scale },
                  ]}
                  value={question.type}
                  onChange={(e) => {
                    const newType = (e.target as HTMLSelectElement).value as QuestionType;
                    updateQuestion(qIndex, 'type', newType);
                    if (newType === 'scale') {
                      updateQuestion(qIndex, 'options', []);
                    }
                  }}
                />
                {question.type === 'multiple' && (
                  <div className="choices-range">
                    <Input
                      label="Минимум вариантов"
                      type="number"
                      min="1"
                      value={String(question.min_choices || 1)}
                      onChange={(e) => updateQuestion(qIndex, 'min_choices', parseInt(e.target.value) || 1)}
                    />
                    <Input
                      label="Максимум вариантов"
                      type="number"
                      min="1"
                      value={String(question.max_choices || 1)}
                      onChange={(e) => updateQuestion(qIndex, 'max_choices', parseInt(e.target.value) || 1)}
                    />
                  </div>
                )}
                {(question.type === 'single' || question.type === 'multiple') && (
                  <div className="options-list">
                    <div className="options-header">
                      <span>Варианты ответа</span>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => addOption(qIndex)}
                      >
                        <Plus size={14} /> Вариант
                      </Button>
                    </div>
                    {(question.options || []).map((option, oIndex) => (
                      <div key={oIndex} className="option-row">
                        <Input
                          label=""
                          placeholder="Текст варианта"
                          value={option.text}
                          onChange={(e) => updateOption(qIndex, oIndex, e.target.value)}
                        />
                        <Button
                          type="button"
                          variant="danger"
                          size="sm"
                          onClick={() => removeOption(qIndex, oIndex)}
                          disabled={(question.options || []).length <= 1}
                        >
                          <Trash2 size={14} />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </Card>

          <div className="poll-create-actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} fullWidth>
              Создать опрос
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};