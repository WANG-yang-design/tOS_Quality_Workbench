from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class VersionCreate(BaseModel):
    """创建版本请求模型"""
    version_name: str
    jira_project: str = "TOS"
    jira_fix_version: Optional[str] = None
    owner_name: str = "未配置"
    is_train_version: bool = False
    is_pad: bool = False
    utp_owner_codes: Optional[str] = ""
    baseline_date: Optional[str] = None
    branch_name: Optional[str] = None
    device_count: Optional[int] = 6
    device_list: Optional[str] = ""
    coverage_scope: Optional[str] = "手机+PAD"
    project_status: Optional[str] = "进行中"
    feishu_sheet_url: Optional[str] = ""
    perf_sheet_url: Optional[str] = ""
    battery_sheet_url: Optional[str] = ""
    alm_space_bid: Optional[str] = ""
    alm_app_bid: Optional[str] = ""
    owner_code: Optional[str] = ""

class VersionUpdate(BaseModel):
    """更新版本请求模型"""
    version_name: Optional[str] = None
    jira_project: Optional[str] = None
    jira_fix_version: Optional[str] = None
    owner_name: Optional[str] = None
    is_train_version: Optional[bool] = None
    is_pad: Optional[bool] = None
    utp_owner_codes: Optional[str] = None
    baseline_date: Optional[str] = None
    branch_name: Optional[str] = None
    device_count: Optional[int] = None
    device_list: Optional[str] = None
    coverage_scope: Optional[str] = None
    project_status: Optional[str] = None
    feishu_sheet_url: Optional[str] = None
    perf_sheet_url: Optional[str] = None
    battery_sheet_url: Optional[str] = None
    alm_space_bid: Optional[str] = None
    alm_app_bid: Optional[str] = None
    owner_code: Optional[str] = None

class StageUpdate(BaseModel):
    """更新阶段请求模型"""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    current_flag: Optional[int] = None

class CredentialSave(BaseModel):
    """保存凭据请求模型"""
    jira_base_url: str = "http://jira.transsion.com"
    username: str
    password_or_token: str

class SyncRequest(BaseModel):
    """同步请求模型"""
    use_mock: bool = False
    force_full: bool = False  # 强制全量同步（忽略本地缓存，重新抓取全部数据）

class StageBatchUpdate(BaseModel):
    """批量更新阶段请求模型"""
    stages: List[Dict[str, Any]]

class FeishuImportRequest(BaseModel):
    """飞书导入请求模型"""
    feishu_url: str
    sheet_id: Optional[str] = None

class FeishuConfigSave(BaseModel):
    """保存飞书配置请求模型"""
    app_id: str
    app_secret: str

class StabilityDataCreate(BaseModel):
    """创建稳定性数据请求模型"""
    device_name: str
    rom_version: Optional[str] = ""
    sys_apr_value: Optional[str] = ""
    sys_apr_threshold: Optional[str] = ""
    sys_apr_duration: Optional[str] = ""
    app_apr_value: Optional[str] = ""
    app_apr_threshold: Optional[str] = ""
    app_apr_duration: Optional[str] = ""
    subsys_apr_value: Optional[str] = ""
    subsys_apr_threshold: Optional[str] = ""
    subsys_apr_duration: Optional[str] = ""
    third_apr_value: Optional[str] = ""
    third_apr_threshold: Optional[str] = ""
    third_apr_duration: Optional[str] = ""
    jira_keys: Optional[str] = ""
    remark: Optional[str] = ""

class StabilityDataUpdate(BaseModel):
    """更新稳定性数据请求模型"""
    rom_version: Optional[str] = None
    sys_apr_value: Optional[str] = None
    sys_apr_threshold: Optional[str] = None
    sys_apr_duration: Optional[str] = None
    app_apr_value: Optional[str] = None
    app_apr_threshold: Optional[str] = None
    app_apr_duration: Optional[str] = None
    subsys_apr_value: Optional[str] = None
    subsys_apr_threshold: Optional[str] = None
    subsys_apr_duration: Optional[str] = None
    third_apr_value: Optional[str] = None
    third_apr_threshold: Optional[str] = None
    third_apr_duration: Optional[str] = None
    jira_keys: Optional[str] = None
    remark: Optional[str] = None

class TestPlanCreate(BaseModel):
    """创建测试计划请求模型"""
    device_name: str
    test_items: Optional[str] = ""
    plan_status: Optional[str] = "planned"
    plan_start_date: Optional[str] = ""
    plan_end_date: Optional[str] = ""
    responsible_person: Optional[str] = ""
    remark: Optional[str] = ""

class TestPlanUpdate(BaseModel):
    """更新测试计划请求模型"""
    test_items: Optional[str] = None
    plan_status: Optional[str] = None
    plan_start_date: Optional[str] = None
    plan_end_date: Optional[str] = None
    responsible_person: Optional[str] = None
    remark: Optional[str] = None

class ValuePointCreate(BaseModel):
    """创建价值点请求模型"""
    value_name: str
    ir_conclusion: Optional[str] = "PASS"
    fail_reason: Optional[str] = ""
    test_owner: Optional[str] = ""

class ValuePointUpdate(BaseModel):
    """更新价值点请求模型"""
    value_name: Optional[str] = None
    ir_conclusion: Optional[str] = None
    fail_reason: Optional[str] = None
    test_owner: Optional[str] = None

class ALMConfigSave(BaseModel):
    """保存ALM配置请求模型"""
    uac_gateway: Optional[str] = None
    alm_app_id: Optional[str] = None
    uac_username: Optional[str] = None
    password: Optional[str] = None
    uac_source: Optional[str] = None
    alm_base_url: Optional[str] = None
    alm_space_bid: Optional[str] = None
    alm_app_bid: Optional[str] = None

class AIConfigSave(BaseModel):
    """保存AI配置请求模型"""
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    user_no: Optional[str] = None
    user_name: Optional[str] = None
    user_dept: Optional[str] = None
    sr_ai_prompt: Optional[str] = None

class JiraFilterUpdate(BaseModel):
    """更新Jira过滤器请求模型"""
    custom_jql: Optional[str] = None


class StabilityDeviceData(BaseModel):
    """稳定性设备数据模型"""
    device_name: str
    rom_version: Optional[str] = ""
    sys_apr_value: Optional[str] = ""
    sys_apr_threshold: Optional[str] = ""
    sys_apr_duration: Optional[str] = ""
    app_apr_value: Optional[str] = ""
    app_apr_threshold: Optional[str] = ""
    app_apr_duration: Optional[str] = ""
    subsys_apr_value: Optional[str] = ""
    subsys_apr_threshold: Optional[str] = ""
    subsys_apr_duration: Optional[str] = ""
    third_apr_value: Optional[str] = ""
    third_apr_threshold: Optional[str] = ""
    third_apr_duration: Optional[str] = ""
    jira_keys: Optional[str] = ""
    remark: Optional[str] = ""


class TestPlanData(BaseModel):
    """测试计划数据模型"""
    device_name: str
    test_items: Optional[str] = ""
    plan_status: Optional[str] = "planned"
    plan_start_date: Optional[str] = ""
    plan_end_date: Optional[str] = ""
    responsible_person: Optional[str] = ""
    remark: Optional[str] = ""


class ValuePointData(BaseModel):
    """价值点数据模型"""
    value_name: str
    ir_conclusion: Optional[str] = "PASS"
    fail_reason: Optional[str] = ""
    test_owner: Optional[str] = ""