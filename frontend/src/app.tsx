import React from 'react';
import { App as AntApp, ConfigProvider, theme } from 'antd';

export function rootContainer(container: React.ReactNode) {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#c35f2b',
          colorInfo: '#1c8a84',
          borderRadius: 12,
          fontFamily: '"Space Grotesk", "Avenir Next", "Trebuchet MS", sans-serif',
          colorBgLayout: '#f5efdf',
        },
      }}
    >
      <AntApp>{container}</AntApp>
    </ConfigProvider>
  );
}
