import React, { useEffect, useMemo, useState } from 'react';
import { Link, Outlet, useLocation } from '@umijs/max';
import {
  CheckCircleOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  SettingOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { Alert, Badge, Layout, Menu, Space, Tag, Typography } from 'antd';
import type { MenuProps } from 'antd';

import { apiRequest } from '@/utils/api';
import type { EnvironmentSnapshot } from '@/utils/environment';

const { Content, Sider } = Layout;

export default function AppLayout() {
  const location = useLocation();
  const [environment, setEnvironment] = useState<EnvironmentSnapshot | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const snapshot = await apiRequest<EnvironmentSnapshot>('/ui/environment-settings');
        if (active) {
          setEnvironment(snapshot);
        }
      } catch {
        if (active) {
          setEnvironment(null);
        }
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), 8000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [location.pathname]);

  const taskLocked = environment ? !environment.readiness.article_ready : false;
  const contextWarning = environment ? !environment.readiness.all_ready : false;

  const items = useMemo<MenuProps['items']>(() => [
    {
      key: '/environment',
      icon: <SettingOutlined />,
      label: <Link to="/environment">Подготовка окружения</Link>,
    },
    {
      key: '/task',
      icon: <FileTextOutlined />,
      disabled: taskLocked,
      label: taskLocked ? 'Подготовка статьи' : <Link to="/task">Подготовка статьи</Link>,
    },
    {
      key: '/models-docs',
      icon: <DatabaseOutlined />,
      label: (
        <Link to="/models-docs">
          <Space size={8}>
            <span>Модели и контекст</span>
            <Badge color={contextWarning ? '#ff4d4f' : '#52c41a'} />
          </Space>
        </Link>
      ),
    },
  ], [contextWarning, taskLocked]);

  const selectedKey = location.pathname.startsWith('/models-docs')
    ? '/models-docs'
    : location.pathname.startsWith('/task')
      ? '/task'
      : '/environment';

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={300} theme="light" style={{ borderRight: '1px solid #f0f0f0', paddingTop: 20 }}>
        <div style={{ padding: '0 20px 20px' }}>
          <Typography.Title level={4} style={{ marginBottom: 8 }}>
            Analytics AI Kit
          </Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            Слева теперь три понятных режима: сначала готовим окружение, потом статью, а техническое состояние держим отдельно в «Модели и контекст».
          </Typography.Paragraph>
        </div>
        <Menu mode="inline" selectedKeys={[selectedKey]} items={items} style={{ borderInlineEnd: 'none' }} />
        <div style={{ padding: 20 }}>
          {environment ? (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Tag color={environment.readiness.all_ready ? 'success' : 'error'} icon={environment.readiness.all_ready ? <CheckCircleOutlined /> : <StopOutlined />}>
                {environment.readiness.all_ready ? 'Окружение готово' : 'Есть незавершенная подготовка'}
              </Tag>
              {taskLocked ? (
                <Alert
                  type="warning"
                  showIcon
                  message="Подготовка статьи пока недоступна"
                  description="Сначала заполни настройки Confluence, отметь готовность VS Code и Continue и скачай обязательные модели."
                />
              ) : null}
            </Space>
          ) : (
            <Alert type="info" showIcon message="Статус окружения загружается" />
          )}
        </div>
      </Sider>
      <Layout>
        <Content style={{ padding: 24, background: '#f5f7fa' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
