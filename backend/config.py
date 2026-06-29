from pathlib import Path

# ==============================
# 应用目录配置
# ==============================
APP_DIR = Path.home() / ".tos_quality_workbench"
DB_PATH = APP_DIR / "tos_quality.db"
KEY_PATH = APP_DIR / "secret.key"

# ==============================
# Jira 状态配置
# ==============================
CLOSED_STATUS = {
    "Closed", "Done", "Resolved", "Verified",
    "关闭", "已解决", "已验证",
    "无法复现", "延期处理", "重复问题", "By Design", "Won't Fix", "Duplicate"
}

# 所有已知的状态列表（用于统计和展示）
ALL_KNOWN_STATUS = {
    "Open", "In Progress", "Reopened", "Submitted", "Modifying",
    "测试执行中", "重新打开", "测试中",
    "Closed", "Done", "Resolved", "Verified",
    "关闭", "已解决", "已验证",
    "无法复现", "延期处理", "重复问题", "By Design", "Won't Fix", "Duplicate"
}

HIGH_PRIORITY = {"Blocker", "Critical", "Major", "Highest", "High", "P0", "P1", "严重", "高"}

# 默认Jira服务器地址
DEFAULT_JIRA_BASE_URL = "http://jira.transsion.com"

# ==============================
# Jira 自定义字段配置
# ==============================
JIRA_CUSTOM_FIELDS = {
    "must_fix": "customfield_15400",      # 必解标签 (MP Block / Not MP Block)
    "android_version": "customfield_13100",  # Android版本
    "os_version": "customfield_13101",       # OS版本
    "model": "customfield_15302",            # 机型/项目 (如 X6878)
    "severity": "customfield_13004",         # 严重程度/等级
    "issue_category": "customfield_10203",   # 问题类别 (如 Stability)
    "frequency": "customfield_10204",        # 出现概率 (如 Often)
    "test_type": "customfield_10900",        # 测试类型
    "migration": "customfield_11101",        # 迁移/处理结论
    "sr_feature": "customfield_13800",       # SR/特性关联
    "system_category": "customfield_15205",  # 系统分类
    "module_category": "customfield_14907",  # 模块分类
    "solution_type": "customfield_14102",    # 解决方式
    "project_code": "customfield_14205",     # 项目代号
}

# Jira API 请求的字段列表
JIRA_SEARCH_FIELDS = [
    "summary", "status", "project", "reporter", "assignee", "priority",
    "components", "labels", "created", "updated", "resolution", "resolutiondate",
    "versions", "fixVersions", "issuetype", "description", "comment",
    # 自定义字段
    "customfield_15400", "customfield_13100", "customfield_13101",
    "customfield_15302", "customfield_13004", "customfield_10203",
    "customfield_10204", "customfield_10900", "customfield_11101",
    "customfield_13800", "customfield_15205", "customfield_14907",
    "customfield_14102", "customfield_14205",
]