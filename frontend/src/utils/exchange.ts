export type ExchangeBundle = {
  bundle_id: string;
  created_at: string;
  created_by: string;
  description: string;
  type: string;
  categories: string[];
  file_count: number;
  imported: boolean;
  imported_at: string;
  has_conflicts: boolean;
  conflict_count: number;
  path_label: string;
};

export type ExchangeStatus = {
  status: string;
  configured_path: string;
  mounted_path: string;
  mounted: boolean;
  requires_restart: boolean;
  syncthing_ready: boolean;
  auto_scan: boolean;
  poll_interval_sec: number;
  doc_path: string;
  recommended_diff_tool: {
    key: string;
    title: string;
    description: string;
  };
  local_sources: Array<{
    key: string;
    title: string;
    repo_path: string;
    file_count: number;
  }>;
  new_bundles_count: number;
  total_bundles_count: number;
  last_scan_at: string;
  bundles: ExchangeBundle[];
};
