import React, { useEffect, useMemo, useState } from 'react';
import { LinkOutlined, SearchOutlined, UploadOutlined } from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import {
  Alert,
  Button,
  Descriptions,
  Input,
  List,
  Segmented,
  Select,
  Space,
  Tabs,
  Typography,
  Upload,
  message,
} from 'antd';
import type { UploadRequestOption as RcCustomRequestOptions } from 'rc-upload/lib/interface';

import { API_BASE, apiRequest, artifactUrl } from '@/utils/api';
import type { EnvironmentSnapshot } from '@/utils/environment';

type FileMeta = {
  name: string;
  size_bytes?: number;
  modified_at?: string;
};

type ReviewState = {
  review_id: string;
  sources: FileMeta[];
  artifacts: FileMeta[];
  latest_preview: string;
  latest_meta?: {
    document_type?: string;
    model?: string;
    created_at?: string;
    sources?: string[];
    [key: string]: unknown;
  } | null;
};

type SourceMode = 'files' | 'links';

export default function ReviewPage() {
  const [environment, setEnvironment] = useState<EnvironmentSnapshot | null>(null);
  const [reviewId, setReviewId] = useState('');
  const [reviewState, setReviewState] = useState<ReviewState | null>(null);
  const [sourceMode, setSourceMode] = useState<SourceMode>('links');
  const [confluenceUrls, setConfluenceUrls] = useState('');
  const [documentType, setDocumentType] = useState<'auto' | 'ft' | 'nft'>('auto');
  const [reviewModel, setReviewModel] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  const currentReviewId = reviewId.trim();
  const linkRows = useMemo(
    () => confluenceUrls.split(/\n+/).map((item) => item.trim()).filter(Boolean),
    [confluenceUrls],
  );
  const reviewModelOptions = environment?.review_models || [];

  async function loadEnvironment() {
    const payload = await apiRequest<EnvironmentSnapshot>('/ui/environment-settings');
    setEnvironment(payload);
  }

  async function loadReviewState(targetReviewId: string) {
    if (!targetReviewId) {
      setReviewState(null);
      return;
    }
    const payload = await apiRequest<ReviewState>(`/ui/review-state/${encodeURIComponent(targetReviewId)}`);
    setReviewState(payload);
  }

  useEffect(() => {
    void loadEnvironment();
  }, []);

  useEffect(() => {
    if (!reviewModel && reviewModelOptions.length) {
      setReviewModel(reviewModelOptions[0]);
    }
    if (reviewModel && reviewModelOptions.length && !reviewModelOptions.includes(reviewModel)) {
      setReviewModel(reviewModelOptions[0]);
    }
  }, [reviewModel, reviewModelOptions]);

  useEffect(() => {
    if (!currentReviewId) {
      setReviewState(null);
      return;
    }
    void loadReviewState(currentReviewId);
  }, [currentReviewId]);

  async function withBusy(key: string, action: () => Promise<void>, successMessage: string) {
    setBusy(key);
    try {
      await action();
      message.success(successMessage);
      await loadEnvironment();
      if (currentReviewId) {
        await loadReviewState(currentReviewId);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Операция завершилась ошибкой');
    } finally {
      setBusy(null);
    }
  }

  async function importConfluenceLinks() {
    if (!currentReviewId) {
      message.error('Сначала укажи Review ID');
      return;
    }
    if (!linkRows.length) {
      message.error('Добавь хотя бы одну ссылку');
      return;
    }
    const baseUrl = environment?.settings.confluence_base_url?.trim();
    const invalidLinks = baseUrl ? linkRows.filter((item) => !item.startsWith(baseUrl)) : [];
    if (invalidLinks.length) {
      message.error('Часть ссылок не совпадает с Base URL Confluence из настроек окружения');
      return;
    }
    await withBusy('links', async () => {
      await apiRequest('/ui/review-import-confluence', {
        method: 'POST',
        body: JSON.stringify({ review_id: currentReviewId, urls: linkRows }),
      });
    }, 'Статья по ссылке импортирована для ревью');
  }

  async function uploadSource(options: RcCustomRequestOptions) {
    if (!currentReviewId) {
      message.error('Сначала укажи Review ID');
      options.onError?.(new Error('Review ID is required'));
      return;
    }
    const formData = new FormData();
    formData.append('files', options.file as Blob, (options.file as File).name);
    try {
      const response = await fetch(`${API_BASE}/ui/review-upload/${encodeURIComponent(currentReviewId)}`, {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const payload = await response.text();
        throw new Error(payload || 'Не удалось загрузить файл');
      }
      options.onSuccess?.({}, options.file as never);
      message.success(`Файл ${(options.file as File).name} загружен для ревью`);
      await loadReviewState(currentReviewId);
    } catch (error) {
      options.onError?.(error as Error);
      message.error(error instanceof Error ? error.message : 'Не удалось загрузить файл');
    }
  }

  async function runReview() {
    if (!currentReviewId) {
      message.error('Сначала укажи Review ID');
      return;
    }
    const targetModel = reviewModel || reviewModelOptions[0];
    if (!targetModel) {
      message.error('Нет доступной модели для ревью');
      return;
    }
    await withBusy('review', async () => {
      await apiRequest('/review-analytics', {
        method: 'POST',
        body: JSON.stringify({
          review_id: currentReviewId,
          document_type: documentType,
          model: targetModel,
        }),
      });
    }, `Ревью аналитики завершено моделью ${targetModel}`);
  }

  function renderFileList(kind: string, items: FileMeta[], emptyText: string) {
    return (
      <List
        dataSource={items}
        locale={{ emptyText }}
        renderItem={(item) => (
          <List.Item>
            <a href={artifactUrl(kind, currentReviewId, item.name)} target="_blank" rel="noreferrer">
              {item.name}
            </a>
          </List.Item>
        )}
      />
    );
  }

  return (
    <PageContainer
      title="Ревью аналитики"
      subTitle="Здесь можно дать ссылку на статью или загрузить файл, а система проверит материал на соответствие шаблону, противоречия, недоработки и рекомендации."
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {!environment?.readiness.models_ready ? (
          <Alert
            type="warning"
            showIcon
            message="Сначала скачай обязательные модели"
            description="Для ревью нужна хотя бы одна готовая review-модель. Проверь раздел «Модели и контекст»."
          />
        ) : null}

        <ProCard title="Шаг 1. Что именно ревьюим" bordered>
          <Typography.Paragraph>
            `Review ID` создаёт отдельную папку для ревью. В ней будут храниться исходные статьи и итоговые отчёты ревью.
          </Typography.Paragraph>
          <Input
            value={reviewId}
            onChange={(event) => setReviewId(event.target.value)}
            placeholder="Например, article-review-billing-ft"
          />
        </ProCard>

        <ProCard title="Шаг 2. Источник статьи: ссылка или файл" bordered>
          <Segmented<SourceMode>
            block
            options={[
              { label: 'Ссылка Confluence', value: 'links' },
              { label: 'Локальный файл', value: 'files' },
            ]}
            value={sourceMode}
            onChange={(value) => setSourceMode(value as SourceMode)}
          />

          <Space direction="vertical" size={16} style={{ width: '100%', marginTop: 16 }}>
            {sourceMode === 'links' ? (
              <ProCard type="inner" title="2.1 Импорт статьи по ссылке">
                <Typography.Paragraph type="secondary">
                  Система возьмёт доступы к Confluence из «Подготовки окружения», заберёт статью и сохранит её локально как источник ревью.
                </Typography.Paragraph>
                <Input.TextArea
                  rows={6}
                  value={confluenceUrls}
                  onChange={(event) => setConfluenceUrls(event.target.value)}
                  placeholder={environment?.settings.confluence_base_url
                    ? `${environment.settings.confluence_base_url}/...`
                    : 'Вставь ссылки Confluence по одной на строку'}
                />
                <Space style={{ marginTop: 12 }} wrap>
                  <Button type="primary" loading={busy === 'links'} icon={<LinkOutlined />} onClick={() => void importConfluenceLinks()}>
                    Импортировать статью
                  </Button>
                  <Typography.Text type="secondary">
                    Источники ревью сохраняются отдельно и не смешиваются с task attachments.
                  </Typography.Text>
                </Space>
              </ProCard>
            ) : (
              <ProCard type="inner" title="2.2 Загрузка статьи файлом">
                <Typography.Paragraph type="secondary">
                  Поддерживаются `.md`, `.txt`, `.docx`, `.pdf`. После загрузки файл станет локальным источником для ревью.
                </Typography.Paragraph>
                <Upload multiple customRequest={uploadSource} showUploadList={false}>
                  <Button icon={<UploadOutlined />}>Загрузить файл статьи</Button>
                </Upload>
              </ProCard>
            )}
          </Space>
        </ProCard>

        <ProCard title="Шаг 3. Как именно проверять статью" bordered>
          <Typography.Paragraph>
            `Auto` сам определяет, это FT или NFT. Если ты уже точно знаешь тип документа, можно указать его вручную.
          </Typography.Paragraph>
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Select
              value={documentType}
              onChange={(value) => setDocumentType(value)}
              options={[
                { label: 'Auto', value: 'auto' },
                { label: 'FT — функциональные требования', value: 'ft' },
                { label: 'NFT — нефункциональные требования', value: 'nft' },
              ]}
            />
            <Select
              value={reviewModel || undefined}
              onChange={(value) => setReviewModel(value)}
              options={reviewModelOptions.map((item) => ({ label: item, value: item }))}
              placeholder="Выбери модель для ревью"
            />
            <Alert
              type="info"
              showIcon
              message="Что проверяет ревью аналитики"
              description="Система смотрит на соответствие шаблону FT/NFT, на внутренние противоречия, на слабые или пустые разделы, на недосказанности и в конце даёт список рекомендаций по доработке."
            />
            <Button
              type="primary"
              icon={<SearchOutlined />}
              loading={busy === 'review'}
              onClick={() => void runReview()}
              disabled={!reviewModelOptions.length}
            >
              Запустить ревью аналитики
            </Button>
          </Space>
        </ProCard>

        <ProCard title="Результат ревью" bordered>
          <Tabs
            items={[
              {
                key: 'status',
                label: 'Сводка',
                children: (
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <Descriptions column={1} bordered size="small">
                      <Descriptions.Item label="Последний тип документа">
                        {reviewState?.latest_meta?.document_type || 'Пока не определён'}
                      </Descriptions.Item>
                      <Descriptions.Item label="Последняя модель ревью">
                        {reviewState?.latest_meta?.model || 'Пока не запускалось'}
                      </Descriptions.Item>
                      <Descriptions.Item label="Источников подключено">
                        {reviewState?.sources?.length || 0}
                      </Descriptions.Item>
                    </Descriptions>
                    <Typography.Paragraph>
                      <Typography.Text strong>Preview отчёта:</Typography.Text>
                      <br />
                      {reviewState?.latest_preview || 'Пока нет отчёта ревью'}
                    </Typography.Paragraph>
                  </Space>
                ),
              },
              {
                key: 'sources',
                label: 'Источники',
                children: renderFileList('review_sources', reviewState?.sources || [], 'Источники ревью пока не загружены'),
              },
              {
                key: 'reports',
                label: 'Отчёты',
                children: renderFileList('analytics_reviews', reviewState?.artifacts || [], 'Отчёты ревью пока не созданы'),
              },
            ]}
          />
        </ProCard>
      </Space>
    </PageContainer>
  );
}
