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
  model_plan: {
    profile_key: string;
    required_models: string[];
    ready_models: string[];
    missing_models: string[];
    deferred_models: string[];
    download_models: string[];
    draft_model: string;
    review_model: string;
    refine_model: string;
    continue_model: string;
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
    required_models: string[];
    deferred_models: string[];
    draft_model: string;
    review_model: string;
    refine_model: string;
  }>;
  commands: {
    start: string;
    stop: string;
    power_mode: string;
  };
};
