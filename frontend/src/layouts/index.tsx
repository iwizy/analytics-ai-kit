import { FileTextOutlined, HddOutlined } from '@ant-design/icons';
import { Outlet, useLocation, useNavigate } from '@umijs/max';
import { Layout, Menu, Space, Typography } from 'antd';

const { Header, Sider, Content } = Layout;

const items = [
  {
    key: '/task',
    icon: <FileTextOutlined />,
    label: 'Подготовка статьи',
  },
  {
    key: '/models-docs',
    icon: <HddOutlined />,
    label: 'Модели и контекст',
  },
];

export default function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={280}
        breakpoint="lg"
        collapsedWidth={0}
        style={{
          background: 'rgba(20, 29, 34, 0.92)',
          backdropFilter: 'blur(10px)',
        }}
      >
        <div style={{ padding: 20, borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <Space direction="vertical" size={2}>
            <Typography.Title level={4} style={{ margin: 0, color: '#f8f4ea' }}>
              Analytics AI Kit
            </Typography.Title>
            <Typography.Text style={{ color: 'rgba(255,255,255,0.65)' }}>
              Рабочее место аналитика
            </Typography.Text>
          </Space>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={items}
          style={{
            marginTop: 12,
            background: 'transparent',
            borderInlineEnd: 'none',
          }}
          onClick={({ key }) => navigate(String(key))}
        />
      </Sider>

      <Layout
        style={{
          background: 'transparent',
          minWidth: 0,
        }}
      >
        <Header
          style={{
            height: 64,
            padding: '0 24px',
            background: 'rgba(255,255,255,0.46)',
            borderBottom: '1px solid rgba(30, 41, 48, 0.08)',
            display: 'flex',
            alignItems: 'center',
            backdropFilter: 'blur(8px)',
          }}
        >
          <Space direction="vertical" size={0}>
            <Typography.Text strong style={{ color: '#173447' }}>
              {location.pathname === '/models-docs' ? 'Модели и контекст' : 'Подготовка статьи'}
            </Typography.Text>
            <Typography.Text type="secondary">
              Интерфейс ведёт аналитика по шагам и сохраняет все результаты в рабочие папки проекта.
            </Typography.Text>
          </Space>
        </Header>

        <Content style={{ minWidth: 0 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
