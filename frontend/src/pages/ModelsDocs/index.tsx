import {
  CloudDownloadOutlined,
  PlayCircleOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  RetweetOutlined,
} from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import { Alert, App, Button, Collapse, List, Progress, Space, Spin, Tag, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';

type ModelPullEntry = {
  status: string;
  message: string;
  progress?: number | null;
  error?: string | null;
};

type ServiceProbe = {
  ok: boolean;
  status_code?: number | null;
  error?: string | null;
};

type ContainerState = {
  container_name: string;
  running: boolean;
  exists: boolean;
  state: string;
  error?: string | null;
};

type OperationsPayload = {
  docker: {
    available: boolean;
    error?: string | null;
  };
  services: Record<string, ServiceProbe>;
  containers: Record<string, ContainerState>;
  models: {
    required: string[];
    ready_required: string[];
    missing: string[];
    error?: string | null;
  };
  model_pull: {
    running: boolean;
    status: string;
    requested_models: string[];
    per_model: Record<string, ModelPullEntry>;
    logs: string[];
  };
};

const API_BASE = process.env.UMI_APP_API_BASE_URL || '';

async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail =
      typeof payload === 'object' && payload
        ? (payload as { detail?: string }).detail || JSON.stringify(payload)
        : String(payload);
    throw new Error(detail || `HTTP ${response.status}`);
  }

  return payload as T;
}

function modelStatusColor(status: string) {
  if (status === 'failed' || status === 'interrupted') return 'red';
  if (status === 'done' || status === 'skipped' || status === 'ready') return 'green';
  if (status === 'starting') return 'gold';
  return 'blue';
}

function probeColor(ok: boolean) {
  return ok ? 'green' : 'red';
}

