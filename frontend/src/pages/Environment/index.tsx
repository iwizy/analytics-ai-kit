import React, { useEffect, useMemo, useState } from 'react';
import { CheckCircleOutlined, DownloadOutlined, LinkOutlined, ToolOutlined } from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import {
  Alert,
  Button,
  Checkbox,
  Descriptions,
  Form,
  Input,
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
  model_profile: string;
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
      model_profile: payload.settings.model_profile || 'powerful',
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
      subTitle="Здесь мы один раз настраиваем доступы, локальные инструменты и модельный профиль. Пока этот шаг не завершён, подготовка статьи будет заблокирована."
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
        ) : (
          <Alert type="info" showIcon message="Загружаю настройки окружения" />
        )}

        <ProCard gutter={16} wrap>
          <ProCard colSpan={{ xs: 24, xl: 15 }} title="1. Доступ к Confluence" bordered>
            <Typography.Paragraph>
              Здесь сохраняются базовый адрес Confluence и твои учётные данные. После этого в статье ты будешь вставлять только ссылки, без повторного ввода логина и пароля.
            </Typography.Paragraph>
            <Form form={form} layout="vertical" onFinish={saveSettings} initialValues={{ model_profile: 'powerful' }}>
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

              <Typography.Title level={5}>3. Рекомендация по модели</Typography.Title>
              <Typography.Paragraph type="secondary">
                Эта настройка пока больше про подсказку для аналитика и Continue. Для мощного Mac оставляем тяжёлый профиль, для более слабых машин можно выбрать вариант полегче.
              </Typography.Paragraph>
              <Form.Item label="Профиль производительности" name="model_profile">
                <Radio.Group optionType="button" buttonStyle="solid">
                  <Radio.Button value="light">Лёгкий</Radio.Button>
                  <Radio.Button value="standard">Стандартный</Radio.Button>
                  <Radio.Button value="powerful">Мощный</Radio.Button>
                </Radio.Group>
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
              </Descriptions>

              <Alert
                type="info"
                showIcon
                message="Шаблоны не даём обычному аналитику"
                description="Подложить шаблон task.md можно из статьи, но редактирование самих шаблонов оставляем для power mode во VS Code. Это отдельный слой администрирования, а не часть обычного analyst flow."
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

              {selectedProfile ? (
                <ProCard type="inner" title={selectedProfile.title}>
                  <Typography.Paragraph>{selectedProfile.description}</Typography.Paragraph>
                  <Tag color="blue" icon={<ToolOutlined />}>Continue: {selectedProfile.continue_model}</Tag>
                  <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                    {selectedProfile.pipeline_hint}
                  </Typography.Paragraph>
                </ProCard>
              ) : null}
            </Space>
          </ProCard>
        </ProCard>

        <ProCard title="Что дальше после сохранения" bordered>
          <List
            dataSource={[
              'Открой «Модели и контекст» и проверь, что обязательные модели скачаны. Если нет, там же будет кнопка загрузки и прогресс.',
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

            <ProCard type="inner" title="1. Подготовить VS Code">
              <List
                dataSource={[
                  'Установи Visual Studio Code, если он ещё не установлен.',
                  'Открой проект локально: `code /Users/iwizard/Dev/analytics-ai-kit` или просто запусти `./power-mode.command <task-id>` после подготовки handoff.',
                  'Проверь, что команда `code` доступна в терминале. На macOS это обычно делается через Command Palette → `Shell Command: Install code command in PATH`.',
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
                  'После настройки вернись сюда и отметь галочку, что Continue готов.',
                ]}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
            </ProCard>

            <ProCard type="inner" title="3. Как работать после handoff">
              <List
                dataSource={[
                  'Сначала собери задачу в UI: task.md, контекст, draft, gaps, refine.',
                  'Нажми `Prepare handoff`, чтобы система создала handoff-файл и рабочую копию черновика.',
                  'Запусти `./power-mode.command <task-id>`: он откроет проект, свежий handoff и рабочую копию в VS Code.',
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
