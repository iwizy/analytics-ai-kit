import React, { useEffect, useMemo, useState } from 'react';
import { CheckCircleOutlined, CloudDownloadOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import { Alert, Button, List, Space, Table, Tag, Typography, message } from 'antd';

import { apiRequest } from '@/utils/api';
import type { EnvironmentSnapshot } from '@/utils/environment';

type ModelPullItem = {
  status?: string;
  message?: string;
  completed?: number;
  total?: number;
  error?: string;
};

type OperationsPayload = {
  docker: {
    available: boolean;
    error?: string;
  };
  containers: Record<string, {
    state?: string;
    status?: string;
    health?: string;
    error?: string;
  }>;
  services: Record<string, {
    status?: string;
    description?: string;
    detail?: string;
  }>;
  models: {
    required: string[];
    installed: string[];
    ready_required: string[];
    missing: string[];
    error?: string;
  };
  model_pull: {
    status?: string;
    message?: string;
    models?: Record<string, ModelPullItem>;
  };
};

function renderModelStatus(model: string, operations: OperationsPayload | null) {
  const ready = new Set(operations?.models?.ready_required || []);
  const modelPull = operations?.model_pull?.models?.[model];
  if (ready.has(model)) {
    return <Tag color="success">Готово</Tag>;
  }
  if (modelPull?.status === 'failed') {
    return <Tag color="error">Ошибка загрузки</Tag>;
  }
  if (modelPull?.status && modelPull.status !== 'idle' && modelPull.status !== 'done') {
    return <Tag color="processing">Скачивается</Tag>;
  }
  return <Tag color="default">Не скачано</Tag>;
}

export default function ModelsDocsPage() {
  const [environment, setEnvironment] = useState<EnvironmentSnapshot | null>(null);
  const [operations, setOperations] = useState<OperationsPayload | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  async function refreshAll() {
    const [environmentPayload, operationsPayload] = await Promise.all([
      apiRequest<EnvironmentSnapshot>('/ui/environment-settings'),
      apiRequest<{ operations: OperationsPayload }>('/ui/ops/status'),
    ]);
    setEnvironment(environmentPayload);
    setOperations(operationsPayload.operations);
  }

  useEffect(() => {
    void refreshAll();
  }, []);

  const missingModels = useMemo(() => operations?.models?.missing || [], [operations]);

  async function controlContainers(action: 'start' | 'restart' | 'stop') {
    setBusyAction(action);
    try {
      await apiRequest(`/ui/ops/containers/${action}`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      message.success(`Команда ${action} отправлена`);
      await refreshAll();
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Не удалось отправить команду контейнерам');
    } finally {
      setBusyAction(null);
    }
  }

  async function pullMissingModels() {
    setBusyAction('models');
    try {
      await apiRequest('/ui/ops/models/pull', {
        method: 'POST',
        body: JSON.stringify({}),
      });
      message.success('Загрузка моделей запущена');
      await refreshAll();
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Не удалось запустить загрузку моделей');
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <PageContainer
      title="Модели и контекст"
      subTitle="Здесь живёт вся техническая готовность: Docker, контейнеры, модели, доступность сервисов и сводка того, что ещё мешает перейти к статье."
      extra={[
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => void refreshAll()}>
          Обновить
        </Button>,
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {environment ? (
          <Alert
            type={environment.readiness.all_ready ? 'success' : 'warning'}
            showIcon
            message={environment.readiness.all_ready ? 'Все обязательные проверки пройдены' : 'Есть незавершённая подготовка'}
            description={environment.readiness.all_ready
              ? 'Красный индикатор в меню должен исчезнуть, и раздел статьи станет доступен.'
              : environment.readiness.missing_items.join(' | ')}
          />
        ) : (
          <Alert type="info" showIcon message="Сводка готовности загружается" />
        )}

        <ProCard gutter={16} wrap>
          <ProCard colSpan={{ xs: 24, xl: 11 }} title="Сводка по готовности" bordered>
            <List
              bordered
              dataSource={environment?.readiness.missing_items?.length ? environment.readiness.missing_items : ['Все обязательные шаги уже выполнены']}
              renderItem={(item) => (
                <List.Item>
                  <Space>
                    {environment?.readiness.all_ready ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <StopOutlined style={{ color: '#ff4d4f' }} />}
                    <span>{item}</span>
                  </Space>
                </List.Item>
              )}
            />
            <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>
              Остановка локального стека по-прежнему делается через `./stop.command`. Здесь мы только даём обзор и кнопки на базовые docker-операции.
            </Typography.Paragraph>
          </ProCard>

          <ProCard colSpan={{ xs: 24, xl: 13 }} title="Модели" bordered extra={
            <Space>
              <Button
                type="primary"
                icon={<CloudDownloadOutlined />}
                loading={busyAction === 'models'}
                onClick={() => void pullMissingModels()}
                disabled={!missingModels.length}
              >
                Скачать недостающие
              </Button>
            </Space>
          }>
            <Typography.Paragraph>
              Обязательные модели проверяются автоматически. Пока хотя бы одна из них не готова, пункт «Подготовка статьи» останется заблокированным, а в меню у «Модели и контекст» будет красный индикатор.
            </Typography.Paragraph>
            <List
              dataSource={operations?.models?.required || []}
              renderItem={(model) => {
                const pullState = operations?.model_pull?.models?.[model];
                const progress = pullState?.total ? `${pullState.completed || 0}/${pullState.total}` : null;
                return (
                  <List.Item>
                    <Space direction="vertical" size={2} style={{ width: '100%' }}>
                      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                        <Typography.Text strong>{model}</Typography.Text>
                        {renderModelStatus(model, operations)}
                      </Space>
                      <Typography.Text type="secondary">
                        {pullState?.error || pullState?.message || (missingModels.includes(model) ? 'Модель ещё не скачана' : 'Модель готова к работе')}
                      </Typography.Text>
                      {progress ? <Typography.Text type="secondary">Прогресс: {progress}</Typography.Text> : null}
                    </Space>
                  </List.Item>
                );
              }}
            />
          </ProCard>
        </ProCard>

        <ProCard gutter={16} wrap>
          <ProCard colSpan={{ xs: 24, xl: 10 }} title="Docker и контейнеры" bordered extra={
            <Space>
              <Button loading={busyAction === 'start'} onClick={() => void controlContainers('start')}>Старт</Button>
              <Button loading={busyAction === 'restart'} onClick={() => void controlContainers('restart')}>Рестарт</Button>
              <Button danger loading={busyAction === 'stop'} onClick={() => void controlContainers('stop')}>Стоп</Button>
            </Space>
          }>
            <Alert
              type={operations?.docker?.available ? 'success' : 'error'}
              showIcon
              message={operations?.docker?.available ? 'Docker доступен' : 'Docker недоступен'}
              description={operations?.docker?.error || 'Контейнеры и health-check статусы читаются прямо из локального стека.'}
            />
            <Table
              rowKey={(row: { name: string }) => row.name}
              style={{ marginTop: 16 }}
              pagination={false}
              dataSource={Object.entries(operations?.containers || {}).map(([name, value]) => ({ name, ...value }))}
              columns={[
                { title: 'Контейнер', dataIndex: 'name', key: 'name' },
                { title: 'Состояние', dataIndex: 'state', key: 'state', render: (value: string | undefined) => <Tag>{value || 'unknown'}</Tag> },
                { title: 'Health', dataIndex: 'health', key: 'health', render: (value: string | undefined) => value || 'n/a' },
              ]}
            />
          </ProCard>

          <ProCard colSpan={{ xs: 24, xl: 14 }} title="Статусы сервисов" bordered>
            <Table
              rowKey={(row: { name: string }) => row.name}
              pagination={false}
              dataSource={Object.entries(operations?.services || {}).map(([name, value]) => ({ name, ...value }))}
              columns={[
                { title: 'Сервис', dataIndex: 'name', key: 'name' },
                { title: 'Статус', dataIndex: 'status', key: 'status', render: (value: string | undefined) => <Tag color={value === 'ok' ? 'success' : 'default'}>{value || 'unknown'}</Tag> },
                { title: 'Описание', dataIndex: 'description', key: 'description' },
                { title: 'Детали', dataIndex: 'detail', key: 'detail', render: (value: string | undefined) => value || '—' },
              ]}
            />
          </ProCard>
        </ProCard>
      </Space>
    </PageContainer>
  );
}
