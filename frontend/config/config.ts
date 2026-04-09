import { defineConfig } from '@umijs/max';

export default defineConfig({
  npmClient: 'npm',
  layout: {
    title: 'Analytics AI Kit',
    locale: false,
  },
  routes: [
    {
      path: '/',
      component: '@/pages/Workbench',
    },
  ],
});
