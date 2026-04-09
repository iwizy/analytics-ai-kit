export type EnvironmentSnapshot = {
  settings: {
    confluence_base_url: string;
    confluence_login: string;
    has_confluence_password: boolean;
    vscode_ready: boolean;
    continue_ready: boolean;
    model_profile: string;
    templates_mode?: string;
  };
  readiness: {
    confluence_ready: boolean;
    vscode_ready: boolean;
    continue_ready: boolean;
    models_ready: boolean;
    article_ready: boolean;
    all_ready: boolean;
    missing_items: string[];
  };
  recommended_profiles: Array<{
    key: string;
    title: string;
    description: string;
    continue_model: string;
    pipeline_hint: string;
  }>;
  commands: {
    start: string;
    stop: string;
    power_mode: string;
  };
};
