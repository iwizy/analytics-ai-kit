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
    {
      path: '/context-collection',
      name: 'Сбор контекста',
      component: '@/pages/ContextCollection/index.tsx',
    },
    {
      path: '/review',
      name: 'Ревью аналитики',
      component: '@/pages/Review/index.tsx',
    },
    {
      path: '/exchange',
      name: 'Обмен контекстом',
      component: '@/pages/Exchange/index.tsx',
    },
  ],
});
