import { defineConfig } from '@umijs/max';

export default defineConfig({
  npmClient: 'npm',
  mfsu: false,
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
