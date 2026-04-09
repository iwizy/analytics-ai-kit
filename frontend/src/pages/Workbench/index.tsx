import React, { useEffect, useMemo, useState } from 'react';
        import { LinkOutlined, SendOutlined, UploadOutlined } from '@ant-design/icons';
        import { Link } from '@umijs/max';
        import { PageContainer, ProCard } from '@ant-design/pro-components';
        import {
          Alert,
          Button,
          Checkbox,
          Descriptions,
          Divider,
          Input,
          List,
          Segmented,
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
          size?: number;
          modified_at?: string;
        };

        type AnalysisPayload = {
          document_kind?: string;
          document_type?: string;
          summary?: string;
          recommended_sections?: string[];
          [key: string]: unknown;
        };

        type PipelineSnapshot = {
          run_id?: string;
          status?: string;
          stage?: string;
          error?: string;
          updated_at?: string;
          started_at?: string;
          finished_at?: string;
          [key: string]: unknown;
        };

        type TaskState = {
          task_id: string;
          task_content: string;
          attachments: FileMeta[];
          analysis?: AnalysisPayload | null;
          artifacts?: Record<string, FileMeta[]>;
          latest_pipeline?: PipelineSnapshot | null;
          latest?: {
            draft_preview?: string;
            gaps_preview?: string;
            handoff_preview?: string;
          };
        };

        type SourceMode = 'files' | 'links' | 'both';
        type BusyKey = 'template' | 'save' | 'links' | 'analyze' | 'draft' | 'gap' | 'refine' | 'pipeline' | 'handoff' | null;

        export default function WorkbenchPage() {
          const [environment, setEnvironment] = useState<EnvironmentSnapshot | null>(null);
          const [taskId, setTaskId] = useState('');
          const [taskContent, setTaskContent] = useState('');
          const [confluenceUrls, setConfluenceUrls] = useState('');
          const [refineInstructions, setRefineInstructions] = useState('Уточни формулировки, убери неоднозначности и сделай текст пригодным для согласования с разработкой и аналитикой.');
          const [sourceMode, setSourceMode] = useState<SourceMode>('both');
          const [runGaps, setRunGaps] = useState(true);
          const [autoRunRefine, setAutoRunRefine] = useState(true);
          const [busyKey, setBusyKey] = useState<BusyKey>(null);
          const [taskState, setTaskState] = useState<TaskState | null>(null);

          const currentTaskId = taskId.trim();
          const readyForWork = environment?.readiness.article_ready || false;
          const linkRows = useMemo(
            () => confluenceUrls.split(/\n+/).map((item) => item.trim()).filter(Boolean),
            [confluenceUrls],
          );

          async function loadEnvironment() {
            const payload = await apiRequest<EnvironmentSnapshot>('/ui/environment-settings');
            setEnvironment(payload);
          }

          async function loadTaskState(targetTaskId: string) {
            if (!targetTaskId) {
              setTaskState(null);
              return;
            }
            const payload = await apiRequest<TaskState>(`/ui/state/${encodeURIComponent(targetTaskId)}`);
            setTaskState(payload);
            setTaskContent(payload.task_content || '');
          }

          useEffect(() => {
            void loadEnvironment();
          }, []);

          useEffect(() => {
            if (!currentTaskId) {
              setTaskState(null);
              return;
            }
            void loadTaskState(currentTaskId);
          }, [currentTaskId]);

          async function withBusy(key: BusyKey, action: () => Promise<void>, successMessage: string) {
            setBusyKey(key);
            try {
              await action();
              message.success(successMessage);
              await loadEnvironment();
              if (currentTaskId) {
                await loadTaskState(currentTaskId);
              }
            } catch (error) {
              message.error(error instanceof Error ? error.message : 'Операция завершилась ошибкой');
            } finally {
              setBusyKey(null);
            }
          }

          async function loadTemplate() {
            await withBusy('template', async () => {
              const payload = await apiRequest<{ template: string }>('/ui/task-template');
              setTaskContent(payload.template);
            }, 'Шаблон task.md подложен в редактор');
          }

          async function saveTask() {
            if (!currentTaskId) {
              message.error('Сначала укажи Task ID');
              return;
            }
            await withBusy('save', async () => {
              await apiRequest('/ui/create-task', {
                method: 'POST',
                body: JSON.stringify({ task_id: currentTaskId, content: taskContent }),
              });
            }, 'task.md сохранён');
          }

          async function importConfluenceLinks() {
            if (!currentTaskId) {
              message.error('Сначала укажи Task ID');
              return;
            }
            if (!linkRows.length) {
              message.error('Добавь хотя бы одну ссылку');
              return;
            }
            const baseUrl = environment?.settings.confluence_base_url?.trim();
            const invalidLinks = baseUrl
              ? linkRows.filter((item) => !item.startsWith(baseUrl))
              : [];
            if (invalidLinks.length) {
              message.error('Часть ссылок не совпадает с Base URL Confluence из настроек окружения');
              return;
            }
            await withBusy('links', async () => {
              await apiRequest('/ui/import-confluence', {
                method: 'POST',
                body: JSON.stringify({
                  task_id: currentTaskId,
                  analyst_id: 'default',
                  urls: linkRows,
                }),
              });
            }, 'Ссылки Confluence импортированы и сохранены как локальный контекст');
          }

          async function uploadAttachment(options: RcCustomRequestOptions) {
            if (!currentTaskId) {
              message.error('Сначала укажи Task ID');
              options.onError?.(new Error('Task ID is required'));
              return;
            }
            const formData = new FormData();
            formData.append('files', options.file as Blob, (options.file as File).name);
            try {
              const response = await fetch(`${API_BASE}/ui/upload-attachments/${encodeURIComponent(currentTaskId)}`, {
                method: 'POST',
                body: formData,
              });
              if (!response.ok) {
                const payload = await response.text();
                throw new Error(payload || 'Не удалось загрузить файл');
              }
              options.onSuccess?.({}, options.file as never);
              message.success(`Файл ${(options.file as File).name} загружен`);
              await loadTaskState(currentTaskId);
            } catch (error) {
              options.onError?.(error as Error);
              message.error(error instanceof Error ? error.message : 'Не удалось загрузить файл');
            }
          }

          async function runAnalyze() {
            if (!currentTaskId) {
              message.error('Сначала укажи Task ID');
              return;
            }
            await withBusy('analyze', async () => {
              await apiRequest('/analyze-task', {
                method: 'POST',
                body: JSON.stringify({ task_id: currentTaskId }),
              });
            }, 'Анализ задачи завершён');
          }

          async function runDraft() {
            if (!currentTaskId) {
              message.error('Сначала укажи Task ID');
              return;
            }
            await withBusy('draft', async () => {
              await apiRequest('/draft', {
                method: 'POST',
                body: JSON.stringify({ task_id: currentTaskId }),
              });
            }, 'Первый черновик собран');
          }

          async function runGapAnalysis() {
            if (!currentTaskId) {
              message.error('Сначала укажи Task ID');
              return;
            }
            await withBusy('gap', async () => {
              await apiRequest('/gap-analysis', {
                method: 'POST',
                body: JSON.stringify({ task_id: currentTaskId }),
              });
            }, 'Пробелы и открытые вопросы найдены');
          }

          async function runRefine() {
            if (!currentTaskId) {
              message.error('Сначала укажи Task ID');
              return;
            }
            await withBusy('refine', async () => {
              await apiRequest('/refine', {
                method: 'POST',
                body: JSON.stringify({ task_id: currentTaskId, instructions: refineInstructions }),
              });
            }, 'Черновик доработан');
          }

          async function runPipeline() {
            if (!currentTaskId) {
              message.error('Сначала укажи Task ID');
              return;
            }
            await withBusy('pipeline', async () => {
              await apiRequest('/run-pipeline', {
                method: 'POST',
                body: JSON.stringify({
                  task_id: currentTaskId,
                  run_gaps: runGaps,
                  run_refine: autoRunRefine,
                  refine_instructions: refineInstructions,
                }),
              });
            }, 'Полный pipeline запущен');
          }

          async function prepareHandoff() {
            if (!currentTaskId) {
              message.error('Сначала укажи Task ID');
              return;
            }
            await withBusy('handoff', async () => {
              await apiRequest('/prepare-handoff', {
                method: 'POST',
                body: JSON.stringify({ task_id: currentTaskId }),
              });
            }, 'Handoff для Continue подготовлен');
          }

          function renderArtifactList(kind: string, title: string, items: FileMeta[]) {
            return (
              <List
                size="small"
                header={title}
                dataSource={items}
                locale={{ emptyText: 'Пока пусто' }}
                renderItem={(item) => (
                  <List.Item>
                    {kind === 'attachments' ? (
                      <span>{item.name}</span>
                    ) : (
                      <a href={artifactUrl(kind, currentTaskId, item.name)} target="_blank" rel="noreferrer">
                        {item.name}
                      </a>
                    )}
                  </List.Item>
                )}
              />
            );
          }

          if (!readyForWork) {
            return (
              <PageContainer
                title="Подготовка статьи"
                subTitle="Этот раздел открывается только после завершения подготовки окружения."
              >
                <Alert
                  type="warning"
                  showIcon
                  message="Сначала закончи подготовку окружения"
                  description={environment?.readiness.missing_items?.join(' | ') || 'Нужно сохранить настройки Confluence, отметить VS Code и Continue и скачать модели.'}
                />
                <Divider />
                <Space wrap>
                  <Button type="primary">
                    <Link to="/environment">Перейти в подготовку окружения</Link>
                  </Button>
                  <Button>
                    <Link to="/models-docs">Открыть модели и контекст</Link>
                  </Button>
                </Space>
              </PageContainer>
            );
          }

          return (
            <PageContainer
              title="Подготовка статьи"
              subTitle="Этот раздел сопровождает аналитика по шагам: от Task ID и источников до handoff в VS Code + Continue."
            >
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Alert
                  type="info"
                  showIcon
                  message="Шаблоны для обычного аналитика не редактируем здесь"
                  description="Кнопка ниже просто подложит текущий шаблон task.md в редактор. Если нужно менять сам шаблон или структуру документа, это делаем отдельно в power mode."
                />

                <ProCard title="Шаг 1. Описание задачи и Task ID" bordered>
                  <Typography.Paragraph>
                    `Task ID` станет именем папки задачи. По нему система создаст `tasks/inbox/&lt;task-id&gt;/task.md`, положит вложения в `attachments/` и будет складывать артефакты в `artifacts/.../&lt;task-id&gt;/`.
                  </Typography.Paragraph>
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <Input value={taskId} onChange={(event) => setTaskId(event.target.value)} placeholder="Например, billing-api-ft" />
                    <Space wrap>
                      <Button loading={busyKey === 'template'} onClick={() => void loadTemplate()}>Подложить шаблон</Button>
                      <Button type="primary" loading={busyKey === 'save'} onClick={() => void saveTask()}>Сохранить task.md</Button>
                    </Space>
                    <Input.TextArea
                      rows={14}
                      value={taskContent}
                      onChange={(event) => setTaskContent(event.target.value)}
                      placeholder="Опиши задачу, контекст, ограничения и ожидаемый результат"
                    />
                  </Space>
                </ProCard>

                <ProCard title="Шаг 2. Источники: файлы, ссылки или оба варианта" bordered>
                  <Typography.Paragraph>
                    Здесь аналитик сам решает, как дать контекст: загрузить документы, вставить ссылки на Confluence или использовать смешанный режим. Все обработанные ссылки сохраняются локально текстом и дальше участвуют в генерации как обычный контекст.
                  </Typography.Paragraph>
                  <Segmented<SourceMode>
                    block
                    options={[
                      { label: 'Только файлы', value: 'files' },
                      { label: 'Только ссылки', value: 'links' },
                      { label: 'Файлы и ссылки', value: 'both' },
                    ]}
                    value={sourceMode}
                    onChange={(value) => setSourceMode(value as SourceMode)}
                  />
                  <Space direction="vertical" size={16} style={{ width: '100%', marginTop: 16 }}>
                    {sourceMode !== 'links' ? (
                      <ProCard type="inner" title="2.1 Загрузка файлов">
                        <Typography.Paragraph type="secondary">
                          Загруженные документы копируются в `tasks/inbox/&lt;task-id&gt;/attachments/` и становятся частью локального контекста.
                        </Typography.Paragraph>
                        <Upload multiple customRequest={uploadAttachment} showUploadList={false}>
                          <Button icon={<UploadOutlined />}>Загрузить документы</Button>
                        </Upload>
                      </ProCard>
                    ) : null}

                    {sourceMode !== 'files' ? (
                      <ProCard type="inner" title="2.2 Ссылки Confluence">
                        <Typography.Paragraph type="secondary">
                          Логин, пароль и Base URL уже берутся из «Подготовка окружения». Здесь нужно только вставить ссылки, каждая с новой строки.
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
                          <Button type="primary" loading={busyKey === 'links'} icon={<LinkOutlined />} onClick={() => void importConfluenceLinks()}>
                            Импортировать ссылки
                          </Button>
                          <Typography.Text type="secondary">Импортированные страницы сохранятся как `.md` в attachments.</Typography.Text>
                        </Space>
                      </ProCard>
                    ) : null}

                    <Descriptions column={1} bordered size="small">
                      <Descriptions.Item label="Вложений уже в задаче">{taskState?.attachments?.length || 0}</Descriptions.Item>
                      <Descriptions.Item label="Base URL Confluence">{environment?.settings.confluence_base_url || 'Не задан'}</Descriptions.Item>
                    </Descriptions>
                  </Space>
                </ProCard>

                <ProCard title="Шаг 3. Генерация документа" bordered>
                  <Alert
                    type="info"
                    showIcon
                    message="FT и NFT"
                    description="FT — функциональные требования, то есть что система должна делать. NFT — нефункциональные требования: производительность, надёжность, безопасность, ограничения среды и подобные характеристики."
                  />
                  <List
                    style={{ marginTop: 16 }}
                    dataSource={[
                      '3.1 Analyze: анализирует задачу, определяет тип документа и рекомендуемую структуру разделов.',
                      '3.2 Draft: собирает первый черновик на основе task.md, вложений и импортированного контекста.',
                      '3.3 Gaps: ищет пробелы, недосказанности, спорные места и вопросы, которые стоит уточнить.',
                      '3.4 Refine: доработка уже созданного черновика. На этом шаге система перечитывает текущий текст, сверяет его с контекстом, переписывает двусмысленные формулировки, делает текст понятнее и полезнее для согласования.',
                      '3.5 Prepare handoff: готовит handoff для VS Code + Continue, чтобы аналитик мог открыть рабочую копию и править результат в разговорном режиме.',
                    ]}
                    renderItem={(item) => <List.Item>{item}</List.Item>}
                  />
                  <Input.TextArea
                    rows={4}
                    style={{ marginTop: 16 }}
                    value={refineInstructions}
                    onChange={(event) => setRefineInstructions(event.target.value)}
                    placeholder="Что именно нужно улучшить на шаге refine"
                  />
                  <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
                    Поле выше влияет только на `refine`. Здесь можно написать, что именно хочется улучшить в уже готовом черновике: тон, полноту описаний, список открытых вопросов, структуру разделов.
                  </Typography.Paragraph>
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <Space wrap>
                      <Button loading={busyKey === 'analyze'} onClick={() => void runAnalyze()}>3.1 Analyze</Button>
                      <Button loading={busyKey === 'draft'} onClick={() => void runDraft()}>3.2 Draft</Button>
                      <Button loading={busyKey === 'gap'} onClick={() => void runGapAnalysis()}>3.3 Gaps</Button>
                      <Button loading={busyKey === 'refine'} onClick={() => void runRefine()}>3.4 Refine</Button>
                      <Button loading={busyKey === 'handoff'} onClick={() => void prepareHandoff()}>3.5 Prepare handoff</Button>
                      <Button type="primary" icon={<SendOutlined />} loading={busyKey === 'pipeline'} onClick={() => void runPipeline()}>
                        Запустить весь pipeline
                      </Button>
                    </Space>
                    <Space direction="vertical" size={4}>
                      <Checkbox checked={runGaps} onChange={(event) => setRunGaps(event.target.checked)}>
                        После draft автоматически искать пробелы
                      </Checkbox>
                      <Checkbox checked={autoRunRefine} onChange={(event) => setAutoRunRefine(event.target.checked)}>
                        После draft автоматически запускать refine
                      </Checkbox>
                    </Space>
                  </Space>
                </ProCard>

                <ProCard title="Шаг 4. Переход в VS Code и Continue" bordered>
                  <List
                    dataSource={[
                      'После `Prepare handoff` система создаёт handoff-файл с контекстом задачи и отдельную рабочую копию черновика.',
                      'Открой VS Code через `./power-mode.command <task-id>` — он подтянет проект, handoff и рабочую копию.',
                      'Дальше аналитик может уже разговаривать с агентом в Continue и править результат онлайн, не теряя артефакты, собранные в UI.',
                    ]}
                    renderItem={(item) => <List.Item>{item}</List.Item>}
                  />
                </ProCard>

                <ProCard title="Результат и артефакты" bordered>
                  <Tabs
                    items={[
                      {
                        key: 'status',
                        label: 'Текущий статус',
                        children: (
                          <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            <Descriptions column={1} bordered size="small">
                              <Descriptions.Item label="Определённый тип документа">
                                {taskState?.analysis?.document_kind || taskState?.analysis?.document_type || 'Пока не определён'}
                              </Descriptions.Item>
                              <Descriptions.Item label="Последний pipeline">
                                {taskState?.latest_pipeline?.status || 'Пока не запускался'}
                              </Descriptions.Item>
                            </Descriptions>
                            <Typography.Paragraph>
                              <Typography.Text strong>Черновик:</Typography.Text>
                              <br />
                              {taskState?.latest?.draft_preview || 'Пока нет черновика'}
                            </Typography.Paragraph>
                            <Typography.Paragraph>
                              <Typography.Text strong>Пробелы и вопросы:</Typography.Text>
                              <br />
                              {taskState?.latest?.gaps_preview || 'Пока нет результата gap-analysis'}
                            </Typography.Paragraph>
                            <Typography.Paragraph>
                              <Typography.Text strong>Handoff preview:</Typography.Text>
                              <br />
                              {taskState?.latest?.handoff_preview || 'Handoff ещё не подготовлен'}
                            </Typography.Paragraph>
                          </Space>
                        ),
                      },
                      {
                        key: 'attachments',
                        label: 'Контекст',
                        children: renderArtifactList('attachments', 'Вложения и импортированные страницы', taskState?.attachments || []),
                      },
                      {
                        key: 'drafts',
                        label: 'Черновики',
                        children: renderArtifactList('drafts', 'Drafts', taskState?.artifacts?.drafts || []),
                      },
                      {
                        key: 'reviews',
                        label: 'Gaps',
                        children: renderArtifactList('reviews', 'Gap analysis', taskState?.artifacts?.reviews || []),
                      },
                      {
                        key: 'handoffs',
                        label: 'Handoff',
                        children: renderArtifactList('handoffs', 'Handoff files', taskState?.artifacts?.handoffs || []),
                      },
                      {
                        key: 'pipeline',
                        label: 'Pipeline runs',
                        children: renderArtifactList('pipeline_runs', 'Снимки pipeline', taskState?.artifacts?.pipeline_runs || []),
                      },
                    ]}
                  />
                </ProCard>
              </Space>
            </PageContainer>
          );
        }
