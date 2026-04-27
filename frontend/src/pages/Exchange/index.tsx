import React, { useEffect, useMemo, useState } from 'react';
import { CloudDownloadOutlined, ExportOutlined, ReloadOutlined, WarningOutlined } from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import {
  Alert,
  Button,
  Checkbox,
  Descriptions,
  Form,
  Input,
  List,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';

import { apiRequest } from '@/utils/api';
import type { EnvironmentSnapshot } from '@/utils/environment';
import type { ExchangeStatus } from '@/utils/exchange';

type ExchangeStatusPayload = {
  status: string;
  exchange: ExchangeStatus;
};

type PublishForm = {
  author: string;
  description: string;
  categories: string[];
};

type ImportPayload = {
  status: string;
  imported: Array<{
    bundle_id: string;
    copied: string[];
    skipped: string[];
    conflicts: Array<{
      target: string;
      incoming: string;
    }>;
  }>;
  exchange: ExchangeStatus;
};

export default function ExchangePage() {
  const [form] = Form.useForm<PublishForm>();
  const [environment, setEnvironment] = useState<EnvironmentSnapshot | null>(null);
  const [exchange, setExchange] = useState<ExchangeStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function refreshAll() {
    const [environmentPayload, exchangePayload] = await Promise.all([
      apiRequest<EnvironmentSnapshot>('/ui/environment-settings'),
      apiRequest<ExchangeStatusPayload>('/ui/exchange/status'),
    ]);
    setEnvironment(environmentPayload);
    setExchange(exchangePayload.exchange);
    const currentValues = form.getFieldsValue();
    form.setFieldsValue({
      author: currentValues.author || environmentPayload.settings.confluence_login || 'analyst',
      description: currentValues.description || '',
      categories: currentValues.categories?.length ? currentValues.categories : ['context', 'templates', 'glossary'],
    });
  }

  useEffect(() => {
    void refreshAll();
  }, []);

  useEffect(() => {
    if (!exchange?.auto_scan) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      void refreshAll();
    }, exchange.poll_interval_sec * 1000);
    return () => window.clearInterval(timer);
  }, [exchange?.auto_scan, exchange?.poll_interval_sec]);

  const pendingBundles = useMemo(() => (exchange?.bundles || []).filter((item) => !item.imported), [exchange]);

  async function publish(values: PublishForm) {
    setBusy('publish');
    try {
      const payload = await apiRequest<ExchangeStatusPayload>('/ui/exchange/publish', {
        method: 'POST',
        body: JSON.stringify(values),
      });
      setExchange(payload.exchange);
      message.success('Bundle с локальными изменениями опубликован');
      form.setFieldValue('description', '');
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Не удалось опубликовать bundle');
    } finally {
      setBusy(null);
    }
  }

  async function importBundles(bundleIds?: string[]) {
    setBusy('import');
    try {
      const payload = await apiRequest<ImportPayload>('/ui/exchange/import', {
        method: 'POST',
        body: JSON.stringify({ bundle_ids: bundleIds || [] }),
      });
      setExchange(payload.exchange);
      const conflicts = payload.imported.reduce((sum, item) => sum + item.conflicts.length, 0);
      if (conflicts) {
        message.warning(`Импорт завершён, но есть ${conflicts} конфликт(ов). Разбери их через VS Code Compare.`);
      } else {
        message.success('Bundle-пакеты импортированы локально');
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Не удалось импортировать bundle');
    } finally {
      setBusy(null);
    }
  }

  return (
    <PageContainer
      title="Обмен контекстом"
      subTitle="Здесь живёт обмен общим контекстом проекта между аналитиками без облака и без git: только локальная папка обмена, Syncthing и bundle-пакеты."
      extra={[
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => void refreshAll()}>
          Проверить обновления
        </Button>,
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {exchange ? (
          <Alert
            type={exchange.new_bundles_count ? 'warning' : 'success'}
            showIcon
            message={exchange.new_bundles_count ? `Найдено новых bundle-пакетов: ${exchange.new_bundles_count}` : 'Новых bundle-пакетов пока нет'}
            description={
              exchange.requires_restart
                ? `Сначала перезапусти стек через ./start.command, чтобы сервис начал смотреть в ${exchange.configured_path}.`
                : 'Система сравнивает папку обмена с локальным import-state и показывает только новые или конфликтные пакеты.'
            }
          />
        ) : null}

        <ProCard gutter={16} wrap>
          <ProCard colSpan={{ xs: 24, xl: 10 }} title="Статус обмена" bordered>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="Настроенный путь">
                <Typography.Text code>{exchange?.configured_path || '—'}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Сейчас смонтировано в сервис">
                <Typography.Text code>{exchange?.mounted_path || '—'}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Syncthing">
                <Tag color={environment?.settings.syncthing_ready ? 'success' : 'default'}>
                  {environment?.settings.syncthing_ready ? 'Готов' : 'Не подтверждён'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Рекомендуемый diff">
                <Typography.Text>{exchange?.recommended_diff_tool.title || 'VS Code Compare'}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Инструкция">
                <Typography.Text code>{exchange?.doc_path || 'docs/team-exchange.md'}</Typography.Text>
              </Descriptions.Item>
            </Descriptions>

            {exchange?.requires_restart ? (
              <Alert
                style={{ marginTop: 16 }}
                type="warning"
                showIcon
                message="Нужен перезапуск стека"
                description="Ты уже сохранил новый путь к папке обмена, но Docker ещё смотрит в старый каталог. После ./start.command всё переключится."
              />
            ) : null}

            <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>
              Для конфликтов используем один стандарт: `VS Code Compare`. Если импорт создаст incoming-файл, открой обычный и incoming-файл в сравнении, перенеси нужные правки и удали incoming-версию.
            </Typography.Paragraph>
          </ProCard>

          <ProCard colSpan={{ xs: 24, xl: 14 }} title="Что публикуем в обмен" bordered>
            <List
              dataSource={exchange?.local_sources || []}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Tag key="count" color="blue">
                      {item.file_count} файлов
                    </Tag>,
                  ]}
                >
                  <List.Item.Meta
                    title={item.title}
                    description={<Typography.Text code>{item.repo_path}</Typography.Text>}
                  />
                </List.Item>
              )}
            />
          </ProCard>
        </ProCard>

        <ProCard title="Найденные bundle-пакеты" bordered extra={
          <Button
            type="primary"
            icon={<CloudDownloadOutlined />}
            loading={busy === 'import'}
            onClick={() => void importBundles()}
            disabled={!pendingBundles.length}
          >
            Забрать все новые
          </Button>
        }>
          <Table
            rowKey="bundle_id"
            pagination={false}
            dataSource={exchange?.bundles || []}
            columns={[
              {
                title: 'Bundle',
                dataIndex: 'bundle_id',
                key: 'bundle_id',
                render: (value: string, record: ExchangeStatus['bundles'][number]) => (
                  <Space direction="vertical" size={2}>
                    <Typography.Text strong>{value}</Typography.Text>
                    <Typography.Text type="secondary">{record.description || 'Без описания'}</Typography.Text>
                  </Space>
                ),
              },
              {
                title: 'Автор',
                dataIndex: 'created_by',
                key: 'created_by',
              },
              {
                title: 'Содержимое',
                key: 'categories',
                render: (_: unknown, record: ExchangeStatus['bundles'][number]) => record.categories.join(', ') || '—',
              },
              {
                title: 'Статус',
                key: 'status',
                render: (_: unknown, record: ExchangeStatus['bundles'][number]) => (
                  <Space wrap>
                    <Tag color={record.imported ? 'success' : 'processing'}>
                      {record.imported ? 'Уже импортирован' : 'Новый'}
                    </Tag>
                    {record.has_conflicts ? (
                      <Tag color="warning" icon={<WarningOutlined />}>
                        Конфликты: {record.conflict_count}
                      </Tag>
                    ) : null}
                  </Space>
                ),
              },
              {
                title: 'Действие',
                key: 'action',
                render: (_: unknown, record: ExchangeStatus['bundles'][number]) => (
                  <Button
                    size="small"
                    disabled={record.imported}
                    loading={busy === 'import'}
                    onClick={() => void importBundles([record.bundle_id])}
                  >
                    Перенести к себе
                  </Button>
                ),
              },
            ]}
          />
        </ProCard>

        <ProCard title="Опубликовать свои локальные изменения" bordered>
          <Form form={form} layout="vertical" onFinish={publish}>
            <Form.Item label="Автор публикации" name="author" rules={[{ required: true, message: 'Укажи имя автора bundle' }]}>
              <Input placeholder="ivanov" />
            </Form.Item>
            <Form.Item label="Короткое описание" name="description">
              <Input placeholder="Например: обновил контекст по интеграции с биллингом" />
            </Form.Item>
            <Form.Item
              label="Что включить в bundle"
              name="categories"
              rules={[{ required: true, message: 'Выбери хотя бы одну категорию' }]}
            >
              <Checkbox.Group
                options={[
                  { label: 'Общий контекст', value: 'context' },
                  { label: 'Шаблоны', value: 'templates' },
                  { label: 'Глоссарий', value: 'glossary' },
                ]}
              />
            </Form.Item>
            <Space wrap>
              <Button type="primary" htmlType="submit" icon={<ExportOutlined />} loading={busy === 'publish'}>
                Опубликовать в папку обмена
              </Button>
              <Typography.Text type="secondary">
                Bundle берётся только из `docs/shared-context`, `docs/templates`, `docs/glossary`.
              </Typography.Text>
            </Space>
          </Form>
        </ProCard>
      </Space>
    </PageContainer>
  );
}
