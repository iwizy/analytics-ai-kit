import React, { useEffect, useMemo, useState } from 'react';
import { CheckCircleOutlined, DownloadOutlined, FileAddOutlined, LinkOutlined, SwapOutlined, ToolOutlined } from '@ant-design/icons';
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
  Popconfirm,
  Radio,
  Space,
  Tag,
  Typography,
  Divider,
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
  const [baselineValues, setBaselineValues] = useState<EnvironmentForm | null>(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [continueConfigBusy, setContinueConfigBusy] = useState(false);
  const [continueConfigError, setContinueConfigError] = useState('');

  function normalizeFormValues(values: Partial<EnvironmentForm> | null | undefined): EnvironmentForm {
    const optionalModels = [...(values?.optional_models || [])]
      .map((item) => String(item).trim())
      .filter(Boolean)
      .sort();

    return {
      confluence_base_url: String(values?.confluence_base_url || '').trim(),
      confluence_login: String(values?.confluence_login || '').trim(),
      confluence_password: String(values?.confluence_password || ''),
      vscode_ready: Boolean(values?.vscode_ready),
      continue_ready: Boolean(values?.continue_ready),
      syncthing_ready: Boolean(values?.syncthing_ready),
      model_profile: String(values?.model_profile || 'powerful'),
      optional_models: optionalModels,
      exchange_folder: String(values?.exchange_folder || '').trim(),
      exchange_auto_scan: values?.exchange_auto_scan !== false,
      exchange_poll_interval_sec: Number(values?.exchange_poll_interval_sec || 60),
    };
  }

  function applyDirtyState(nextValues?: Partial<EnvironmentForm>) {
    if (!baselineValues) {
      setHasChanges(false);
      return;
    }
    const current = normalizeFormValues(nextValues || form.getFieldsValue(true));
    setHasChanges(JSON.stringify(current) !== JSON.stringify(baselineValues));
  }

  async function loadSnapshot() {
    const payload = await apiRequest<EnvironmentSnapshot>('/ui/environment-settings');
    setSnapshot(payload);
    setSaveError('');
    setContinueConfigError('');
    const values = normalizeFormValues({
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
    form.setFieldsValue(values);
    setBaselineValues(values);
    setHasChanges(false);
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
      const nextValues = normalizeFormValues({ ...values, confluence_password: '' });
      form.setFieldsValue(nextValues);
      setBaselineValues(nextValues);
      setHasChanges(false);
      setSaveError('');
      message.success('Настройки окружения сохранены');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Не удалось сохранить настройки';
      setSaveError(errorMessage);
      message.error(errorMessage);
    } finally {
      setSaving(false);
    }
  }

  async function handleSave() {
    await saveSettings(normalizeFormValues(form.getFieldsValue(true)));
  }

  async function writeContinueConfig(overwrite: boolean) {
    setContinueConfigBusy(true);
    try {
      const payload = await apiRequest<EnvironmentSnapshot & { status: string; continue_config_write: { path: string } }>('/ui/continue-config', {
        method: 'POST',
        body: JSON.stringify({ overwrite }),
      });
      setSnapshot(payload);
      setContinueConfigError('');
      message.success(`config.yaml Continue ${overwrite ? 'обновлён' : 'создан'}: ${payload.continue_config_write.path}`);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Не удалось создать config.yaml Continue';
      setContinueConfigError(errorMessage);
      message.error(errorMessage);
    } finally {
      setContinueConfigBusy(false);
    }
  }

  function resetToSavedState() {
    if (!baselineValues) {
      return;
    }
    form.setFieldsValue(baselineValues);
    setHasChanges(false);
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

        {saveError ? (
          <Alert
            type="error"
            showIcon
            closable
            message="Настройки не сохранились"
            description={saveError}
            onClose={() => setSaveError('')}
          />
        ) : null}

        <ProCard gutter={16} wrap>
          <ProCard colSpan={{ xs: 24, xl: 15 }} title="1. Доступ к Confluence" bordered>
            <Typography.Paragraph>
              Здесь сохраняются базовый адрес Confluence и твои учётные данные. После этого в статье ты будешь вставлять только ссылки, без повторного ввода логина и пароля.
            </Typography.Paragraph>
            <Form
              form={form}
              layout="vertical"
              initialValues={{ model_profile: 'powerful', exchange_auto_scan: true, exchange_poll_interval_sec: 60 }}
              onValuesChange={(_, allValues) => applyDirtyState(allValues as Partial<EnvironmentForm>)}
            >
              <Form.Item
                label="Base URL Confluence"
                name="confluence_base_url"
              >
                <Input placeholder="https://confluence.company.ru" prefix={<LinkOutlined />} />
              </Form.Item>
              <Form.Item label="Логин" name="confluence_login">
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
                      <Button onClick={() => void loadSnapshot()}>Обновить статус</Button>
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

                  {continueConfigError ? (
                    <Alert
                      type="error"
                      showIcon
                      closable
                      message="config.yaml Continue не сохранён"
                      description={continueConfigError}
                      onClose={() => setContinueConfigError('')}
                    />
                  ) : null}

                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Space wrap>
                      {snapshot.continue_config.exists ? (
                        <Popconfirm
                          title="Перезаписать config.yaml Continue?"
                          description="Система заменит файл рекомендуемым YAML для текущего профиля и выбранных optional-моделей."
                          okText="Перезаписать"
                          cancelText="Отмена"
                          onConfirm={() => void writeContinueConfig(true)}
                        >
                          <Button
                            icon={<FileAddOutlined />}
                            loading={continueConfigBusy}
                          >
                            Обновить config.yaml по рекомендации
                          </Button>
                        </Popconfirm>
                      ) : (
                        <Button
                          type="primary"
                          icon={<FileAddOutlined />}
                          loading={continueConfigBusy}
                          onClick={() => void writeContinueConfig(false)}
                        >
                          Создать config.yaml в правильном месте
                        </Button>
                      )}
                      <Button onClick={() => void loadSnapshot()} disabled={continueConfigBusy}>
                        Проверить заново
                      </Button>
                    </Space>
                    <Typography.Text type="secondary">
                      Кнопка записывает файл в путь, который ожидает Continue для текущей ОС:
                      {' '}
                      <Typography.Text code>{snapshot.continue_config.detected_path}</Typography.Text>
                      . Если Docker не видит этот путь, перезапусти проект через
                      {' '}
                      <Typography.Text code>./start.command</Typography.Text>
                      , он смонтирует папку
                      {' '}
                      <Typography.Text code>~/.continue</Typography.Text>
                      {' '}на запись.
                    </Typography.Text>
                  </Space>

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
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Alert
                  type="info"
                  showIcon
                  message="Как ставить Syncthing"
                  description={(
                    <Space direction="vertical" size={8}>
                      <span>
                        Официальная страница загрузки:
                        {' '}
                        <a href="https://syncthing.net/downloads/" target="_blank" rel="noreferrer">syncthing.net/downloads</a>
                      </span>
                      <span>
                        macOS: лучше начинать с app bundle
                        {' '}
                        <a href="https://github.com/syncthing/syncthing-macos" target="_blank" rel="noreferrer">syncthing-macos</a>
                      </span>
                      <span>
                        Windows: лучше начинать с установщика
                        {' '}
                        <a href="https://github.com/Bill-Stewart/SyncthingWindowsSetup" target="_blank" rel="noreferrer">Syncthing Windows Setup</a>
                      </span>
                    </Space>
                  )}
                />

                <Alert
                  type="warning"
                  showIcon
                  message="Почему Syncthing не вшит в bundle проекта"
                  description="Syncthing живёт своим release cycle, а внутри проекта нам важнее держать чистую on-prem схему без сторонних бинарников в репозитории. Поэтому в bundle оставляем инструкции и официальный путь установки, а само приложение ставим отдельно на машину аналитика."
                />

                <List
                  dataSource={[
                    'Установи Syncthing на каждую машину аналитика.',
                    'После установки открой его web-интерфейс и убедись, что сервис реально запустился.',
                    'Создай папку обмена, например `/Users/<user>/team-exchange` на macOS или `C:\\team-exchange` на Windows.',
                    'Дальше свяжи машины между собой: на машине A скопируй её Device ID, на машине B скопируй её Device ID, затем на обеих машинах нажми `Add Remote Device` и добавь друг друга по этим ID.',
                    'Когда устройства увидели друг друга, на одной из машин нажми `Add Folder`, укажи локальный путь к папке обмена и отметь вторую машину в списке `Share With`.',
                    'На второй машине появится предложение принять эту папку. Подтверди её, укажи свой локальный путь к этой же папке обмена и сохрани настройки.',
                    'Проверь, что на обеих машинах папка стала `Up to Date`. Для быстрой проверки положи в неё тестовый `.md` файл и дождись, пока он появится на второй стороне.',
                    'Укажи этот путь выше в поле «Путь к папке обмена», сохрани настройки и перезапусти стек через `./start.command`.',
                    'Для разбора incoming-файлов используем один рекомендуемый инструмент: встроенный `VS Code Compare`, отдельный diff-клиент не нужен.',
                  ]}
                  renderItem={(item) => <List.Item>{item}</List.Item>}
                />

                <ProCard type="inner" title="Подробный сценарий: машина A ↔ машина B">
                  <List
                    dataSource={[
                      '1. На машине A и на машине B установи и запусти Syncthing.',
                      '2. Открой web-интерфейс Syncthing на обеих машинах. Обычно он открывается автоматически в браузере после старта.',
                      '3. На машине A найди её `Device ID` и скопируй его. На машине B сделай то же самое.',
                      '4. На машине A нажми `Add Remote Device`, вставь `Device ID` машины B, при желании укажи человекочитаемое имя и сохрани.',
                      '5. На машине B повтори то же самое для машины A. Связь двусторонняя: одного добавления недостаточно.',
                      '6. Когда обе машины добавлены друг к другу, на одной из них нажми `Add Folder`.',
                      '7. В `Folder Path` укажи путь к папке обмена, например `/Users/<user>/team-exchange` или `C:\\team-exchange`.',
                      '8. В `Share With` отметь вторую машину и сохрани папку.',
                      '9. На второй машине появится запрос на добавление общей папки. Подтверди его и укажи локальный путь, где эта папка должна лежать у тебя.',
                      '10. Дождись статуса `Up to Date` на обеих машинах. Если хочешь проверить руками, создай тестовый файл `sync-test.md` и убедись, что он доехал на вторую машину.',
                      '11. Только после этого укажи путь к этой папке в настройках нашего приложения и перезапусти стек через `./start.command`.',
                    ]}
                    renderItem={(item) => <List.Item>{item}</List.Item>}
                  />
                </ProCard>
              </Space>
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
      {hasChanges ? (
        <div
          style={{
            position: 'fixed',
            right: 24,
            bottom: 24,
            zIndex: 1000,
            width: 'min(560px, calc(100vw - 32px))',
            background: '#ffffff',
            border: '1px solid #d9d9d9',
            borderRadius: 12,
            boxShadow: '0 12px 40px rgba(0, 0, 0, 0.12)',
            padding: 16,
          }}
        >
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <div>
              <Typography.Text strong>Есть несохранённые изменения</Typography.Text>
              <br />
              <Typography.Text type="secondary">
                Сохранить можно в любом промежуточном состоянии, даже если ты заполнил только одно поле. Недостающие настройки можно добавить позже.
              </Typography.Text>
            </div>
            <Divider style={{ margin: 0 }} />
            <Space wrap>
              <Button type="primary" loading={saving} onClick={() => void handleSave()}>
                Сохранить
              </Button>
              <Button onClick={resetToSavedState} disabled={saving}>
                Вернуть сохранённое
              </Button>
            </Space>
          </Space>
        </div>
      ) : null}
    </PageContainer>
  );
}
