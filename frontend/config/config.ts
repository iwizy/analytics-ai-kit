import { defineConfig } from '@umijs/max';

export default defineConfig({
  npmClient: 'npm',
  mfsu: false,
  layout: {
    title: 'Analytics AI Kit',
    locale: false,
  },
  routes: [
    {
      path: '/',
      redirect: '/task',
    },
    {
      path: '/task',
      name: 'Подготовка статьи',
      component: '@/pages/Workbench',
    },
    {
      path: '/models-docs',
      name: 'Модели и контекст',
      component: '@/pages/ModelsDocs',
    },
  ],
});
