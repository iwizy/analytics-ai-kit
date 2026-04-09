import {
  CloudDownloadOutlined,
  FileAddOutlined,
  LinkOutlined,
  PlayCircleOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  RetweetOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import { PageContainer, ProCard, ProDescriptions } from '@ant-design/pro-components';
import {
  Alert,
  App,
  Button,
  Checkbox,
  Collapse,
  Input,
  List,
  Progress,
  Segmented,
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
} from 'antd';
import type { UploadFile, UploadProps } from 'antd/es/upload/interface';
import { useEffect, useMemo, useState } from 'react';

type SourceMode = 'files' | 'links' | 'mixed';

type FileMeta = {
  name: string;
  size_bytes: number;
  modified_at: string;
};

type AnalysisPayload = {
  document_type: string;
  sections: string[];
  service?: string | null;
  attachments_count?: number;
};

type ArtifactState = {
  drafts: FileMeta[];
  reviews: FileMeta[];
  context_packs: FileMeta[];
  pipeline_runs: FileMeta[];
  handoffs: FileMeta[];
};

type PipelineStage = {
  name: string;
  state: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  details?: Record<string, unknown>;
};

type PipelineSnapshot = {
  run_id: string;
  state: string;
  started_at?: string | null;
  finished_at?: string | null;
  stages?: PipelineStage[];
  result?: Record<string, unknown>;
  errors?: string[];
};

type TaskState = {
  task_text: string;
  attachments: FileMeta[];
  analysis?: AnalysisPayload | null;
  analysis_error?: string | null;
  artifacts: ArtifactState;
  latest_pipeline?: PipelineSnapshot | null;
  latest: {
    draft_preview: string;
    gaps_preview: string;
    handoff_preview: string;
  };
};

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
const TERMINAL_PIPELINE_STATES = new Set(['completed', 'failed', 'interrupted']);

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

function bytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
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

function pipelineStateColor(state: string) {
  if (state === 'completed') return 'green';
  if (state === 'failed' || state === 'interrupted') return 'red';
  if (state === 'running') return 'blue';
  return 'default';
}

function artifactUrl(kind: string, taskId: string, filename: string) {
  return `${API_BASE}/ui/artifacts/${encodeURIComponent(kind)}/${encodeURIComponent(taskId)}/${encodeURIComponent(filename)}`;
}

export default function WorkbenchPage() {
  const { message } = App.useApp();
  const [taskId, setTaskId] = useState('');
  const [taskText, setTaskText] = useState('');
  const [docType, setDocType] = useState('auto');
  const [pipelineType, setPipelineType] = useState('auto');
  const [refineInstructions, setRefineInstructions] = useState('');
  const [runGaps, setRunGaps] = useState(true);
  const [runRefine, setRunRefine] = useState(false);
  const [sourceMode, setSourceMode] = useState<SourceMode>('mixed');
  const [analystId, setAnalystId] = useState('');
  const [analystLogin, setAnalystLogin] = useState('');
  const [analystPassword, setAnalystPassword] = useState('');
  const [confluenceUrls, setConfluenceUrls] = useState('');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [taskState, setTaskState] = useState<TaskState | null>(null);
  const [opsState, setOpsState] = useState<OperationsPayload | null>(null);
  const [pipelineState, setPipelineState] = useState<PipelineSnapshot | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const currentTaskId = taskId.trim();
  const models = opsState?.models;
  const modelPull = opsState?.model_pull;
  const readyModels = new Set(models?.ready_required || []);
  const missingModels = models?.missing || [];
  const modelsReady = Boolean(models) && missingModels.length === 0 && !models?.error;
  const actionDisabled = !currentTaskId || !modelsReady;

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
    void loadTemplate();
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

  useEffect(() => {
    if (!activeRunId || !currentTaskId) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      void pollPipeline(currentTaskId, activeRunId);
    }, 1500);

    return () => window.clearInterval(timer);
  }, [activeRunId, currentTaskId]);

  const uploadProps: UploadProps = {
    multiple: true,
    beforeUpload: () => false,
    fileList,
    onChange: ({ fileList: nextFileList }) => setFileList(nextFileList),
  };

  async function withBusy<T>(key: string, action: () => Promise<T>) {
    setBusyKey(key);
    try {
      return await action();
    } finally {
      setBusyKey(null);
    }
  }

  async function loadTemplate() {
    const payload = await apiRequest<{ template: string }>('/ui/task-template');
    setTaskText((current) => current || payload.template || '');
  }

  async function refreshOps() {
    const payload = await apiRequest<{ operations: OperationsPayload }>('/ui/ops/status');
    setOpsState(payload.operations);
  }

  async function refreshTaskState() {
    if (!currentTaskId) {
      message.warning('Укажите Task ID');
      return;
    }

    const payload = await apiRequest<TaskState>(`/ui/state/${encodeURIComponent(currentTaskId)}`);
    setTaskState(payload);
    setTaskText((current) => current || payload.task_text || '');

    if (payload.latest_pipeline) {
      setPipelineState(payload.latest_pipeline);
      if (payload.latest_pipeline.state === 'running') {
        setActiveRunId(payload.latest_pipeline.run_id);
      } else if (!activeRunId || activeRunId === payload.latest_pipeline.run_id) {
        setActiveRunId(null);
      }
    }
  }

  async function saveTask() {
    if (!currentTaskId) {
      message.warning('Укажите Task ID');
      return;
    }

    await withBusy('saveTask', async () => {
      await apiRequest('/ui/create-task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: currentTaskId,
          task_text: taskText,
        }),
      });
      message.success('task.md сохранен');
      await refreshTaskState();
    });
  }

  async function saveAnalystProfile() {
    if (!analystId.trim() || !analystLogin.trim() || !analystPassword.trim()) {
      message.warning('Заполните профиль аналитика, логин и пароль');
      return;
    }

    await withBusy('saveAnalyst', async () => {
      await apiRequest('/ui/analyst-profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          analyst_id: analystId.trim(),
          login: analystLogin.trim(),
          password: analystPassword,
        }),
      });
      setAnalystPassword('');
      message.success('Профиль аналитика сохранен');
    });
  }

  async function importConfluence() {
    if (!currentTaskId) {
      message.warning('Сначала укажите Task ID');
      return;
    }
    if (!analystId.trim()) {
      message.warning('Укажите профиль аналитика');
      return;
    }

    const urls = confluenceUrls
      .split(/\n|,/)
      .map((item) => item.trim())
      .filter(Boolean);

    if (urls.length === 0) {
      message.warning('Добавьте хотя бы одну ссылку Confluence');
      return;
    }

    await withBusy('importConfluence', async () => {
      const payload = await apiRequest<{ imported: Array<unknown>; failed: Array<unknown> }>(
        '/ui/import-confluence',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task_id: currentTaskId,
            analyst_id: analystId.trim(),
            urls,
          }),
        },
      );
      setConfluenceUrls('');
      message.success(`Импортировано страниц: ${payload.imported.length}`);
      if (payload.failed.length > 0) {
        message.warning(`Не удалось импортировать страниц: ${payload.failed.length}`);
      }
      await refreshTaskState();
    });
  }

  async function uploadAttachments() {
    if (!currentTaskId) {
      message.warning('Сначала укажите Task ID');
      return;
    }
    if (fileList.length === 0) {
      message.warning('Добавьте хотя бы один файл');
      return;
    }

    await withBusy('uploadFiles', async () => {
      const formData = new FormData();
      fileList.forEach((file) => {
        if (file.originFileObj) {
          formData.append('files', file.originFileObj);
        }
      });

      await apiRequest(`/ui/upload-attachments/${encodeURIComponent(currentTaskId)}`, {
        method: 'POST',
        body: formData,
      });
      setFileList([]);
      message.success('Вложения загружены');
      await refreshTaskState();
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

  async function runContainerAction(action: 'start' | 'restart' | 'stop') {
    await withBusy(`containers-${action}`, async () => {
      const payload = await apiRequest<{ operation: { results: Array<{ ok: boolean }> } }>(
        `/ui/ops/containers/${action}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        },
      );
      const results = payload.operation.results || [];
      const okCount = results.filter((item) => item.ok).length;
      message.success(`Операция '${action}' завершена: ${okCount}/${results.length} ok`);
      await refreshOps();
    });
  }

  async function runAction(path: string, payload: Record<string, unknown>, successMessage: string) {
    await apiRequest(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    message.success(successMessage);
    await refreshTaskState();
  }

  async function analyzeTask() {
    if (actionDisabled) {
      return;
    }

    await withBusy('analyze', async () => {
      await apiRequest<{ analysis: AnalysisPayload }>('/analyze-task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: currentTaskId }),
      });
      message.success('Analyze выполнен');
      await refreshTaskState();
    });
  }

  async function createDraft() {
    if (actionDisabled) {
      return;
    }

    await withBusy('draft', async () => {
      await runAction(
        '/draft',
        {
          task_id: currentTaskId,
          ...(docType !== 'auto' ? { force_document_type: docType } : {}),
        },
        'Черновик создан',
      );
    });
  }

  async function runGapAnalysis() {
    if (actionDisabled) {
      return;
    }

    await withBusy('gap', async () => {
      await runAction('/gap-analysis', { task_id: currentTaskId }, 'Gap analysis готов');
    });
  }

  async function runRefineAction() {
    if (actionDisabled) {
      return;
    }

    await withBusy('refine', async () => {
      await runAction(
        '/refine',
        {
          task_id: currentTaskId,
          instructions: refineInstructions || 'Уточни формулировки и убери неоднозначности',
        },
        'Refine завершен',
      );
    });
  }

  async function runPipeline() {
    if (actionDisabled) {
      return;
    }

    await withBusy('pipeline', async () => {
      const payload = await apiRequest<{ pipeline: PipelineSnapshot }>('/run-pipeline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: currentTaskId,
          run_gaps: runGaps,
          run_refine: runRefine,
          async_mode: true,
          ...(pipelineType !== 'auto' ? { force_document_type: pipelineType } : {}),
          ...(refineInstructions ? { refine_instructions: refineInstructions } : {}),
        }),
      });

      setPipelineState(payload.pipeline);
      setActiveRunId(payload.pipeline.run_id || null);
      message.success('Pipeline запущен');
    });
  }

  async function prepareHandoff() {
    if (!currentTaskId) {
      message.warning('Сначала укажите Task ID');
      return;
    }

    await withBusy('handoff', async () => {
      const payload = await apiRequest<{ handoff: { handoff_path: string; working_copy_path?: string | null } }>(
        '/prepare-handoff',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task_id: currentTaskId,
            notes: 'Handoff подготовлен из UI для продолжения работы в VS Code + Continue.',
          }),
        },
      );

      message.success(
        payload.handoff.working_copy_path
          ? 'Handoff и рабочая копия для Continue подготовлены'
          : 'Handoff для Continue подготовлен',
      );
      await refreshTaskState();
    });
  }

  async function pollPipeline(id: string, runId: string) {
    const payload = await apiRequest<{ pipeline: PipelineSnapshot }>(
      `/pipeline-status/${encodeURIComponent(id)}/${encodeURIComponent(runId)}`,
    );
    setPipelineState(payload.pipeline);

    if (TERMINAL_PIPELINE_STATES.has(payload.pipeline.state)) {
      setActiveRunId(null);
      await refreshTaskState();
    }
  }

  function renderArtifactList(kind: keyof ArtifactState, title: string, items: FileMeta[]) {
    return {
      key: kind,
      label: `${title} (${items.length})`,
      children: (
        <List
          dataSource={items}
          locale={{ emptyText: `Нет артефактов: ${title}` }}
          renderItem={(item) => (
            <List.Item
              actions={[
                <a
                  key={`${kind}-${item.name}`}
                  href={artifactUrl(kind, currentTaskId, item.name)}
                  target="_blank"
                  rel="noreferrer"
                >
                  Открыть
                </a>,
              ]}
            >
              <List.Item.Meta
                title={item.name}
                description={`${bytes(item.size_bytes)} • ${item.modified_at}`}
              />
            </List.Item>
          )}
        />
      ),
    };
  }

  return (
    <PageContainer
      className="analytics-shell"
      title="Подготовка статьи"
      content="Здесь аналитик пошагово собирает задачу, добавляет контекст, запускает генерацию и подготавливает handoff для работы в VS Code + Continue."
      extra={[
        <Button key="refreshOps" icon={<ReloadOutlined />} onClick={() => void refreshOps()}>
          Обновить статусы
        </Button>,
        <Button
          key="refreshTask"
          type="primary"
          icon={<ReloadOutlined />}
          onClick={() => void refreshTaskState()}
        >
          Обновить задачу
        </Button>,
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          showIcon
          type="info"
          message="Как пользоваться экраном"
          description="Шаг 1: задайте Task ID и сохраните task.md. Шаг 2: добавьте файлы, ссылки Confluence или оба источника сразу. Шаг 3: запустите Analyze, Draft, Gaps или полный pipeline. Шаг 4: подготовьте handoff и продолжайте работу в VS Code + Continue."
        />

        {!modelsReady && (
          <Alert
            showIcon
            type="warning"
            message="Не все модели готовы к работе"
            description={
              <Space direction="vertical" style={{ width: '100%' }}>
                <Typography.Text>
                  Генерация будет доступна после загрузки обязательных моделей.
                </Typography.Text>
                <Button
                  type="primary"
                  icon={<CloudDownloadOutlined />}
                  loading={busyKey === 'downloadModels' || Boolean(modelPull?.running)}
                  onClick={() => void downloadMissingModels()}
                >
                  Скачать недостающие модели
                </Button>
              </Space>
            }
          />
        )}

        <ProCard className="analytics-panel" split="vertical" gutter={16}>
          <ProCard colSpan="58%" title="Шаг 1. Описание задачи">
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Typography.Text type="secondary">
                `Task ID` станет именем рабочей папки задачи. По нему система создаст путь `tasks/inbox/&lt;task-id&gt;/`, будет искать вложения и сохранять артефакты генерации.
              </Typography.Text>
              <Input
                size="large"
                placeholder="Например: operation-history-ft-v1"
                value={taskId}
                onChange={(event) => setTaskId(event.target.value)}
              />
              <Typography.Text type="secondary">
                В `task.md` кратко опишите, что именно нужно подготовить, какой контекст уже известен, какие есть ограничения и как понять, что документ готов.
              </Typography.Text>
              <Input.TextArea
                rows={10}
                placeholder="Опишите цель статьи, контекст, ограничения и критерий готовности"
                value={taskText}
                onChange={(event) => setTaskText(event.target.value)}
              />
              <Space wrap>
                <Button
                  icon={<SaveOutlined />}
                  type="primary"
                  loading={busyKey === 'saveTask'}
                  onClick={() => void saveTask()}
                >
                  Сохранить описание задачи
                </Button>
                <Button onClick={() => void loadTemplate()}>Подставить шаблон</Button>
              </Space>
            </Space>
          </ProCard>

          <ProCard colSpan="42%" title="Сводка по готовности">
            {opsState ? (
              <Space direction="vertical" style={{ width: '100%' }} size={14}>
                <Alert
                  showIcon
                  type={opsState.docker.available ? 'success' : 'error'}
                  message={opsState.docker.available ? 'Docker доступен' : 'Docker недоступен'}
                  description={opsState.docker.error || 'Подробное управление контейнерами и моделями вынесено в раздел «Модели и контекст» слева в меню.'}
                />
                <Typography.Text type="secondary">
                  Если здесь виден статус `missing`, сначала скачайте модели в разделе «Модели и контекст», а потом возвращайтесь к генерации статьи.
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

                <Progress
                  percent={downloadProgress}
                  status={modelPull?.status === 'failed' ? 'exception' : undefined}
                />

                <List
                  size="small"
                  header="Required models"
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

                <Collapse
                  items={[
                    {
                      key: 'containers',
                      label: 'Состояние контейнеров',
                      children: (
                        <List
                          size="small"
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
                      ),
                    },
                    {
                      key: 'services',
                      label: 'Service health',
                      children: (
                        <List
                          size="small"
                          dataSource={Object.entries(opsState.services)}
                          renderItem={([name, state]) => (
                            <List.Item>
                              <Space>
                                <Typography.Text strong>{name}</Typography.Text>
                                <Tag color={probeColor(state.ok)}>
                                  {state.ok ? 'ok' : 'fail'}
                                </Tag>
                                <Typography.Text type="secondary">
                                  {state.status_code ? `HTTP ${state.status_code}` : 'no http'}
                                  {state.error ? ` • ${state.error}` : ''}
                                </Typography.Text>
                              </Space>
                            </List.Item>
                          )}
                        />
                      ),
                    },
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
            ) : (
              <Spin />
            )}
          </ProCard>
        </ProCard>

        <ProCard className="analytics-panel" title="Шаг 2. Источники контекста">
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Typography.Text type="secondary">
              Здесь вы выбираете, откуда система возьмёт контекст для статьи: из загруженных файлов, из ссылок Confluence или сразу из обоих источников. После обработки материалы сохраняются локально в папке задачи и участвуют в генерации как обычные документы.
            </Typography.Text>
            <Segmented
              block
              value={sourceMode}
              onChange={(value) => setSourceMode(value as SourceMode)}
              options={[
                { label: 'Файлы', value: 'files' },
                { label: 'Ссылки', value: 'links' },
                { label: 'Оба источника', value: 'mixed' },
              ]}
            />

            {(sourceMode === 'links' || sourceMode === 'mixed') && (
              <ProCard type="inner" title="Ссылки Confluence">
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                  <Typography.Text type="secondary">
                    Профиль аналитика нужен, чтобы Playwright мог зайти в закрытый Confluence от имени конкретного пользователя. Система сохранит профиль отдельно, а страницу превратит в локальный `.md` файл внутри вложений задачи.
                  </Typography.Text>
                  <Space.Compact style={{ width: '100%' }}>
                    <Input
                      placeholder="Профиль аналитика"
                      value={analystId}
                      onChange={(event) => setAnalystId(event.target.value)}
                    />
                    <Input
                      placeholder="Confluence login"
                      value={analystLogin}
                      onChange={(event) => setAnalystLogin(event.target.value)}
                    />
                    <Input.Password
                      placeholder="Confluence password"
                      value={analystPassword}
                      onChange={(event) => setAnalystPassword(event.target.value)}
                    />
                  </Space.Compact>

                  <Button
                    icon={<SaveOutlined />}
                    loading={busyKey === 'saveAnalyst'}
                    onClick={() => void saveAnalystProfile()}
                  >
                    Сохранить профиль доступа
                  </Button>

                  <Input.TextArea
                    rows={5}
                    placeholder="Вставьте одну или несколько ссылок Confluence, по одной на строку"
                    value={confluenceUrls}
                    onChange={(event) => setConfluenceUrls(event.target.value)}
                  />

                  <Button
                    type="primary"
                    icon={<LinkOutlined />}
                    loading={busyKey === 'importConfluence'}
                    onClick={() => void importConfluence()}
                  >
                    Импортировать ссылки в контекст
                  </Button>
                </Space>
              </ProCard>
            )}

            {(sourceMode === 'files' || sourceMode === 'mixed') && (
              <ProCard type="inner" title="Загрузка файлов">
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                  <Typography.Text type="secondary">
                    Загруженные документы копируются в `tasks/inbox/&lt;task-id&gt;/attachments/`. Потом система разбивает их на текстовые фрагменты и использует как контекст для draft, gaps и refine.
                  </Typography.Text>
                  <Upload.Dragger {...uploadProps}>
                    <p className="ant-upload-drag-icon">
                      <FileAddOutlined />
                    </p>
                    <p className="ant-upload-text">Перетащите файлы или выберите их вручную</p>
                    <p className="ant-upload-hint">Поддерживаются `.md`, `.txt`, `.docx`, `.pdf`.</p>
                  </Upload.Dragger>
                  <Button
                    type="primary"
                    icon={<CloudDownloadOutlined />}
                    loading={busyKey === 'uploadFiles'}
                    onClick={() => void uploadAttachments()}
                  >
                    Загрузить файлы в задачу
                  </Button>
                </Space>
              </ProCard>
            )}

            <List
              header="Что уже подключено к задаче"
              locale={{ emptyText: 'Пока нет вложений' }}
              dataSource={taskState?.attachments || []}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={item.name}
                    description={`${bytes(item.size_bytes)} • ${item.modified_at}`}
                  />
                </List.Item>
              )}
            />
          </Space>
        </ProCard>

        <ProCard className="analytics-panel" split="vertical" gutter={16}>
          <ProCard colSpan="48%" title="Шаг 3. Генерация документа">
            <Space direction="vertical" size={14} style={{ width: '100%' }}>
              {!modelsReady && (
                <Alert
                  showIcon
                  type="info"
                  message="Генерация пока заблокирована"
                  description="Сначала загрузите обязательные модели через блок Models & Ops."
                />
              )}

              <Typography.Text type="secondary">
                `Analyze` определяет тип документа и предлагает секции. `Draft` создаёт черновик статьи. `Gaps` ищет пробелы и вопросы. `Refine` — это доработка уже созданного черновика: система перечитывает контекст и переписывает текст аккуратнее, полнее и проверяемее.
              </Typography.Text>

              <Segmented
                value={docType}
                onChange={(value) => setDocType(String(value))}
                options={['auto', 'ft', 'nft']}
              />

              <Input
                placeholder="Например: уточни интеграции, убери двусмысленности, добавь открытые вопросы"
                value={refineInstructions}
                onChange={(event) => setRefineInstructions(event.target.value)}
              />
              <Typography.Text type="secondary">
                Поле выше влияет только на шаг `refine`: сюда можно написать, что именно улучшить в готовом тексте.
              </Typography.Text>

              <Space wrap>
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  disabled={actionDisabled}
                  loading={busyKey === 'analyze'}
                  onClick={() => void analyzeTask()}
                >
                  Проанализировать задачу
                </Button>
                <Button
                  disabled={actionDisabled}
                  loading={busyKey === 'draft'}
                  onClick={() => void createDraft()}
                >
                  Создать черновик
                </Button>
                <Button
                  disabled={actionDisabled}
                  loading={busyKey === 'gap'}
                  onClick={() => void runGapAnalysis()}
                >
                  Найти пробелы
                </Button>
                <Button
                  disabled={actionDisabled}
                  loading={busyKey === 'refine'}
                  onClick={() => void runRefineAction()}
                >
                  Доработать черновик
                </Button>
              </Space>

              <Space wrap>
                <Segmented
                  value={pipelineType}
                  onChange={(value) => setPipelineType(String(value))}
                  options={['auto', 'ft', 'nft']}
                />
                <Checkbox checked={runGaps} onChange={(event) => setRunGaps(event.target.checked)}>
                  После draft сразу запустить поиск пробелов
                </Checkbox>
                <Checkbox checked={runRefine} onChange={(event) => setRunRefine(event.target.checked)}>
                  После draft сразу запустить refine
                </Checkbox>
              </Space>

              <Button
                type="primary"
                ghost
                disabled={actionDisabled}
                loading={busyKey === 'pipeline' || Boolean(activeRunId)}
                onClick={() => void runPipeline()}
              >
                Запустить полный pipeline
              </Button>
              <Button
                loading={busyKey === 'handoff'}
                onClick={() => void prepareHandoff()}
              >
                Подготовить handoff для Continue
              </Button>
              <Typography.Text type="secondary">
                Для Power mode можно открыть проект командой `./power-mode.command {currentTaskId || '<task-id>'}`.
              </Typography.Text>
            </Space>
          </ProCard>

          <ProCard colSpan="52%" title="Шаг 4. Результат и текущее состояние">
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Typography.Text type="secondary">
                Здесь видно, что именно система определила по задаче, на каком этапе находится pipeline и какие стадии уже завершены. Если что-то пошло не так, ошибка тоже появится здесь.
              </Typography.Text>
              {taskState?.analysis ? (
                <ProDescriptions
                  column={1}
                  dataSource={{
                    type: taskState.analysis.document_type,
                    service: taskState.analysis.service || 'not detected',
                    attachments: taskState.analysis.attachments_count || 0,
                    sections: taskState.analysis.sections.join(', '),
                  }}
                  columns={[
                    { title: 'Тип документа', dataIndex: 'type' },
                    { title: 'Сервис', dataIndex: 'service' },
                    { title: 'Вложений', dataIndex: 'attachments' },
                    { title: 'Секции', dataIndex: 'sections' },
                  ]}
                />
              ) : (
                <Alert
                  showIcon
                  type="info"
                  message="Анализ задачи ещё не запускался"
                  description={taskState?.analysis_error || 'После запуска здесь появится разбор задачи.'}
                />
              )}

              {pipelineState ? (
                <Space direction="vertical" style={{ width: '100%' }} size={8}>
                  <Space>
                    <Typography.Text strong>Pipeline run</Typography.Text>
                    <Tag color={pipelineStateColor(pipelineState.state)}>{pipelineState.state}</Tag>
                    <Typography.Text type="secondary">{pipelineState.run_id}</Typography.Text>
                  </Space>

                  <List
                    size="small"
                    dataSource={pipelineState.stages || []}
                    renderItem={(stage) => (
                      <List.Item>
                        <Space direction="vertical" style={{ width: '100%' }} size={2}>
                          <Space>
                            <Typography.Text strong>{stage.name}</Typography.Text>
                            <Tag color={pipelineStateColor(stage.state)}>{stage.state}</Tag>
                          </Space>
                          <Typography.Text type="secondary">
                            start: {stage.started_at || '-'} • finish: {stage.finished_at || '-'}
                          </Typography.Text>
                          {stage.error && <Typography.Text type="danger">{stage.error}</Typography.Text>}
                        </Space>
                      </List.Item>
                    )}
                  />

                  <Collapse
                    items={[
                      {
                        key: 'pipeline-state',
                        label: 'Подробный статус pipeline',
                        children: (
                          <pre className="analytics-json">
                            {JSON.stringify(pipelineState, null, 2)}
                          </pre>
                        ),
                      },
                    ]}
                  />
                </Space>
              ) : (
                <Typography.Text type="secondary">
                  Pipeline еще не запускался для этой задачи.
                </Typography.Text>
              )}
            </Space>
          </ProCard>
        </ProCard>

        <ProCard className="analytics-panel" split="vertical" gutter={16}>
          <ProCard colSpan="50%" title="Шаг 5. Файлы, которые создала система">
            <Collapse
              items={[
                renderArtifactList('drafts', 'Черновики', taskState?.artifacts?.drafts || []),
                renderArtifactList('reviews', 'Пробелы и ревью', taskState?.artifacts?.reviews || []),
                renderArtifactList('context_packs', 'Контекст-паки', taskState?.artifacts?.context_packs || []),
                renderArtifactList('pipeline_runs', 'История pipeline', taskState?.artifacts?.pipeline_runs || []),
                renderArtifactList('handoffs', 'Handoff для Continue', taskState?.artifacts?.handoffs || []),
              ]}
            />
          </ProCard>

          <ProCard colSpan="50%" title="Быстрый просмотр содержимого">
            <Collapse
              items={[
                {
                  key: 'draft-preview',
                  label: 'Предпросмотр черновика',
                  children: (
                    <pre className="analytics-json">
                      {taskState?.latest?.draft_preview || 'Нет черновика'}
                    </pre>
                  ),
                },
                {
                  key: 'gaps-preview',
                  label: 'Предпросмотр пробелов и вопросов',
                  children: (
                    <pre className="analytics-json">
                      {taskState?.latest?.gaps_preview || 'Нет gap-analysis'}
                    </pre>
                  ),
                },
                {
                  key: 'handoff-preview',
                  label: 'Предпросмотр handoff',
                  children: (
                    <pre className="analytics-json">
                      {taskState?.latest?.handoff_preview || 'Нет handoff файла'}
                    </pre>
                  ),
                },
              ]}
            />
          </ProCard>
        </ProCard>
      </Space>
    </PageContainer>
  );
}