export default function ModelsDocsPage() {
  const { message } = App.useApp();
  const [opsState, setOpsState] = useState<OperationsPayload | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const readyModels = new Set(opsState?.models?.ready_required || []);
  const modelPull = opsState?.model_pull;
  const models = opsState?.models;

  const downloadProgress = useMemo(() => {
    const requested = modelPull?.requested_models || models?.required || [];
    if (requested.length === 0) {
      return 0;
    }

    const total = requested.reduce((sum, model) => {
      if (readyModels.has(model)) {
        return sum + 1;
      }
      const entry = modelPull?.per_model?.[model];
      if (entry?.progress !== undefined && entry?.progress !== null) {
        return sum + entry.progress;
      }
      return sum;
    }, 0);

    return Math.round((total / requested.length) * 100);
  }, [modelPull?.per_model, modelPull?.requested_models, models?.required, readyModels]);

  useEffect(() => {
    void refreshOps();
  }, []);

  useEffect(() => {
    if (!modelPull?.running) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      void refreshOps();
    }, 2000);

    return () => window.clearInterval(timer);
  }, [modelPull?.running]);

  async function withBusy<T>(key: string, action: () => Promise<T>) {
    setBusyKey(key);
    try {
      return await action();
    } finally {
      setBusyKey(null);
    }
  }

  async function refreshOps() {
    const payload = await apiRequest<{ operations: OperationsPayload }>('/ui/ops/status');
    setOpsState(payload.operations);
  }

  async function runContainerAction(action: 'start' | 'restart' | 'stop') {
    await withBusy(`containers-${action}`, async () => {
      await apiRequest(`/ui/ops/containers/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      message.success(`Команда '${action}' отправлена`);
      await refreshOps();
    });
  }

  async function downloadMissingModels() {
    await withBusy('downloadModels', async () => {
      await apiRequest('/ui/ops/models/pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      message.success('Загрузка моделей запущена');
      await refreshOps();
    });
  }

  return (
    <PageContainer
      title="Модели и контекст"
      content="Здесь видно, готова ли инфраструктура к работе: контейнеры, API, модели и лог загрузки. Если чего-то не хватает, именно на этом экране это удобно исправить."
      extra={[
        <Button key="refreshOps" icon={<ReloadOutlined />} onClick={() => void refreshOps()}>
          Обновить статус
        </Button>,
      ]}
    >
      {!opsState ? (
        <Spin />
      ) : (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Alert
            showIcon
            type="info"
            message="Что означает этот экран"
            description="Перед началом работы аналитик может зайти сюда и убедиться, что Docker доступен, контейнеры запущены, а обязательные модели скачаны. Если модели не готовы, генерация статьи на шаге 'Подготовка статьи' будет заблокирована."
          />

          <ProCard split="vertical" gutter={16}>
            <ProCard colSpan="45%" title="Инфраструктура">
              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                <Alert
                  showIcon
                  type={opsState.docker.available ? 'success' : 'error'}
                  message={opsState.docker.available ? 'Docker доступен' : 'Docker недоступен'}
                  description={opsState.docker.error || 'Контейнеры можно запускать и останавливать прямо из интерфейса.'}
                />

                <Typography.Text type="secondary">
                  Если сервисы не отвечают, используйте кнопки ниже. Обычно достаточно «Запустить стек» или «Перезапустить стек».
                </Typography.Text>

                <Space wrap>
                  <Button
                    icon={<PlayCircleOutlined />}
                    loading={busyKey === 'containers-start'}
                    onClick={() => void runContainerAction('start')}
                  >
                    Запустить стек
                  </Button>
                  <Button
                    icon={<RetweetOutlined />}
                    loading={busyKey === 'containers-restart'}
                    onClick={() => void runContainerAction('restart')}
                  >
                    Перезапустить стек
                  </Button>
                  <Button
                    icon={<PoweroffOutlined />}
                    loading={busyKey === 'containers-stop'}
                    onClick={() => void runContainerAction('stop')}
                  >
                    Остановить стек
                  </Button>
                </Space>

                <List
                  size="small"
                  header="Контейнеры"
                  dataSource={Object.entries(opsState.containers)}
                  renderItem={([name, state]) => (
                    <List.Item>
                      <Space direction="vertical" style={{ width: '100%' }} size={2}>
                        <Space>
                          <Typography.Text strong>{name}</Typography.Text>
                          <Tag color={state.running ? 'green' : 'default'}>
                            {state.running ? 'running' : state.state}
                          </Tag>
                        </Space>
                        <Typography.Text type="secondary">
                          {state.container_name}
                          {state.error ? ` • ${state.error}` : ''}
                        </Typography.Text>
                      </Space>
                    </List.Item>
                  )}
                />
              </Space>
            </ProCard>

            <ProCard colSpan="55%" title="Модели">
              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                <Typography.Text type="secondary">
                  Обязательные модели нужны для генерации draft, gap-analysis и refine. Если какой-то модели нет, нажмите кнопку ниже и дождитесь завершения загрузки.
                </Typography.Text>

                <Button
                  type="primary"
                  icon={<CloudDownloadOutlined />}
                  loading={busyKey === 'downloadModels' || Boolean(modelPull?.running)}
                  onClick={() => void downloadMissingModels()}
                >
                  Скачать недостающие модели
                </Button>

                <Progress
                  percent={downloadProgress}
                  status={modelPull?.status === 'failed' ? 'exception' : undefined}
                />

                <List
                  size="small"
                  header="Обязательные модели"
                  dataSource={models?.required || []}
                  renderItem={(item) => {
                    const entry = modelPull?.per_model?.[item];
                    const progress =
                      entry?.progress !== undefined && entry?.progress !== null
                        ? Math.round(entry.progress * 100)
                        : readyModels.has(item)
                          ? 100
                          : 0;
                    const status = entry?.status || (readyModels.has(item) ? 'ready' : 'missing');

                    return (
                      <List.Item>
                        <Space direction="vertical" style={{ width: '100%' }} size={4}>
                          <Space>
                            <Typography.Text strong>{item}</Typography.Text>
                            <Tag color={readyModels.has(item) ? 'green' : modelStatusColor(status)}>
                              {status}
                            </Tag>
                          </Space>
                          <Progress percent={progress} size="small" showInfo={false} />
                          {entry?.error && <Typography.Text type="danger">{entry.error}</Typography.Text>}
                        </Space>
                      </List.Item>
                    );
                  }}
                />
              </Space>
            </ProCard>
          </ProCard>

          <ProCard title="Проверка сервисов и правила хранения контекста">
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Typography.Text>
                Что хранится где:
              </Typography.Text>
              <Typography.Text type="secondary">
                `task.md` и загруженные документы складываются в `tasks/inbox/&lt;task-id&gt;/`, артефакты генерации попадают в `artifacts/`, а handoff для Continue создаётся отдельно, чтобы аналитик мог продолжить работу в VS Code без риска перетереть системный результат.
              </Typography.Text>

              <List
                size="small"
                header="Health checks"
                dataSource={Object.entries(opsState.services)}
                renderItem={([name, state]) => (
                  <List.Item>
                    <Space>
                      <Typography.Text strong>{name}</Typography.Text>
                      <Tag color={probeColor(state.ok)}>{state.ok ? 'ok' : 'fail'}</Tag>
                      <Typography.Text type="secondary">
                        {state.status_code ? `HTTP ${state.status_code}` : 'no http'}
                        {state.error ? ` • ${state.error}` : ''}
                      </Typography.Text>
                    </Space>
                  </List.Item>
                )}
              />

              <Collapse
                items={[
                  {
                    key: 'model-log',
                    label: 'Лог загрузки моделей',
                    children: (
                      <pre className="analytics-json">
                        {(modelPull?.logs || []).join('\n') || 'Пока пусто'}
                      </pre>
                    ),
                  },
                ]}
              />
            </Space>
          </ProCard>
        </Space>
      )}
    </PageContainer>
  );
}
