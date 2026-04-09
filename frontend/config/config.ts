import { defineConfig } from '@umijs/max';

export default defineConfig({
  npmClient: 'npm',
  mfsu: false,
  devServer: {
    headers: {
      'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
      Pragma: 'no-cache',
      Expires: '0',
      Surrogate-Control: 'no-store',
    },
  },
  routes: [
    { path: '/', redirect: '/environment' },
    {
      path: '/environment',
      name: 'Подготовка окружения',
      component: '@/pages/Environment/index.tsx',
    },
    {
      path: '/task',
      name: 'Подготовка статьи',
      component: '@/pages/Workbench/index.tsx',
    },
    {
      path: '/models-docs',
      name: 'Модели и контекст',
      component: '@/pages/ModelsDocs/index.tsx',
    },
  ],
});
