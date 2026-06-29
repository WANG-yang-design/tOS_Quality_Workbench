# -*- coding: utf-8 -*-
"""Agent tools: definitions (JSON Schema) and executors."""
import json
from typing import Any, Dict

# ============================================================
# Tool definitions for LLM function calling
# ============================================================

AGENT_TOOLS = [
    # ===== 数据刷新工具 =====
    {
        "type": "function",
        "function": {
            "name": "refresh_jira_data",
            "description": (
                "Refresh Jira data from Jira server. This will sync all issues for the current version. "
                "Use when user wants to update/sync Jira issues. Returns sync result with counts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "force": {
                        "type": "boolean",
                        "description": "Force full refresh even if recently synced. Default false."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "refresh_sr_data",
            "description": (
                "Refresh SR (Service Request) data from ALM platform. "
                "Updates locked SR list and SR issue cache. Returns sync result."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "refresh_utp_data",
            "description": (
                "Refresh UTP (Unified Test Platform) data including weekly reports and test plan progress. "
                "Returns sync result."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "refresh_all_data",
            "description": (
                "Refresh all data sources: Jira + SR + UTP. Use when user wants a full data update. "
                "Returns combined sync results."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    # ===== 数据导出工具 =====
    {
        "type": "function",
        "function": {
            "name": "export_issues_to_excel",
            "description": (
                "Export Jira issues to Excel file. Use filter_key to select issue type. "
                "Returns download URL for the Excel file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_key": {
                        "type": "string",
                        "enum": ["open_reopen", "submitted_modifying", "pending_verification", "main_sync", "all"],
                        "description": "Which issues to export. Default: all"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max issues to export. Default: 500"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "export_sr_list_to_excel",
            "description": (
                "Export SR (Service Request) list to Excel file. "
                "Returns download URL for the Excel file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "include_ai_analysis": {
                        "type": "boolean",
                        "description": "Include AI risk analysis in export. Default true."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "export_weekly_report",
            "description": (
                "Generate and export weekly report as Markdown file. "
                "Includes all key metrics, risks, trends, and recommendations. "
                "Returns download URL and report content."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "export_custom_data",
            "description": (
                "Export custom data to CSV file. Use this when you need to export filtered/subset data "
                "that is not covered by other export tools. "
                "For example: export only high-risk SRs, export issues from specific modules, etc. "
                "You must provide the column definitions and row data. "
                "Returns download URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Export filename (without extension), e.g. 'high_risk_srs', 'stability_issues'"
                    },
                    "title": {
                        "type": "string",
                        "description": "Title/description for the export, shown in download message"
                    },
                    "columns": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {"type": "string", "description": "Field key in row data"},
                                "header": {"type": "string", "description": "Column header display name"}
                            },
                            "required": ["key", "header"]
                        },
                        "description": "Column definitions for the CSV"
                    },
                    "rows": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Array of data rows, each row is an object with keys matching column keys"
                    }
                },
                "required": ["filename", "columns", "rows"]
            }
        }
    },
    # ===== 查询工具 =====
    {
        "type": "function",
        "function": {
            "name": "query_jira_issues",
            "description": (
                "Query Jira issues for the current version/stage. "
                "Use filter_key to choose query type: open_reopen (Open/Reopened), "
                "submitted_modifying (Submitted/Modifying), pending_verification (Resolved/Verified), "
                "main_sync (all bugs). Returns issue list with key, summary, status, priority, assignee, aging_days."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_key": {
                        "type": "string",
                        "enum": ["open_reopen", "submitted_modifying", "pending_verification", "main_sync"],
                        "description": "Query type filter"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return, default 30"
                    }
                },
                "required": ["filter_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_analysis_metrics",
            "description": (
                "Get comprehensive risk analysis metrics for current version/stage. "
                "Returns: total/closed/unresolved issue counts, close ratio, high-priority counts, "
                "must-fix stats, status distribution, top risk modules, top risk owners."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sr_locked_summary",
            "description": (
                "Get ALM locked SR summary: total count, status breakdown (INITIALIZE/DESIGNING/DEVELOPING/TESTING/UAT/COMPLETED), "
                "today new count, this week new count."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sr_details",
            "description": (
                "Get SR requirement details from ALM: sr_coding, sr_name, issue_count, "
                "test_module_owners, planned_acceptance date, AI risk level. "
                "Use risk_level to filter: high/medium/low/all."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_level": {
                        "type": "string",
                        "enum": ["high", "medium", "low", "all"],
                        "description": "Filter by AI risk level, default all"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_utp_weekly_report",
            "description": (
                "Get UTP Weekly test report: sub-domain PASS/FAIL counts, case pass rate, "
                "defect counts (A/B/C/D class), domain-level results. "
                "Optionally filter by platform (MTK/Q)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "enum": ["MTK", "Q"],
                        "description": "Filter by platform"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_trend_data",
            "description": (
                "Get weekly trend data: per-week created/closed/net/cumulative_open counts. "
                "Useful for comparing week-over-week changes."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_custom_risks",
            "description": "Get user-defined custom risk items (title, level, owner, plan_close_date, status).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_custom_risk",
            "description": "Add a new custom risk item to the platform.",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_level": {"type": "string", "enum": ["high", "medium", "low"], "description": "Risk level"},
                    "title": {"type": "string", "description": "Risk title"},
                    "description": {"type": "string", "description": "Detailed description"},
                    "owner": {"type": "string", "description": "Person responsible"},
                    "plan_close_date": {"type": "string", "description": "Planned close date YYYY-MM-DD"}
                },
                "required": ["risk_level", "title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stability_data",
            "description": "Get stability test data: device names, ROM versions, APR values (system/app/subsystem/third-party).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_jira_issue_detail",
            "description": (
                "Get detailed info for a specific Jira issue by key (e.g. TOS170-2954). "
                "Returns: summary, status, priority, assignee, reporter, created_time, aging_days, must_fix, severity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Jira issue key, e.g. TOS170-2954"}
                },
                "required": ["issue_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_test_activities",
            "description": (
                "Get key test activities for a specific stage. Returns activity list with name, status (pass/fail/unconfirmed), "
                "operator, employee_id, remark, updated_at. Also returns stats (total/pass/fail/unconfirmed/completion_rate)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stage": {
                        "type": "string",
                        "description": "Stage name: 概念启动/STR1/STR2/STR3/STR4/STR4A/STR5/1+N版本火车. Leave empty for current stage."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_work_hours",
            "description": (
                "Get work hours data: person name, test hours, regression hours, other hours, total. "
                "Returns data list and AI analysis if available."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sr_test_progress",
            "description": (
                "Get SR test progress from UTP: matching SRs in TESTING status with their UTP test plan execution progress. "
                "Returns SR list with progress percentage, test plan info."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_utp_plan_progress",
            "description": (
                "Get UTP test plan progress: plan name, status (INIT/RUNNING/COMPLETED/INVALID), execute schedule %, "
                "test stage, level, creator, end time. Returns stats (total/completed/in_progress/not_started/avg_progress)."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_locked_sr_list",
            "description": (
                "Get ALM locked SR list with life cycle status (INITIALIZE/DESIGNING/DEVELOPING/TESTING/UAT/COMPLETED). "
                "Returns SR list with sr_coding, sr_name, life_cycle_name, priority, test_representative, tag."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by life cycle status: TESTING/COMPLETED/etc. Leave empty for all."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_jira_trend_comparison",
            "description": (
                "Get Jira trend analysis comparing current version with predecessor version. "
                "Returns overall metrics comparison, convergence analysis, module trends, "
                "submit/resolve chart data, and AI analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stage": {
                        "type": "string",
                        "description": "Stage name for comparison. Default: current stage."
                    }
                }
            }
        }
    },
    # ===== 新增查询工具 =====
    {
        "type": "function",
        "function": {
            "name": "get_performance_data",
            "description": (
                "Get performance test data: device names, benchmark scores (AnTuTu/GeekBench/3DMark), "
                "comparison with baseline. Returns device list with scores."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_battery_data",
            "description": (
                "Get battery/power consumption test data: device names, battery life, charging time, "
                "power consumption metrics. Returns device list with metrics."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_value_points",
            "description": (
                "Get value point verification data: value point names, IR conclusion (PASS/FAIL), "
                "fail reason, test owner. Returns value point list with status."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stage_schedule",
            "description": (
                "Get stage schedule/configuration: stage names (概念启动/STR1-STR5/STR4A/1+N版本火车), "
                "start dates, end dates, current flag. Returns stage list."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_custom_risk",
            "description": "Delete a custom risk item by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_id": {"type": "integer", "description": "Risk item ID to delete"}
                },
                "required": ["risk_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_test_activity",
            "description": (
                "Update test activity status. Use to mark activities as pass/fail/unconfirmed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stage": {"type": "string", "description": "Stage name"},
                    "activity_index": {"type": "integer", "description": "Activity index (0-based)"},
                    "status": {"type": "string", "enum": ["pass", "fail", "unconfirmed"], "description": "New status"},
                    "operator": {"type": "string", "description": "Operator name"},
                    "remark": {"type": "string", "description": "Remark"}
                },
                "required": ["stage", "activity_index", "status"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_version_info",
            "description": (
                "Get current version configuration: version name, Jira project, owner, "
                "branch name, device count, coverage scope, project status."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_report",
            "description": (
                "Get or generate daily SR risk report. Returns SR summary, high/medium/low risk SRs, "
                "blocker/critical issues, top owners, AI analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "generate": {
                        "type": "boolean",
                        "description": "Force regenerate report. Default false (use cached)."
                    }
                }
            }
        }
    },
]


# ============================================================
# Tool executor
# ============================================================

def execute_tool(name: str, args: Dict[str, Any], version_id: int, stage: str) -> Any:
    """Execute a tool by name and return the result as a JSON-serializable dict."""
    try:
        # ===== 数据刷新工具 =====
        if name == "refresh_jira_data":
            return _refresh_jira_data(version_id, args)
        elif name == "refresh_sr_data":
            return _refresh_sr_data(version_id)
        elif name == "refresh_utp_data":
            return _refresh_utp_data(version_id)
        elif name == "refresh_all_data":
            return _refresh_all_data(version_id)
        # ===== 数据导出工具 =====
        elif name == "export_issues_to_excel":
            return _export_issues_to_excel(version_id, stage, args)
        elif name == "export_sr_list_to_excel":
            return _export_sr_list_to_excel(version_id, args)
        elif name == "export_weekly_report":
            return _export_weekly_report(version_id, stage)
        elif name == "export_custom_data":
            return _export_custom_data(args)
        # ===== 原有查询工具 =====
        elif name == "query_jira_issues":
            return _query_jira_issues(version_id, stage, args)
        elif name == "get_analysis_metrics":
            return _get_analysis_metrics(version_id, stage)
        elif name == "get_sr_locked_summary":
            return _get_sr_locked_summary(version_id)
        elif name == "get_sr_details":
            return _get_sr_details(version_id, args)
        elif name == "get_utp_weekly_report":
            return _get_utp_weekly_report(version_id, args)
        elif name == "get_trend_data":
            return _get_trend_data(version_id, stage)
        elif name == "get_custom_risks":
            return _get_custom_risks(version_id)
        elif name == "add_custom_risk":
            return _add_custom_risk(version_id, args)
        elif name == "get_stability_data":
            return _get_stability_data(version_id)
        elif name == "get_jira_issue_detail":
            return _get_jira_issue_detail(version_id, stage, args)
        elif name == "get_test_activities":
            return _get_test_activities(version_id, stage, args)
        elif name == "get_work_hours":
            return _get_work_hours(version_id)
        elif name == "get_sr_test_progress":
            return _get_sr_test_progress(version_id)
        elif name == "get_utp_plan_progress":
            return _get_utp_plan_progress(version_id)
        elif name == "get_locked_sr_list":
            return _get_locked_sr_list(version_id, args)
        elif name == "get_jira_trend_comparison":
            return _get_jira_trend_comparison(version_id, stage, args)
        # ===== 新增查询工具 =====
        elif name == "get_performance_data":
            return _get_performance_data(version_id)
        elif name == "get_battery_data":
            return _get_battery_data(version_id)
        elif name == "get_value_points":
            return _get_value_points(version_id)
        elif name == "get_stage_schedule":
            return _get_stage_schedule(version_id)
        elif name == "delete_custom_risk":
            return _delete_custom_risk(version_id, args)
        elif name == "update_test_activity":
            return _update_test_activity(version_id, args)
        elif name == "get_version_info":
            return _get_version_info(version_id)
        elif name == "get_daily_report":
            return _get_daily_report(version_id, args)
        else:
            return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        return {"error": f"Tool {name} failed: {str(e)[:200]}"}


# ============================================================
# Tool implementations (internal calls, no HTTP)
# ============================================================

def _query_jira_issues(version_id: int, stage: str, args: dict) -> dict:
    from ..database import get_conn
    filter_key = args.get("filter_key", "open_reopen")
    limit = min(args.get("limit", 200), 500)  # 增加默认返回数量
    conn = get_conn()
    cur = conn.cursor()
    # Build WHERE based on filter_key
    conditions = ["version_id = ?"]
    params: list = [version_id]
    if stage and stage != "ALL":
        conditions.append("str_stage = ?")
        params.append(stage)
    if filter_key == "open_reopen":
        conditions.append("status IN ('Open','Reopened')")
    elif filter_key == "submitted_modifying":
        conditions.append("status IN ('Submitted','Modifying')")
    elif filter_key == "pending_verification":
        conditions.append("status IN ('Resolved','Verified')")
    # main_sync: no extra filter
    where = " AND ".join(conditions)
    cur.execute(
        f"SELECT issue_key, summary, status, priority, assignee, aging_days, must_fix_flag, module_name "
        f"FROM jira_issue_cache WHERE {where} ORDER BY "
        f"CASE priority WHEN 'Blocker' THEN 0 WHEN 'Critical' THEN 1 WHEN 'Major' THEN 2 ELSE 3 END, "
        f"aging_days DESC LIMIT ?",
        params + [limit],
    )
    rows = [dict(r) for r in cur.fetchall()]
    cur.execute(f"SELECT COUNT(*) as c FROM jira_issue_cache WHERE {where}", params)
    total = cur.fetchone()["c"]
    conn.close()
    return {"filter": filter_key, "total": total, "returned": len(rows), "issues": rows}


def _get_analysis_metrics(version_id: int, stage: str) -> dict:
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT metrics_json, risks_json FROM analysis_snapshot WHERE version_id=? AND str_stage=? "
        "ORDER BY created_at DESC LIMIT 1",
        (version_id, stage),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"error": "No analysis data. Please sync Jira first."}
    metrics = json.loads(row["metrics_json"]) if row["metrics_json"] else {}
    risks = json.loads(row["risks_json"]) if row["risks_json"] else {}
    return {
        "total_issues": metrics.get("total_issue_count", 0),
        "closed": metrics.get("closed_issue_count", 0),
        "unresolved": metrics.get("unresolved_issue_count", 0),
        "close_ratio": metrics.get("close_new_ratio", 0),
        "high_unresolved": metrics.get("high_unresolved_count", 0),
        "must_fix_open": metrics.get("must_fix_pending_count", 0),
        "open_reopen": metrics.get("open_reopen_count", 0),
        "top_modules": (risks.get("top_modules") or [])[:5],
        "top_owners": (risks.get("top_owners") or [])[:5],
    }


def _get_sr_locked_summary(version_id: int) -> dict:
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT total_count, status_json, synced_at FROM alm_locked_sr_snapshot WHERE version_id=?", (version_id,))
    snap = cur.fetchone()
    if not snap:
        conn.close()
        return {"cached": False, "total": 0, "message": "No SR data. Click 'From ALM' to refresh."}
    status = json.loads(snap["status_json"]) if snap["status_json"] else {}
    # Get today/week new counts
    from datetime import datetime, timedelta
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    weekday = now.weekday()
    week_start_str = (now - timedelta(days=weekday)).strftime("%Y-%m-%d")
    cur.execute("SELECT sr_codings_json FROM alm_locked_sr_daily_snapshot WHERE version_id=? AND snapshot_date=?", (version_id, today_str))
    today_row = cur.fetchone()
    today_codings = set(json.loads(today_row["sr_codings_json"])) if today_row and today_row["sr_codings_json"] else set()
    cur.execute("SELECT sr_codings_json FROM alm_locked_sr_daily_snapshot WHERE version_id=? AND snapshot_date=?", (version_id, yesterday_str))
    yest_row = cur.fetchone()
    yest_codings = set(json.loads(yest_row["sr_codings_json"])) if yest_row and yest_row["sr_codings_json"] else set()
    cur.execute("SELECT sr_codings_json FROM alm_locked_sr_daily_snapshot WHERE version_id=? AND snapshot_date=?", (version_id, week_start_str))
    week_row = cur.fetchone()
    week_codings = set(json.loads(week_row["sr_codings_json"])) if week_row and week_row["sr_codings_json"] else set()
    conn.close()
    today_new = len(today_codings - yest_codings) if yest_codings else 0
    week_new = len(today_codings - week_codings) if week_codings else len(today_codings)
    return {
        "total": snap["total_count"],
        "status_breakdown": status,
        "today_new": today_new,
        "week_new": week_new,
        "synced_at": snap["synced_at"],
    }


def _get_sr_details(version_id: int, args: dict) -> dict:
    from ..database import get_conn
    risk_level = args.get("risk_level", "all")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT d.sr_coding, d.sr_name, d.issue_count, d.test_module_owners_display, "
        "d.planned_acceptance, p.risk_level, p.analysis "
        "FROM sr_detail_cache d LEFT JOIN sr_ai_priority p "
        "ON d.version_id = p.version_id AND d.sr_coding = p.sr_coding "
        "WHERE d.version_id = ? AND d.is_other_version = 0 "
        "ORDER BY d.issue_count DESC",
        (version_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    if risk_level != "all":
        rows = [r for r in rows if (r.get("risk_level") or "").lower() == risk_level]
    return {"total": len(rows), "sr_list": rows[:200]}  # 增加返回数量


def _get_utp_weekly_report(version_id: int, args: dict) -> dict:
    from ..database import get_conn
    platform_filter = args.get("platform")
    conn = get_conn()
    cur = conn.cursor()
    if platform_filter:
        cur.execute("SELECT data_json FROM utp_weekly_cache WHERE version_id=? AND platform=?", (version_id, platform_filter))
    else:
        cur.execute("SELECT platform, data_json FROM utp_weekly_cache WHERE version_id=?", (version_id,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return {"error": "No UTP data. Click 'From UTP' to refresh."}
    results = []
    for row in rows:
        d = json.loads(row["data_json"])
        tasks = d.get("group_tasks") or []
        sub_pass = sum(1 for t in tasks if (t.get("sub_result") or "").upper() == "PASS")
        sub_fail = sum(1 for t in tasks if (t.get("sub_result") or "").upper() in ("FAIL", "NG"))
        results.append({
            "platform": d.get("platform", row.get("platform", "")),
            "report_result": d.get("report_result", ""),
            "case_count": d.get("case_count", {}),
            "jira_count": d.get("jira_count", {}),
            "sub_domain_pass": sub_pass,
            "sub_domain_fail": sub_fail,
            "sub_domain_total": len(tasks),
        })
    return {"platforms": results}


def _get_trend_data(version_id: int, stage: str) -> dict:
    from ..database import get_conn
    from ..routers.versions import get_version
    version = get_version(version_id)
    if not version:
        return {"error": "Version not found"}
    conn = get_conn()
    cur = conn.cursor()
    where = "version_id = ?"
    params: list = [version_id]
    if stage and stage != "ALL":
        where += " AND str_stage = ?"
        params.append(stage)
    cur.execute(f"SELECT created_time, updated_time, status, resolved_time FROM jira_issue_cache WHERE {where}", params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    # Group by ISO week
    from collections import defaultdict
    weekly = defaultdict(lambda: {"created": 0, "closed": 0})
    for r in rows:
        ct = (r.get("created_time") or "")[:10]
        if ct:
            try:
                from datetime import datetime
                d = datetime.fromisoformat(ct)
                iso = d.isocalendar()
                key = f"{iso[0]}-W{iso[1]:02d}"
                weekly[key]["created"] += 1
            except Exception:
                pass
        rt = (r.get("resolved_time") or "")[:10]
        if rt:
            try:
                from datetime import datetime
                d = datetime.fromisoformat(rt)
                iso = d.isocalendar()
                key = f"{iso[0]}-W{iso[1]:02d}"
                weekly[key]["closed"] += 1
            except Exception:
                pass
    sorted_weeks = sorted(weekly.keys())[-8:]  # last 8 weeks
    trend = []
    cumulative = 0
    for w in sorted_weeks:
        c = weekly[w]["created"]
        cl = weekly[w]["closed"]
        net = c - cl
        cumulative += net
        trend.append({"week": w, "created": c, "closed": cl, "net": net, "cumulative_open": max(cumulative, 0)})
    return {"weeks": trend}


def _get_custom_risks(version_id: int) -> dict:
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, risk_level, title, description, owner, plan_close_date, status FROM custom_risks "
        "WHERE version_id=? ORDER BY CASE risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END",
        (version_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"total": len(rows), "risks": rows}


def _add_custom_risk(version_id: int, args: dict) -> dict:
    from ..database import get_conn
    from ..utils import now_iso
    if not args.get("title", "").strip():
        return {"error": "title is required"}
    conn = get_conn()
    cur = conn.cursor()
    ts = now_iso()
    cur.execute(
        "INSERT INTO custom_risks (version_id,risk_level,title,description,owner,plan_close_date,status,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (version_id, args.get("risk_level", "medium"), args["title"], args.get("description", ""),
         args.get("owner", ""), args.get("plan_close_date", ""), "open", ts, ts),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Risk '{args['title']}' added."}


def _get_stability_data(version_id: int) -> dict:
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM stability_data WHERE version_id=?", (version_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"total": len(rows), "devices": rows}


def _get_jira_issue_detail(version_id: int, stage: str, args: dict) -> dict:
    from ..database import get_conn
    issue_key = args.get("issue_key", "")
    if not issue_key:
        return {"error": "issue_key is required"}
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT issue_key, summary, status, priority, assignee, reporter, module_name, "
        "created_time, updated_time, aging_days, stale_days, must_fix, severity, grade "
        "FROM jira_issue_cache WHERE version_id=? AND issue_key=?",
        (version_id, issue_key),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"error": f"Issue {issue_key} not found in local cache."}
    return dict(row)


def _get_test_activities(version_id: int, stage: str, args: dict) -> dict:
    from ..routers.test_activities import STAGE_ACTIVITIES, ensure_activities_exist
    from ..database import get_conn
    target_stage = args.get("stage", "") or stage
    if not target_stage or target_stage == "ALL":
        target_stage = "STR3"
    conn = get_conn()
    ensure_activities_exist(conn, version_id, target_stage)
    cur = conn.cursor()
    cur.execute(
        "SELECT activity_name, status, operator, employee_id, remark, updated_at "
        "FROM test_activities WHERE version_id=? AND stage_name=? ORDER BY activity_index",
        (version_id, target_stage),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    total = len(rows)
    pass_n = sum(1 for r in rows if r["status"] == "pass")
    fail_n = sum(1 for r in rows if r["status"] == "fail")
    unconf = total - pass_n - fail_n
    fail_items = [r for r in rows if r["status"] == "fail"]
    return {
        "stage": target_stage, "total": total, "pass": pass_n, "fail": fail_n,
        "unconfirmed": unconf, "completion_rate": round(pass_n / total * 100, 1) if total else 0,
        "fail_items": fail_items, "activities": rows,
    }


def _get_work_hours(version_id: int) -> dict:
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT data_json, ai_analysis FROM work_hours WHERE version_id=?", (version_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"data": [], "ai_analysis": "", "message": "No work hours data imported yet."}
    data = json.loads(row["data_json"]) if row["data_json"] else []
    total_test = sum(r.get("test_hours", 0) for r in data)
    total_reg = sum(r.get("regression_hours", 0) for r in data)
    total_other = sum(r.get("other_hours", 0) for r in data)
    return {
        "total_records": len(data), "total_test_hours": total_test,
        "total_regression_hours": total_reg, "total_other_hours": total_other,
        "total_hours": total_test + total_reg + total_other,
        "ai_analysis": row["ai_analysis"] or "", "data": data[:30],
    }


def _get_sr_test_progress(version_id: int) -> dict:
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM utp_sr_progress_cache WHERE version_id=? ORDER BY execute_schedule ASC", (version_id,))
    rows = [dict(r) for r in cur.fetchall()]
    # Also get testing SRs from locked SR
    cur.execute(
        "SELECT sr_coding, sr_name, life_cycle_name FROM alm_locked_sr_cache "
        "WHERE version_id=? AND (life_cycle_name='测试' OR life_cycle_code='TESTING')",
        (version_id,),
    )
    testing_srs = [dict(r) for r in cur.fetchall()]
    conn.close()
    utp_map = {}
    for r in rows:
        if r.get("sr_coding"):
            utp_map[r["sr_coding"]] = r["execute_schedule"]
    matched = []
    for sr in testing_srs:
        coding = sr["sr_coding"]
        matched.append({
            "sr_coding": coding, "sr_name": sr["sr_name"],
            "progress": utp_map.get(coding),
        })
    return {
        "testing_sr_total": len(testing_srs), "with_progress": sum(1 for m in matched if m["progress"] is not None),
        "sr_list": matched[:30],
    }


def _get_utp_plan_progress(version_id: int) -> dict:
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT plan_name, plan_status, execute_schedule, test_stage, level, created_by_name, end_time, warning_status "
        "FROM utp_plan_cache WHERE version_id=? ORDER BY plan_status, execute_schedule ASC",
        (version_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    total = len(rows)
    done = sum(1 for r in rows if (r.get("execute_schedule") or 0) >= 100)
    return {"total": total, "completed": done, "plans": rows[:100]}  # 增加返回数量


def _get_locked_sr_list(version_id: int, args: dict) -> dict:
    from ..database import get_conn
    status_filter = (args.get("status") or "").strip()
    conn = get_conn()
    cur = conn.cursor()
    if status_filter:
        cur.execute(
            "SELECT sr_coding, sr_name, life_cycle_name, life_cycle_code, priority, test_representative, tag "
            "FROM alm_locked_sr_cache WHERE version_id=? AND (life_cycle_name=? OR life_cycle_code=?)",
            (version_id, status_filter, status_filter),
        )
    else:
        cur.execute(
            "SELECT sr_coding, sr_name, life_cycle_name, life_cycle_code, priority, test_representative, tag "
            "FROM alm_locked_sr_cache WHERE version_id=?",
            (version_id,),
        )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"total": len(rows), "filter": status_filter or "all", "sr_list": rows[:200]}  # 增加返回数量


def _get_jira_trend_comparison(version_id: int, stage: str, args: dict) -> dict:
    from ..services.trend_analysis_service import build_trend_analysis
    target_stage = args.get("stage", "") or stage or "ALL"
    result = build_trend_analysis(version_id, target_stage, use_cache=True, refresh_ai=False, force=False)
    # Strip large chart data to save tokens
    for key in ("submit", "resolve"):
        if key in result and "chart_data" in result[key]:
            result[key]["chart_data_count"] = len(result[key].pop("chart_data", []))
    return result


# ============================================================
# New tool implementations
# ============================================================

def _refresh_jira_data(version_id: int, args: dict) -> dict:
    """刷新Jira数据"""
    from ..routers.jira import sync_jira_data
    force = args.get("force", False)
    try:
        result = sync_jira_data(version_id, force=force)
        return {"success": True, "message": "Jira数据刷新完成", "details": result}
    except Exception as e:
        return {"success": False, "error": f"刷新失败: {str(e)[:200]}"}


def _refresh_sr_data(version_id: int) -> dict:
    """刷新SR数据"""
    from ..routers.alm_locked_sr import refresh_locked_srs
    try:
        result = refresh_locked_srs(version_id)
        return {"success": True, "message": "SR数据刷新完成", "details": result}
    except Exception as e:
        return {"success": False, "error": f"刷新失败: {str(e)[:200]}"}


def _refresh_utp_data(version_id: int) -> dict:
    """刷新UTP数据"""
    from ..routers.utp_weekly import refresh_utp_reports
    try:
        result = refresh_utp_reports(version_id)
        return {"success": True, "message": "UTP数据刷新完成", "details": result}
    except Exception as e:
        return {"success": False, "error": f"刷新失败: {str(e)[:200]}"}


def _refresh_all_data(version_id: int) -> dict:
    """刷新所有数据"""
    results = {}
    # 刷新Jira
    try:
        from ..routers.jira import sync_jira_data
        results["jira"] = sync_jira_data(version_id, force=False)
    except Exception as e:
        results["jira"] = {"error": str(e)[:100]}
    # 刷新SR
    try:
        from ..routers.alm_locked_sr import refresh_locked_srs
        results["sr"] = refresh_locked_srs(version_id)
    except Exception as e:
        results["sr"] = {"error": str(e)[:100]}
    # 刷新UTP
    try:
        from ..routers.utp_weekly import refresh_utp_reports
        results["utp"] = refresh_utp_reports(version_id)
    except Exception as e:
        results["utp"] = {"error": str(e)[:100]}
    return {"success": True, "message": "全量数据刷新完成", "details": results}


def _export_issues_to_excel(version_id: int, stage: str, args: dict) -> dict:
    """导出问题到Excel"""
    from ..database import get_conn
    import os
    import csv
    import io
    from datetime import datetime

    filter_key = args.get("filter_key", "all")
    limit = min(args.get("limit", 500), 1000)

    conn = get_conn()
    cur = conn.cursor()
    conditions = ["version_id = ?"]
    params = [version_id]
    if stage and stage != "ALL":
        conditions.append("str_stage = ?")
        params.append(stage)
    if filter_key == "open_reopen":
        conditions.append("status IN ('Open','Reopened')")
    elif filter_key == "submitted_modifying":
        conditions.append("status IN ('Submitted','Modifying')")
    elif filter_key == "pending_verification":
        conditions.append("status IN ('Resolved','Verified')")

    where = " AND ".join(conditions)
    cur.execute(
        f"SELECT issue_key, summary, status, priority, assignee, module_name, aging_days, "
        f"created_time, resolved_time FROM jira_issue_cache WHERE {where} "
        f"ORDER BY CASE priority WHEN 'Blocker' THEN 0 WHEN 'Critical' THEN 1 WHEN 'Major' THEN 2 ELSE 3 END "
        f"LIMIT ?",
        params + [limit]
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        return {"success": False, "message": "没有可导出的数据"}

    # 生成CSV内容
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["issue_key", "summary", "status", "priority", "assignee", "module_name", "aging_days", "created_time", "resolved_time"])
    writer.writeheader()
    writer.writerows(rows)

    # 保存到导出目录
    from ..routers.agent import EXPORT_DIR
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"jira_issues_{filter_key}_{date_str}.csv"
    filepath = os.path.join(EXPORT_DIR, filename)
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        f.write(output.getvalue())

    download_url = f"/api/agent/export/{filename}"
    return {
        "success": True,
        "message": f"已导出 {len(rows)} 条问题",
        "filename": filename,
        "download_url": download_url,
        "count": len(rows)
    }


def _export_sr_list_to_excel(version_id: int, args: dict) -> dict:
    """导出SR列表到Excel"""
    from ..database import get_conn
    import os
    import csv
    import io
    from datetime import datetime

    include_ai = args.get("include_ai_analysis", True)
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT sr_coding, sr_name, life_cycle_name, priority, test_representative, tag "
        "FROM alm_locked_sr_cache WHERE version_id=?",
        (version_id,)
    )
    rows = [dict(r) for r in cur.fetchall()]

    if include_ai:
        cur.execute(
            "SELECT sr_coding, risk_level, analysis FROM sr_ai_priority WHERE version_id=?",
            (version_id,)
        )
        ai_map = {r["sr_coding"]: dict(r) for r in cur.fetchall()}
        for row in rows:
            ai = ai_map.get(row["sr_coding"], {})
            row["risk_level"] = ai.get("risk_level", "")
            row["ai_analysis"] = ai.get("analysis", "")

    conn.close()

    if not rows:
        return {"success": False, "message": "没有可导出的SR数据"}

    # 生成CSV
    output = io.StringIO()
    fields = ["sr_coding", "sr_name", "life_cycle_name", "priority", "test_representative", "tag"]
    if include_ai:
        fields.extend(["risk_level", "ai_analysis"])
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

    from ..routers.agent import EXPORT_DIR
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sr_list_{date_str}.csv"
    filepath = os.path.join(EXPORT_DIR, filename)
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        f.write(output.getvalue())

    download_url = f"/api/agent/export/{filename}"
    return {
        "success": True,
        "message": f"已导出 {len(rows)} 条SR",
        "filename": filename,
        "download_url": download_url,
        "count": len(rows)
    }


def _export_weekly_report(version_id: int, stage: str) -> dict:
    """生成并导出周报"""
    from ..routers.agent import api_generate_weekly_report, EXPORT_DIR
    import os
    from datetime import datetime
    try:
        result = api_generate_weekly_report({"version_id": version_id, "stage": stage})
        report_content = result.get("report", "")
        filename = result.get("filename", f"weekly_report_{datetime.now().strftime('%Y%m%d')}.md")

        # 保存到导出目录
        filepath = os.path.join(EXPORT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report_content)

        download_url = f"/api/agent/export/{filename}"
        return {
            "success": True,
            "message": "周报生成完成，可下载",
            "filename": filename,
            "download_url": download_url,
            "report_preview": report_content[:500] + "..."
        }
    except Exception as e:
        return {"success": False, "error": f"周报生成失败: {str(e)[:200]}"}


def _export_custom_data(args: dict) -> dict:
    """导出自定义数据到CSV"""
    import os
    import csv
    import io
    from datetime import datetime

    filename_prefix = args.get("filename", "custom_export")
    title = args.get("title", "自定义导出")
    columns = args.get("columns", [])
    rows = args.get("rows", [])

    if not columns:
        return {"success": False, "error": "columns 不能为空"}
    if not rows:
        return {"success": False, "error": "rows 不能为空，没有数据可导出"}

    # 生成CSV
    output = io.StringIO()
    fieldnames = [col["key"] for col in columns]
    headers = {col["key"]: col.get("header", col["key"]) for col in columns}

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    # 写入自定义表头
    writer.writerow(headers)
    writer.writerows(rows)

    from ..routers.agent import EXPORT_DIR
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{date_str}.csv"
    filepath = os.path.join(EXPORT_DIR, filename)
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        f.write(output.getvalue())

    download_url = f"/api/agent/export/{filename}"
    return {
        "success": True,
        "message": f"已导出 {title}（{len(rows)} 条）",
        "filename": filename,
        "download_url": download_url,
        "count": len(rows)
    }


def _get_performance_data(version_id: int) -> dict:
    """获取性能数据"""
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM stability_data WHERE version_id=?", (version_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    # 性能数据可能在stability_data表或其他表中
    return {"total": len(rows), "devices": rows, "message": "性能数据来自稳定性数据表"}


def _get_battery_data(version_id: int) -> dict:
    """获取续航数据"""
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM stability_data WHERE version_id=?", (version_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"total": len(rows), "devices": rows, "message": "续航数据来自稳定性数据表"}


def _get_value_points(version_id: int) -> dict:
    """获取价值点数据"""
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT value_name, ir_conclusion, fail_reason, test_owner, updated_at "
        "FROM value_points WHERE version_id=? ORDER BY ir_conclusion",
        (version_id,)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    total = len(rows)
    passed = sum(1 for r in rows if r.get("ir_conclusion") == "PASS")
    failed = total - passed
    return {"total": total, "passed": passed, "failed": failed, "value_points": rows}


def _get_stage_schedule(version_id: int) -> dict:
    """获取阶段时间表"""
    from ..database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT stage_name, start_date, end_date, current_flag "
        "FROM str_stage_config WHERE version_id=? ORDER BY "
        "CASE stage_name WHEN '概念启动' THEN 0 WHEN 'STR1' THEN 1 WHEN 'STR2' THEN 2 "
        "WHEN 'STR3' THEN 3 WHEN 'STR4' THEN 4 WHEN 'STR4A' THEN 5 WHEN 'STR5' THEN 6 "
        "WHEN '1+N版本火车' THEN 7 ELSE 8 END",
        (version_id,)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    current = next((r["stage_name"] for r in rows if r.get("current_flag")), None)
    return {"stages": rows, "current_stage": current}


def _delete_custom_risk(version_id: int, args: dict) -> dict:
    """删除自定义风险项"""
    from ..database import get_conn
    risk_id = args.get("risk_id")
    if not risk_id:
        return {"error": "risk_id is required"}
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM custom_risks WHERE id=? AND version_id=?", (risk_id, version_id))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return {"success": deleted, "message": "风险项已删除" if deleted else "未找到风险项"}


def _update_test_activity(version_id: int, args: dict) -> dict:
    """更新测试活动状态"""
    from ..database import get_conn
    from ..utils import now_iso

    stage = args.get("stage")
    index = args.get("activity_index")
    status = args.get("status")
    operator = args.get("operator", "")
    remark = args.get("remark", "")

    if not stage or index is None or not status:
        return {"error": "stage, activity_index, and status are required"}

    conn = get_conn()
    cur = conn.cursor()
    ts = now_iso()
    cur.execute(
        "UPDATE test_activities SET status=?, operator=?, remark=?, updated_at=? "
        "WHERE version_id=? AND stage_name=? AND activity_index=?",
        (status, operator, remark, ts, version_id, stage, index)
    )
    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return {"success": updated, "message": f"测试活动已更新为 {status}" if updated else "未找到测试活动"}


def _get_version_info(version_id: int) -> dict:
    """获取版本信息"""
    from ..routers.versions import get_version
    version = get_version(version_id)
    if not version:
        return {"error": "Version not found"}
    return {
        "version_name": version.get("version_name"),
        "jira_project": version.get("jira_project"),
        "jira_fix_version": version.get("jira_fix_version"),
        "owner_name": version.get("owner_name"),
        "branch_name": version.get("branch_name"),
        "device_count": version.get("device_count"),
        "coverage_scope": version.get("coverage_scope"),
        "project_status": version.get("project_status"),
        "is_train_version": version.get("is_train_version"),
        "is_pad": version.get("is_pad"),
    }


def _get_daily_report(version_id: int, args: dict) -> dict:
    """获取或生成每日报告"""
    from ..database import get_conn
    import json as _json

    generate = args.get("generate", False)
    conn = get_conn()
    cur = conn.cursor()

    if not generate:
        # 尝试获取缓存的报告
        cur.execute(
            "SELECT data_json, generated_at FROM sr_daily_risk_report "
            "WHERE version_id=? ORDER BY generated_at DESC LIMIT 1",
            (version_id,)
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return {"cached": True, "data": _json.loads(row["data_json"]), "generated_at": row["generated_at"]}

    # 生成新报告
    try:
        from ..routers.sr_progress import generate_daily_risk_report
        result = generate_daily_risk_report(version_id, include_ai=True)
        return {"cached": False, "data": result.get("data"), "generated_at": result.get("generated_at")}
    except Exception as e:
        return {"error": f"报告生成失败: {str(e)[:200]}"}