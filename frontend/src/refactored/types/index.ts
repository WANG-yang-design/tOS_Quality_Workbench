// 从 App.tsx 提取的类型定义 - 原样复制

export type VersionItem = {
  id: number;
  version_name: string;
  jira_project: string;
  jira_fix_version: string;
  owner_name: string;
  is_train_version: number;
  is_pad?: number;
  utp_owner_codes?: string;
  baseline_date?: string;
  branch_name?: string;
  device_count?: number;
  device_list?: string;
  coverage_scope?: string;
  project_status?: string;
  feishu_sheet_url?: string;
  alm_space_bid?: string;
  alm_app_bid?: string;
  owner_code?: string;
  perf_sheet_url?: string;
  battery_sheet_url?: string;
};

export type CredentialStatus = {
  configured: boolean;
  valid: boolean;
  username?: string;
  jira_base_url?: string;
  expire_at?: string;
  message: string;
};

export type Analysis = {
  metrics: any;
  risks: any;
};

export type StabilityDevice = {
  id?: number;
  device_name: string;
  rom_version: string;
  sys_apr_value: string; sys_apr_threshold: string; sys_apr_duration: string;
  app_apr_value: string; app_apr_threshold: string; app_apr_duration: string;
  subsys_apr_value: string; subsys_apr_threshold: string; subsys_apr_duration: string;
  third_apr_value: string; third_apr_threshold: string; third_apr_duration: string;
  jira_keys: string; remark: string;
  updated_at?: string;
};

export const EMPTY_DEVICE: StabilityDevice = {
  device_name: "", rom_version: "",
  sys_apr_value: "", sys_apr_threshold: "", sys_apr_duration: "",
  app_apr_value: "", app_apr_threshold: "", app_apr_duration: "",
  subsys_apr_value: "", subsys_apr_threshold: "", subsys_apr_duration: "",
  third_apr_value: "", third_apr_threshold: "", third_apr_duration: "",
  jira_keys: "", remark: "",
};

export type ValuePoint = {
  id?: number;
  value_name: string;
  ir_conclusion: string;
  fail_reason: string;
  test_owner: string;
  updated_at?: string;
};

export type TestPlan = {
  id?: number;
  device_name: string;
  test_items: string;
  plan_status: string;
  plan_start_date: string;
  plan_end_date: string;
  responsible_person: string;
  remark: string;
};

export const EMPTY_PLAN: TestPlan = {
  device_name: "", test_items: "", plan_status: "planned",
  plan_start_date: "", plan_end_date: "", responsible_person: "", remark: "",
};