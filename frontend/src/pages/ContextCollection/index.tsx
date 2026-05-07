import React, { useEffect, useState } from 'react';
import { BranchesOutlined, DatabaseOutlined, ReloadOutlined } from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import {
  Alert,
  Button,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';

import { apiRequest } from '@/utils/api';
import type { EnvironmentSnapshot } from '@/utils/environment';

type ContextCollection = {
  collection_id: string;
  title: string;
  root_url: string;
  created_at: string;
  imported_count: number;
  failed_count: number;
  path: string;
};

type CollectionsPayload = {
  status: string;
  collections: ContextCollection[];
};

type CollectResult = CollectionsPayload & {
  collection_id: string;
  collection_path: string;
  index_path: string;
  manifest: {
    title: string;
    root_url: string;
    imported_count: number;
    failed: Array<{
      url: string;
      error: string;
    }>;
    pages: Array<{
      title: string;
      resolved_url: string;
      file_name: string;
      depth: number;
      links_found: number;
    }>;
  };
};

type CollectForm = {
  root_url: string;
  collection_id?: string;
  max_depth: number;
  max_pages: number;
};

export default function ContextCollectionPage() {
  const [form] = Form.useForm<CollectForm>();
  const [environment, setEnvironment] = useState<EnvironmentSnapshot | null>(null);
  const [collections, setCollections] = useState<ContextCollection[]>([]);
  const [latest, setLatest] = useState<CollectResult | null>(null);
  const [collectionError, setCollectionError] = useState('');
  const [busy, setBusy] = useState(false);

  async function refreshAll() {
    const [environmentPayload, collectionsPayload] = await Promise.all([
      apiRequest<EnvironmentSnapshot>('/ui/environment-settings'),
      apiRequest<CollectionsPayload>('/ui/context-collections'),
    ]);
    setEnvironment(environmentPayload);
    setCollections(collectionsPayload.collections);
  }

  useEffect(() => {
    form.setFieldsValue({
      max_depth: 1,
      max_pages: 20,
    });
    void refreshAll();
  }, []);

  async function collect(values: CollectForm) {
    setBusy(true);
    setCollectionError('');
    try {
      const payload = await apiRequest<CollectResult>('/ui/context-collections/collect', {
        method: 'POST',
        body: JSON.stringify(values),
      });
      setLatest(payload);
      setCollections(payload.collections);
      if (payload.manifest.imported_count === 0) {
        setCollectionError('Система не смогла собрать ни одной страницы. Проверь ссылку, доступы Confluence и доступность страницы из сети Docker.');
        message.error('Контекст не собран: 0 доступных страниц');
      } else if (payload.manifest.failed.length) {
        message.warning(`Контекст собран частично: ${payload.manifest.imported_count} страниц, ошибок: ${payload.manifest.failed.length}`);
      } else {
        message.success(`Контекст собран: ${payload.manifest.imported_count} страниц`);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Не удалось собрать контекст';
      setCollectionError(errorMessage);
      message.error(errorMessage);
    } finally {
      setBusy(false);
    }
  }

  const confluenceReady = Boolean(
    environment?.settings.confluence_base_url
      && environment?.settings.confluence_login
      && environment?.settings.has_confluence_password,
  );

  return (
    <PageContainer
      title="Сбор контекста"
      subTitle="Обход Confluence-страницы и связанных дочерних страниц в общий локальный контекст проекта."
      extra={[
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => void refreshAll()}>
          Обновить
        </Button>,
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type={confluenceReady ? 'success' : 'warning'}
          showIcon
          message={confluenceReady ? 'Confluence-доступ настроен' : 'Нужно заполнить настройки Confluence'}
          description={confluenceReady
            ? 'Сбор будет идти от сохранённого локального профиля. Результат попадёт в общий контекст.'
            : 'Перед сбором укажи Base URL, логин и пароль в разделе подготовки окружения.'}
        />

        {collectionError ? (
          <Alert
            type="error"
            showIcon
            closable
            message="Контекст не собран"
            description={collectionError}
            onClose={() => setCollectionError('')}
          />
        ) : null}

        <ProCard gutter={16} wrap>
          <ProCard colSpan={{ xs: 24, xl: 10 }} title="Новый сбор" bordered>
            <Form form={form} layout="vertical" onFinish={collect}>
              <Form.Item
                label="Корневая страница Confluence"
                name="root_url"
                rules={[{ required: true, message: 'Укажи ссылку на страницу Confluence' }]}
              >
                <Input placeholder="https://.../confluence/..." />
              </Form.Item>
              <Form.Item label="ID коллекции" name="collection_id">
                <Input placeholder="Например: billing-integration-context" />
              </Form.Item>
              <Space size={16} align="start" wrap>
                <Form.Item label="Глубина обхода" name="max_depth">
                  <InputNumber min={0} max={3} style={{ width: 160 }} />
                </Form.Item>
                <Form.Item label="Лимит страниц" name="max_pages">
                  <InputNumber min={1} max={50} style={{ width: 160 }} />
                </Form.Item>
              </Space>
              <Button
                type="primary"
                htmlType="submit"
                icon={<BranchesOutlined />}
                loading={busy}
                disabled={!confluenceReady}
              >
                Собрать контекст
              </Button>
            </Form>
          </ProCard>

          <ProCard colSpan={{ xs: 24, xl: 14 }} title="Куда сохраняется" bordered>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="Папка контекста">
                <Typography.Text code>docs/shared-context/confluence_collections</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Индекс коллекции">
                <Typography.Text code>context_index.md</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Manifest">
                <Typography.Text code>manifest.json</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Публикация коллегам">
                <Typography.Text>Через раздел «Обмен контекстом», категория «Общий контекст»</Typography.Text>
              </Descriptions.Item>
            </Descriptions>
            <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>
              Глубина 1 обычно означает корневую страницу и найденные дочерние ссылки. Для больших деревьев лучше увеличивать лимит постепенно.
            </Typography.Paragraph>
          </ProCard>
        </ProCard>

        {latest ? (
          <ProCard title="Последний сбор" bordered>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Alert
                type={latest.manifest.imported_count === 0 ? 'error' : latest.manifest.failed.length ? 'warning' : 'success'}
                showIcon
                message={latest.manifest.imported_count === 0
                  ? 'Не удалось собрать ни одной страницы'
                  : `Собрано страниц: ${latest.manifest.imported_count}`}
                description={latest.manifest.imported_count === 0
                  ? 'Проверь, что страница доступна под сохранённым логином, не требует дополнительной авторизации и открывается из сети Docker.'
                  : `Коллекция: ${latest.collection_id}. Индекс: ${latest.index_path}`}
              />
              {latest.manifest.failed.length ? (
                <Alert
                  type="warning"
                  showIcon
                  message="Некоторые страницы не удалось собрать"
                  description={(
                    <Space direction="vertical" size={6} style={{ width: '100%' }}>
                      {latest.manifest.failed.map((item) => (
                        <Typography.Text key={item.url} type="secondary">
                          <Typography.Text code>{item.url}</Typography.Text>
                          {' '}
                          - {item.error}
                        </Typography.Text>
                      ))}
                    </Space>
                  )}
                />
              ) : null}
              <Table
                rowKey="file_name"
                pagination={false}
                dataSource={latest.manifest.pages}
                columns={[
                  { title: 'Страница', dataIndex: 'title', key: 'title' },
                  { title: 'Глубина', dataIndex: 'depth', key: 'depth', render: (value: number) => <Tag>{value}</Tag> },
                  { title: 'Файл', dataIndex: 'file_name', key: 'file_name', render: (value: string) => <Typography.Text code>{value}</Typography.Text> },
                  { title: 'Ссылок найдено', dataIndex: 'links_found', key: 'links_found' },
                ]}
              />
            </Space>
          </ProCard>
        ) : null}

        <ProCard title="Собранные коллекции" bordered extra={<DatabaseOutlined />}>
          <Table
            rowKey="collection_id"
            pagination={{ pageSize: 8 }}
            dataSource={collections}
            columns={[
              {
                title: 'Коллекция',
                dataIndex: 'collection_id',
                key: 'collection_id',
                render: (value: string, record: ContextCollection) => (
                  <Space direction="vertical" size={2}>
                    <Typography.Text strong>{record.title || value}</Typography.Text>
                    <Typography.Text type="secondary">{value}</Typography.Text>
                  </Space>
                ),
              },
              { title: 'Страниц', dataIndex: 'imported_count', key: 'imported_count' },
              {
                title: 'Ошибок',
                dataIndex: 'failed_count',
                key: 'failed_count',
                render: (value: number) => <Tag color={value ? 'warning' : 'success'}>{value}</Tag>,
              },
              { title: 'Создано', dataIndex: 'created_at', key: 'created_at' },
              {
                title: 'Путь',
                dataIndex: 'path',
                key: 'path',
                render: (value: string) => <Typography.Text code>{value}</Typography.Text>,
              },
            ]}
          />
        </ProCard>
      </Space>
    </PageContainer>
  );
}
