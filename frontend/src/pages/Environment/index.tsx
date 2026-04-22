import React, { useEffect, useMemo, useState } from 'react';
import { CheckCircleOutlined, DownloadOutlined, LinkOutlined, SwapOutlined, ToolOutlined } from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import {
  Alert,
  Button,
  Checkbox,
  Descriptions,
  Form,
  Input,
  InputNumber,
  List,
  Radio,
  Space,
  Tag,
  Typography,
  message,
} from 'antd';

import { apiRequest } from '@/utils/api';
import type { EnvironmentSnapshot } from '@/utils/environment';

type EnvironmentForm = {
  confluence_base_url: string;
  confluence_login: string;
  confluence_password: string;
  vscode_ready: boolean;
  continue_ready: boolean;
  syncthing_ready: boolean;
  model_profile: string;
  optional_models: string[];
  exchange_folder: string;
  exchange_auto_scan: boolean;
  exchange_poll_interval_sec: number;
};

export default function EnvironmentPage() {
  const [form] = Form.useForm<EnvironmentForm>();
  const selectedModelProfile = Form.useWatch('model_profile', form) || 'powerful';
  const [snapshot, setSnapshot] = useState<EnvironmentSnapshot | null>(null);
  const [saving, setSaving] = useState(false);

  async function loadSnapshot() {
    const payload = await apiRequest<EnvironmentSnapshot>('/ui/environment-settings');
    setSnapshot(payload);
    form.setFieldsValue({
      confluence_base_url: payload.settings.confluence_base_url,
      confluence_login: payload.settings.confluence_login,
      confluence_password: '',
      vscode_ready: payload.settings.vscode_ready,
      continue_ready: payload.settings.continue_ready,
      syncthing_ready: payload.settings.syncthing_ready,
      model_profile: payload.settings.model_profile || 'powerful',
      optional_models: payload.settings.optional_models || [],
      exchange_folder: payload.settings.exchange_folder || payload.exchange.mounted_path,
      exchange_auto_scan: payload.settings.exchange_auto_scan ?? true,
      exchange_poll_interval_sec: payload.settings.exchange_poll_interval_sec || 60,
    });
  }

  useEffect(() => {
    void loadSnapshot();
  }, []);

  const selectedProfile = useMemo(
    () => snapshot?.recommended_profiles.find((item) => item.key === selectedModelProfile),
    [selectedModelProfile, snapshot],
  );

  async function saveSettings(values: EnvironmentForm) {
    setSaving(true);
    try {
      const payload = await apiRequest<EnvironmentSnapshot & { status: string }>('/ui/environment-settings', {
        method: 'POST',
        body: JSON.stringify(values),
      });
      setSnapshot(payload);
              form.setFieldsValue({ ...values, confluence_password: '' });
      message.success('Настройки окружения сохранены');
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Не удалось сохранить настройки');
    } finally {
      setSaving(false);
    }
  }

  return (
    <PageContainer
      title="Подготовка окружения"
      subTitle="Здесь один раз настраиваются доступы, локальные инструменты, обмен без сервера и модельный профиль. Пока базовые шаги ниже не готовы, раздел статьи останется недоступен."
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {snapshot ? (
          <Alert
            type={snapshot.readiness.all_ready ? 'success' : 'warning'}
            showIcon
            message={snapshot.readiness.all_ready ? 'Окружение готово к работе' : 'Нужно закончить первичную настройку'}
            description={snapshot.readiness.all_ready
              ? 'Теперь можно переходить в «Подготовка статьи» и собирать материалы.'
              : snapshot.readiness.missing_items.join(' | ')}
          />
        ) : null}

        <ProCard gutter={16} wrap>
          <ProCard colSpan={{ xs: 24, xl: 15 }} title="1. Доступ к Confluence" bordered>
            <Typography.Paragraph>
              Здесь сохраняются базовый адрес Confluence и твои учётные данные. После этого в статье ты будешь вставлять только ссылки, без повторного ввода логина и пароля.
            </Typography.Paragraph>
            <Form form={form} layout="vertical" onFinish={saveSettings} initialValues={{ model_profile: 'powerful', exchange_auto_scan: true, exchange_poll_interval_sec: 60 }}>
              <Form.Item
                label="Base URL Confluence"
                name="confluence_base_url"
                rules={[{ required: true, message: 'Укажи корневой адрес Confluence' }]}
              >
                <Input placeholder="https://confluence.company.ru" prefix={<LinkOutlined />} />
              </Form.Item>
              <Form.Item label="Логин" name="confluence_login" rules={[{ required: true, message: 'Укажи логин' }]}>
                <Input placeholder="name.surname" />
              </Form.Item>
              <Form.Item
                label="Пароль"
                name="confluence_password"
                extra={snapshot?.settings.has_confluence_password
                  ? 'Пароль уже сохранён. Оставь поле пустым, если не хочешь его менять.'
                  : 'Пароль будет сохранён локально в файлы сервиса.'}
              >
                <Input.Password placeholder={snapshot?.settings.has_confluence_password ? 'Оставь пустым, чтобы сохранить текущий пароль' : 'Введите пароль'} />
              </Form.Item>

                      <Typography.Title level={5}>2. Подготовка VS Code и Continue</Typography.Title>
                      <Typography.Paragraph type="secondary">
                        Эти отметки нужны, чтобы handoff из UI можно было сразу забрать в VS Code и дорабатывать уже в разговорном режиме через Continue.
                      </Typography.Paragraph>
              <Form.Item name="vscode_ready" valuePropName="checked">
                <Checkbox>VS Code установлен, проект открывается локально и команда `code` доступна</Checkbox>
              </Form.Item>
              <Form.Item name="continue_ready" valuePropName="checked">
                <Checkbox>Continue настроен и готов общаться с локальными моделями</Checkbox>
              </Form.Item>

              <Typography.Title level={5}>3. Командный обмен без облака и без git</Typography.Title>
              <Typography.Paragraph type="secondary">
                Для обмена между аналитиками рекомендуем `Syncthing` как транспорт и встроенный `VS Code Compare` как стандартный способ разбирать расхождения. Система будет смотреть не на весь проект, а только на отдельную папку обмена с bundle-пакетами.
              </Typography.Paragraph>
              <Form.Item
                label="Путь к папке обмена"
                name="exchange_folder"
                extra="После изменения пути нажми «Сохранить настройки», а затем перезапусти стек через ./start.command, чтобы Docker смонтировал новую папку."
              >
                <Input placeholder="/Users/<user>/team-exchange или C:\\team-exchange" prefix={<SwapOutlined />} />
              </Form.Item>
              <Form.Item name="syncthing_ready" valuePropName="checked">
                <Checkbox>Syncthing установлен и эта папка уже синхронизируется между ноутбуками аналитиков</Checkbox>
              </Form.Item>
              <Space size={16} align="start" style={{ width: '100%' }}>
                <Form.Item name="exchange_auto_scan" valuePropName="checked" style={{ marginBottom: 0 }}>
                  <Checkbox>Автоматически проверять папку обмена на новые bundle-пакеты</Checkbox>
                </Form.Item>
                <Form.Item label="Интервал опроса, сек" name="exchange_poll_interval_sec">
                  <InputNumber min={15} max={600} step={15} style={{ width: 140 }} />
                </Form.Item>
              </Space>

              {snapshot?.exchange ? (
                <Alert
                  style={{ marginBottom: 16 }}
                  type={snapshot.exchange.status === 'ready' ? 'success' : snapshot.exchange.requires_restart ? 'warning' : 'info'}
                  showIcon
                  message={
                    snapshot.exchange.status === 'ready'
                      ? 'Папка обмена подключена'
                      : snapshot.exchange.requires_restart
                        ? 'Путь обновлён, нужен перезапуск стека'
                        : 'Папка обмена ещё не доведена до рабочего состояния'
                  }
                  description={
                    snapshot.exchange.status === 'ready'
                      ? `Сейчас сервис смотрит в ${snapshot.exchange.mounted_path} и видит ${snapshot.exchange.total_bundles_count} bundle-пакетов.`
                      : snapshot.exchange.requires_restart
                        ? `Сохранён новый путь ${snapshot.exchange.configured_path}, но сервис всё ещё подключён к ${snapshot.exchange.mounted_path}. После ./start.command всё переключится на новый каталог.`
                        : `Текущая смонтированная папка: ${snapshot.exchange.mounted_path}. Когда подключишь Syncthing и укажешь рабочий путь, здесь появятся статусы новых обновлений.`
                  }
                />
              ) : null}

              <Typography.Title level={5}>4. Рекомендация по модели</Typography.Title>
              <Typography.Paragraph type="secondary">
                Этот выбор влияет не только на подсказки, но и на то, какие модели будут считаться обязательными. При загрузке в разделе «Модели и контекст» будут скачиваться только модели выбранного профиля.
              </Typography.Paragraph>
                      <Form.Item label="Профиль производительности" name="model_profile">
                        <Radio.Group optionType="button" buttonStyle="solid">
                          <Radio.Button value="light">Лёгкий</Radio.Button>
                          <Radio.Button value="standard">Стандартный</Radio.Button>
                          <Radio.Button value="powerful">Мощный</Radio.Button>
                        </Radio.Group>
                      </Form.Item>
                      <Form.Item
                        label="Дополнительные модели"
                        name="optional_models"
                        extra="Эти модели не обязательны для базового pipeline. Их можно выбрать, если хочешь дополнительные сценарии вроде второго мнения для ревью."
                      >
                        <Checkbox.Group
                          options={(snapshot?.optional_models || []).map((item) => ({
                            label: `${item.title} — ${item.description}`,
                            value: item.model,
                          }))}
                        />
                      </Form.Item>
                      <Space wrap>
                        <Button type="primary" htmlType="submit" loading={saving}>
                          Сохранить настройки
                </Button>
                <Button onClick={() => void loadSnapshot()}>Обновить статус</Button>
              </Space>
            </Form>
          </ProCard>

          <ProCard colSpan={{ xs: 24, xl: 9 }} title="Что важно помнить" bordered>
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="Запуск стека">
                  <Typography.Text code>{snapshot?.commands.start || './start.command'}</Typography.Text>
                </Descriptions.Item>
                <Descriptions.Item label="Остановка стека">
                  <Typography.Text code>{snapshot?.commands.stop || './stop.command'}</Typography.Text>
                </Descriptions.Item>
                <Descriptions.Item label="Переход в power mode">
                  <Typography.Text code>{snapshot?.commands.power_mode || './power-mode.command <task-id>'}</Typography.Text>
                </Descriptions.Item>
                <Descriptions.Item label="Инструкция по обмену">
                  <Typography.Text code>{snapshot?.exchange.doc_path || 'docs/team-exchange.md'}</Typography.Text>
                </Descriptions.Item>
                <Descriptions.Item label="Рекомендуемый diff">
                  <Typography.Text>{snapshot?.exchange.recommended_diff_tool.title || 'VS Code Compare'}</Typography.Text>
                </Descriptions.Item>
              </Descriptions>

              <Alert
                type="info"
                showIcon
                message="Подсказка по роли этого экрана"
                description="Здесь настраивается рабочее окружение аналитика: Confluence, VS Code, Continue, Syncthing, папка обмена и модельный профиль. Шаблоны и общий контекст потом живут в локальных папках и публикуются отдельными bundle-пакетами."
              />

              <List
                header="Чек-лист готовности"
                bordered
                dataSource={snapshot?.readiness.missing_items?.length ? snapshot.readiness.missing_items : ['Все обязательные шаги выполнены']}
                renderItem={(item) => (
                  <List.Item>
                    <Space>
                      <CheckCircleOutlined style={{ color: snapshot?.readiness.all_ready ? '#52c41a' : '#faad14' }} />
                      <span>{item}</span>
                    </Space>
                  </List.Item>
                )}
              />

              {snapshot?.exchange ? (
                <ProCard type="inner" title="Командный обмен">
                  <Typography.Paragraph style={{ marginBottom: 8 }}>
                    Текущий путь: <Typography.Text code>{snapshot.exchange.configured_path}</Typography.Text>
                  </Typography.Paragraph>
                  <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
                    {snapshot.exchange.recommended_diff_tool.description}
                  </Typography.Paragraph>
                  <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                    Новых пакетов в обмене: {snapshot.exchange.new_bundles_count}. Источник изменений — папки `docs/shared-context`, `docs/templates`, `docs/glossary`.
                  </Typography.Paragraph>
                </ProCard>
              ) : null}

                      {selectedProfile ? (
                        <ProCard type="inner" title={selectedProfile.title}>
                          <Typography.Paragraph>{selectedProfile.description}</Typography.Paragraph>
                          <Tag color="blue" icon={<ToolOutlined />}>Continue: {selectedProfile.continue_model}</Tag>
                          <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 4 }}>
                            Будут скачиваться сейчас: {(selectedProfile.required_models || []).join(', ')}
                          </Typography.Paragraph>
                          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                            Позже при переключении профиля: {(selectedProfile.deferred_models || []).join(', ') || 'дополнительных моделей нет'}
                          </Typography.Paragraph>
                          <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                            {selectedProfile.pipeline_hint}
                          </Typography.Paragraph>
                          {snapshot?.optional_models?.length ? (
                            <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                              Дополнительно по выбору: {snapshot.optional_models.map((item) => item.title).join(', ')}.
                            </Typography.Paragraph>
                          ) : null}
                        </ProCard>
                      ) : null}
            </Space>
          </ProCard>
        </ProCard>

        <ProCard title="Что дальше после сохранения" bordered>
          <List
            dataSource={[
              'Открой «Модели и контекст» и проверь, что обязательные модели скачаны. Если нет, там же будет кнопка загрузки и прогресс.',
              'Если работаешь в команде без сервера, настрой папку обмена и Syncthing, затем открой «Обмен контекстом». Там можно публиковать свои bundle-пакеты и забирать обновления коллег.',
              'Переходи в «Подготовка статьи» только после того, как шаги выше стали зелёными. Иначе UI осознанно не пустит дальше.',
              'Когда статья будет собрана и готов handoff, забирай задачу в VS Code через `./power-mode.command <task-id>` и дорабатывай результат уже в Continue.',
            ]}
            renderItem={(item) => (
              <List.Item>
                <Space align="start">
                  <DownloadOutlined style={{ marginTop: 4 }} />
                  <span>{item}</span>
                </Space>
              </List.Item>
            )}
          />
        </ProCard>

        <ProCard title="Пошаговая настройка VS Code и Continue" bordered>
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Alert
              type="info"
              showIcon
              message="Этот блок нужен для power mode"
              description="UI собирает материалы и готовит handoff, а VS Code + Continue нужны для живой доработки результата в файлах проекта."
            />

            <ProCard type="inner" title="0. Что подготовить на машине заранее">
              <List
                dataSource={[
                  'Установи Docker Desktop и убедись, что локальные контейнеры проекта могут запускаться.',
                  'Установи Ollama. Именно он будет держать локальные модели, которые используются в UI и в Continue.',
                  'Установи Syncthing, если хочешь обмениваться контекстом с коллегами без сервера и без git.',
                  'Затем открой раздел «Модели и контекст» и скачай недостающие модели. Для более слабой машины выбирай лёгкий или стандартный профиль, для мощного Mac можно оставлять тяжёлый.',
                ]}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
            </ProCard>

            <ProCard type="inner" title="1. Подготовить VS Code">
              <List
                dataSource={[
                  'Установи Visual Studio Code, если он ещё не установлен.',
                  'Открой папку проекта в VS Code обычным способом через интерфейс редактора или через команду `code`, если она настроена.',
                  'Если `code` ещё не доступна в терминале, добавь её в PATH средствами своей операционной системы и самого VS Code.',
                  'После этого вернись сюда и отметь галочку, что VS Code готов.',
                ]}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
            </ProCard>

            <ProCard type="inner" title="2. Подготовить Continue">
              <List
                dataSource={[
                  'Установи расширение Continue в VS Code.',
                  'Открой Continue и подключи локальный Ollama как провайдер моделей.',
                  'Если нужен адрес сервиса, используй `http://localhost:11434`.',
                  `Для текущего профиля машины рекомендуем модель Continue: ${selectedProfile?.continue_model || 'qwen3-coder:30b'}.`,
                  'Если машина не тянет тяжёлую модель, вернись выше и переключи профиль на более лёгкий. Это повлияет на рекомендацию для Continue.',
                  'После настройки вернись сюда и отметь галочку, что Continue готов. Теперь система ещё и смотрит сам config.yaml, а не только на галочку.',
                ]}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />

              {snapshot?.continue_config ? (
                <Space direction="vertical" size={16} style={{ width: '100%', marginTop: 16 }}>
                  <Alert
                    type={snapshot.continue_config.status === 'ready' ? 'success' : 'warning'}
                    showIcon
                    message={
                      snapshot.continue_config.status === 'ready'
                        ? 'Конфиг Continue похож на рекомендуемый'
                        : 'Конфиг Continue нужно проверить'
                    }
                    description={
                      snapshot.continue_config.status === 'ready'
                        ? `Система нашла файл ${snapshot.continue_config.detected_path} и видит в нём нужные алиасы для работы.`
                        : snapshot.continue_config.exists
                          ? `Файл ${snapshot.continue_config.detected_path} найден, но в нём не хватает нужных алиасов или модели отличаются от рекомендуемых.`
                          : `Файл ${snapshot.continue_config.detected_path} пока не найден. Можно создать его по шаблону из репозитория.`
                    }
                  />

                  <Descriptions column={1} size="small" bordered>
                    <Descriptions.Item label="Где искать на macOS">
                      <Typography.Text code>{snapshot.continue_config.known_paths.macos}</Typography.Text>
                    </Descriptions.Item>
                    <Descriptions.Item label="Где искать на Windows">
                      <Typography.Text code>{snapshot.continue_config.known_paths.windows}</Typography.Text>
                    </Descriptions.Item>
                    <Descriptions.Item label="Проверенный путь на этой машине">
                      <Typography.Text code>{snapshot.continue_config.detected_path}</Typography.Text>
                    </Descriptions.Item>
                    <Descriptions.Item label="Шаблон в репозитории">
                      <Typography.Text code>{snapshot.continue_config.template_repo_path}</Typography.Text>
                    </Descriptions.Item>
                  </Descriptions>

                  {snapshot.continue_config.parse_error ? (
                    <Alert
                      type="error"
                      showIcon
                      message="YAML не удалось разобрать"
                      description={snapshot.continue_config.parse_error}
                    />
                  ) : null}

                  <ProCard type="inner" title="Какие алиасы рекомендуем для Continue">
                    <List
                      dataSource={snapshot.continue_config.recommended_models}
                      renderItem={(item) => (
                        <List.Item>
                          <Space direction="vertical" size={4} style={{ width: '100%' }}>
                            <Space wrap>
                              <Tag color={item.required ? 'blue' : 'default'}>{item.alias}</Tag>
                              <Typography.Text code>{item.model}</Typography.Text>
                              <Tag>{item.required ? 'обязательно для профиля' : 'опционально'}</Tag>
                            </Space>
                            <Typography.Text type="secondary">{item.purpose}</Typography.Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  </ProCard>

                  <ProCard type="inner" title="Что сейчас найдено в config.yaml">
                    <List
                      locale={{ emptyText: 'Пока не нашли ни одной модели. Скопируй шаблон и подставь свои значения.' }}
                      dataSource={snapshot.continue_config.current_models}
                      renderItem={(item) => (
                        <List.Item>
                          <Space direction="vertical" size={4} style={{ width: '100%' }}>
                            <Space wrap>
                              <Tag>{item.alias}</Tag>
                              <Typography.Text code>{item.model}</Typography.Text>
                              <Typography.Text type="secondary">{item.provider || 'provider не указан'}</Typography.Text>
                            </Space>
                            <Typography.Text type="secondary">
                              apiBase: {item.api_base || 'не указан'}
                            </Typography.Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  </ProCard>

                  {snapshot.continue_config.missing_aliases.length ? (
                    <Alert
                      type="warning"
                      showIcon
                      message="Не хватает алиасов"
                      description={`Добавь в config.yaml алиасы: ${snapshot.continue_config.missing_aliases.join(', ')}`}
                    />
                  ) : null}

                  {snapshot.continue_config.mismatched_aliases.length ? (
                    <Alert
                      type="warning"
                      showIcon
                      message="Некоторые алиасы смотрят не на те модели"
                      description={snapshot.continue_config.mismatched_aliases
                        .map((item) => `${item.alias}: сейчас ${item.actual_model || 'не указано'}, рекомендуем ${item.expected_model}`)
                        .join(' | ')}
                    />
                  ) : null}

                  <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                    Если удобно, можно взять файл-шаблон из репозитория и адаптировать его под свою машину. Для большинства аналитиков достаточно алиасов
                    {' '}
                    <Typography.Text code>fast</Typography.Text>,
                    {' '}
                    <Typography.Text code>main</Typography.Text>
                    {' '}и, при мощной машине,
                    {' '}
                    <Typography.Text code>heavy</Typography.Text>.
                    {' '}Алиас
                    {' '}
                    <Typography.Text code>review</Typography.Text>
                    {' '}имеет смысл добавлять, если ты отдельно скачал GPT OSS 20B для второго мнения.
                  </Typography.Paragraph>

                  <Typography.Title level={5} style={{ marginBottom: 0 }}>
                    Рекомендуемый YAML для текущего профиля
                  </Typography.Title>
                  <pre
                    style={{
                      margin: 0,
                      padding: 16,
                      overflowX: 'auto',
                      borderRadius: 8,
                      background: '#fafafa',
                      border: '1px solid #f0f0f0',
                    }}
                  >
                    {snapshot.continue_config.recommended_yaml}
                  </pre>
                </Space>
              ) : null}
            </ProCard>

            <ProCard type="inner" title="3. Подготовить командный обмен через Syncthing">
              <List
                dataSource={[
                  'Установи Syncthing на каждую машину аналитика.',
                  'Создай папку обмена, например `/Users/<user>/team-exchange` на macOS или `C:\\team-exchange` на Windows.',
                  'Подключи эту папку в Syncthing на всех машинах, между которыми нужен обмен контекстом.',
                  'Укажи этот путь выше в поле «Путь к папке обмена», сохрани настройки и перезапусти стек через `./start.command`.',
                  'Для разбора incoming-файлов используем один рекомендуемый инструмент: встроенный `VS Code Compare`, отдельный diff-клиент не нужен.',
                ]}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
            </ProCard>

            <ProCard type="inner" title="4. Как работать после handoff">
              <List
                dataSource={[
                  'Сначала собери задачу в UI: task.md, контекст, draft, gaps, refine.',
                  'Нажми `Prepare handoff`, чтобы система создала handoff-файл и рабочую копию черновика.',
                  'Открой рабочую папку в VS Code. Если ты на macOS и используешь локальный помощник проекта, можно запускать `./power-mode.command <task-id>`.',
                  'Дальше уже можно разговаривать с агентом в Continue и править результат онлайн, не ломая основной pipeline.',
                ]}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
            </ProCard>
          </Space>
        </ProCard>
      </Space>
    </PageContainer>
  );
}
