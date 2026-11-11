#!/usr/bin/env python3
"""Create executable API test cases for the SWGD flow-center and monitor services.

The script writes through the AIRETEST REST API so project permissions, change
logs, and assertion persistence follow the same path as the web UI. It is
idempotent by exact title within the target group and previews by default.

Required environment for --apply:
    AIRETEST_USERNAME
    AIRETEST_PASSWORD
    AIRETEST_PROJECT_ID

Optional environment:
    AIRETEST_API_BASE (default: http://127.0.0.1:8000/api/v1)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

FLOW_GROUP = "swgd-imap-flow-center"
MONITOR_GROUP = "swgd-imap-monitor"

FLOW_HEADERS = {"Content-Type": "application/json", "epToken": "{{epToken}}"}
MONITOR_JSON_HEADERS = {"Content-Type": "application/json", "epToken": "{{epToken}}"}
MONITOR_GET_HEADERS = {"epToken": "{{epToken}}"}


def assertion(
    assertion_type: str,
    operator: str,
    expected: str,
    priority: str = "P1",
    expression: str | None = None,
    order: int = 0,
) -> dict[str, Any]:
    return {
        "assertion_type": assertion_type,
        "expression": expression,
        "operator": operator,
        "expected": expected,
        "priority": priority,
        "order": order,
    }


def success_assertions(*extra: dict[str, Any]) -> list[dict[str, Any]]:
    rules = [
        assertion("status_code", "eq", "200", "P0", order=0),
        assertion("json_path", "eq", "200", "P0", "$.code", 1),
        assertion("json_path", "eq", "Success", "P1", "$.message", 2),
    ]
    for index, rule in enumerate(extra, start=len(rules)):
        rule["order"] = index
        rules.append(rule)
    return rules


def error_assertions(*extra: dict[str, Any]) -> list[dict[str, Any]]:
    rules = [
        assertion("status_code", "eq", "200", "P0", order=0),
        assertion("json_path", "ne", "200", "P0", "$.code", 1),
        assertion("json_path", "type", "string", "P2", "$.message", 2),
    ]
    for index, rule in enumerate(extra, start=len(rules)):
        rule["order"] = index
        rules.append(rule)
    return rules


def pagination_assertions(*extra: dict[str, Any]) -> list[dict[str, Any]]:
    return success_assertions(
        assertion("json_path", "type", "number", "P1", "$.data.total"),
        assertion("json_path", "type", "array", "P1", "$.data.rows"),
        *extra,
    )


def description(
    case_id: str,
    priority: str,
    precondition: str,
    data: str,
    steps: str,
    expected: str,
    note: str = "",
) -> str:
    parts = [
        f"用例编号：{case_id}",
        f"优先级：{priority}",
        f"前置条件：{precondition}",
        f"测试数据：{data}",
        f"执行步骤：{steps}",
        f"预期结果：{expected}",
    ]
    if note:
        parts.append(f"注意：{note}")
    return "\n".join(parts)


def case(
    *,
    title: str,
    group: str,
    method: str,
    url: str,
    headers: dict[str, str],
    assertions: list[dict[str, Any]],
    case_id: str,
    priority: str,
    precondition: str,
    data: str,
    expected: str,
    markers: list[str] | None = None,
    body: Any = None,
    note: str = "",
) -> dict[str, Any]:
    return {
        "title": title,
        "description": description(
            case_id,
            priority,
            precondition,
            data,
            "通过 AIRETEST 执行该用例一次，检查 HTTP 状态、业务码和响应字段。",
            expected,
            note,
        ),
        "group_path": group,
        "markers": markers or ["api", "swgd"],
        "method": method,
        "url": url,
        "headers": headers,
        "params": {},
        "body": body,
        "assertions": assertions,
    }


FLOW_SAVE_BODY = {
    "optDesc": "接单",
    "bizType": "swgd_receice_order",
    "optType": "receive",
    "bizId": 10000000001,
    "serialNo": "SWGD202609200001",
    "bizData": '{"agentCode":"AGENT001","tradeCode":"TRADE01"}',
    "source": "SWGD_IMAP",
    "optBy": "zhangsan",
    "optOrgCode": "CUS001",
    "assignName": "测试员",
    "assignCode": "C001,C002",
    "businessTime": "2026-09-20 10:00:00",
    "optTime": "2026-09-20 10:00:00",
}

FLOW_QUERY_API_BODY = {
    "bizType": "swgd_receice_order",
    "between_optTime": "2026-09-01,2026-11-20",
    "optOrgCode": "CUS001",
    "serialNo": "SWGD202609200001",
    "source": "SWGD_IMAP",
    "optType": "receive,delete",
    "cusTomCode": "C001",
    "limit": 10,
    "offset": 1,
}

FLOW_RECEIVE_QUERY_BODY = {
    "bizType": "swgd_receice_order",
    "serialNo": "SWGD202609200002",
    "status": "receive",
    "billNo": "BL20260920001",
    "agentCode": "AGENT001",
    "tradeCode": "TRADE01",
    "cooperateCode": "COOP01",
    "iEMark": "I",
    "settlementCode": "SETTLE01",
    "receiveDate": "2026-09-01,2026-09-20",
    "preEntryId": "EDI20260920001",
    "offset": 1,
    "limit": 10,
}

FTP_MONITOR_NEW = {
    "ftpIp": "192.0.2.10",
    "ftpUser": "api-test",
    "ftpPassword": "test-only-change-me",
    "monitorPath": "/upload/client,/upload/tmp",
}

SQL_MONITOR_NEW = {
    "monitorName": "API自动化-收单未处理量-临时数据",
    "monitorSql": "select count(1) from T_CALL_MANIFEST_RECORD",
    "monitorSchema": "SWGD",
    "pushEMail": "qa@example.invalid",
    "alterContent": "收单未处理量超过阈值",
    "alterThreshold": 100,
    "compareType": ">",
    "sqlResultType": "number",
}


FLOW_CASES: list[dict[str, Any]] = [
    case(
        title="FC-01 保存流程日志-有效请求",
        group=FLOW_GROUP,
        case_id="FC-01",
        priority="P0",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/flowMessage/notify",
        headers=FLOW_HEADERS,
        body=FLOW_SAVE_BODY,
        assertions=success_assertions(
            assertion("json_path", "type", "integer", "P1", "$.data.id"),
            assertion(
                "json_path", "eq", "SWGD202609200001", "P1", "$.data.serialNo"
            ),
        ),
        precondition="网关、flow-center 和日志库可用；epToken 有效。",
        data="使用 SWGD202609200001 提交一条接单流程日志。",
        expected="HTTP 200，业务码 200，返回新增日志 ID 和相同流水号。",
        markers=["api", "swgd", "smoke", "write"],
    ),
    case(
        title="FC-02 保存流程日志-必填参数缺失",
        group=FLOW_GROUP,
        case_id="FC-02",
        priority="P0",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/flowMessage/notify",
        headers=FLOW_HEADERS,
        body={},
        assertions=error_assertions(),
        precondition="网关和 flow-center 可用。",
        data="请求体为空对象。",
        expected="HTTP 200，业务码非 200，提示保存失败，且不新增日志。",
        markers=["api", "swgd", "negative"],
    ),
    case(
        title="FC-03 按业务ID查询流程日志-命中结果",
        group=FLOW_GROUP,
        case_id="FC-03",
        priority="P0",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/flowMessage/queryLog",
        headers=FLOW_HEADERS,
        body={"bizId": 150},
        assertions=success_assertions(
            assertion("json_path", "type", "array", "P1", "$.data"),
            assertion("json_path", "eq", "150", "P1", "$.data[0].bizId"),
        ),
        precondition="日志库中存在 bizId=150 的历史日志。",
        data="bizId=150。",
        expected="HTTP 200，业务码 200，返回数组且首条 bizId=150。",
        markers=["api", "swgd", "smoke"],
    ),
    case(
        title="FC-04 按流水号查询流程日志-命中结果",
        group=FLOW_GROUP,
        case_id="FC-04",
        priority="P0",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/flowMessage/queryLog",
        headers=FLOW_HEADERS,
        body={"serialNo": "122220220817101307086"},
        assertions=success_assertions(
            assertion("json_path", "type", "array", "P1", "$.data"),
            assertion(
                "json_path",
                "eq",
                '"122220220817101307086"',
                "P1",
                "$.data[0].serialNo",
            ),
        ),
        precondition="日志库中存在该流水号的历史日志。",
        data="serialNo=122220220817101307086。",
        expected="HTTP 200，业务码 200，返回该流水号的日志数组。",
    ),
    case(
        title="FC-05 按业务ID或流水号查询流程日志-查询条件缺失",
        group=FLOW_GROUP,
        case_id="FC-05",
        priority="P1",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/flowMessage/queryLog",
        headers=FLOW_HEADERS,
        body={},
        assertions=error_assertions(),
        precondition="flow-center 可用。",
        data="不传 bizId 和 serialNo。",
        expected="HTTP 200，业务码非 200，提示参数错误或缺失。",
        markers=["api", "swgd", "negative"],
    ),
    case(
        title="FC-06 对外日志保存-有效请求",
        group=FLOW_GROUP,
        case_id="FC-06",
        priority="P0",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/flowApi/saveLogApi",
        headers=FLOW_HEADERS,
        body=FLOW_SAVE_BODY,
        assertions=success_assertions(
            assertion("json_path", "type", "integer", "P1", "$.data.id"),
            assertion(
                "json_path", "eq", "SWGD202609200001", "P1", "$.data.serialNo"
            ),
        ),
        precondition="flow-center 和日志库可用；epToken 有效。",
        data="提交完整的外部系统日志。",
        expected="HTTP 200，业务码 200，返回新增日志记录。",
        markers=["api", "swgd", "smoke", "write"],
    ),
    case(
        title="FC-07 对外日志保存-必填参数缺失",
        group=FLOW_GROUP,
        case_id="FC-07",
        priority="P0",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/flowApi/saveLogApi",
        headers=FLOW_HEADERS,
        body={},
        assertions=error_assertions(),
        precondition="flow-center 可用。",
        data="请求体为空对象。",
        expected="HTTP 200，业务码非 200，且不新增日志。",
        markers=["api", "swgd", "negative"],
    ),
    case(
        title="FC-08 对外日志分页查询-组合条件",
        group=FLOW_GROUP,
        case_id="FC-08",
        priority="P0",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/flowApi/queryLogApi",
        headers=FLOW_HEADERS,
        body=FLOW_QUERY_API_BODY,
        assertions=pagination_assertions(),
        precondition="日志库中存在满足组合条件的记录。",
        data="按 bizType、时间范围、机构、流水号、来源等字段查询，offset=1，limit=10。",
        expected="HTTP 200，业务码 200，data.total 为数字且 data.rows 为数组。",
        markers=["api", "swgd", "smoke"],
    ),
    case(
        title="FC-09 对外日志分页查询-空结果",
        group=FLOW_GROUP,
        case_id="FC-09",
        priority="P1",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/flowApi/queryLogApi",
        headers=FLOW_HEADERS,
        body={
            "bizType": "swgd_receice_order",
            "between_optTime": "2020-01-01,2020-01-02",
            "optOrgCode": "CUS001",
            "serialNo": "NOT_EXIST_SERIAL_987654321",
            "source": "SWGD_IMAP",
            "optType": "receive,delete",
            "cusTomCode": "C001",
            "limit": 10,
            "offset": 1,
        },
        assertions=pagination_assertions(
            assertion("json_path", "eq", "0", "P1", "$.data.total"),
        ),
        precondition="测试流水号 NOT_EXIST_SERIAL_987654321 在查询时间范围内无日志。",
        data="使用完整必填筛选条件，serialNo=NOT_EXIST_SERIAL_987654321。",
        expected="HTTP 200，业务码 200，total=0，rows 为空数组。",
        markers=["api", "swgd", "boundary"],
    ),
    case(
        title="FC-10 对外日志分页查询-查询参数缺失",
        group=FLOW_GROUP,
        case_id="FC-10",
        priority="P1",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/flowApi/queryLogApi",
        headers=FLOW_HEADERS,
        body={},
        assertions=error_assertions(),
        precondition="flow-center 可用。",
        data="请求体为空对象。",
        expected="HTTP 200，业务码非 200，提示参数错误或缺失。",
        markers=["api", "swgd", "negative"],
    ),
    case(
        title="FC-11 收单日志保存-有效请求",
        group=FLOW_GROUP,
        case_id="FC-11",
        priority="P0",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/optLog/saveLog",
        headers=FLOW_HEADERS,
        body={
            **FLOW_SAVE_BODY,
            "bizId": 10000000002,
            "serialNo": "SWGD202609200002",
            "optDesc": "接单成功",
        },
        assertions=success_assertions(
            assertion("json_path", "type", "integer", "P1", "$.data.id"),
            assertion(
                "json_path", "eq", "SWGD202609200002", "P1", "$.data.serialNo"
            ),
        ),
        precondition="flow-center 和日志库可用；epToken 有效。",
        data="新增一条流水号为 SWGD202609200002 的收单日志。",
        expected="HTTP 200，业务码 200，返回新增日志记录。",
        markers=["api", "swgd", "smoke", "write"],
    ),
    case(
        title="FC-12 收单日志保存-必填参数缺失",
        group=FLOW_GROUP,
        case_id="FC-12",
        priority="P0",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/optLog/saveLog",
        headers=FLOW_HEADERS,
        body={},
        assertions=error_assertions(),
        precondition="flow-center 可用。",
        data="请求体为空对象。",
        expected="HTTP 200，业务码非 200，且不新增日志。",
        markers=["api", "swgd", "negative"],
    ),
    case(
        title="FC-13 收单日志分页查询-组合条件",
        group=FLOW_GROUP,
        case_id="FC-13",
        priority="P0",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/optLog/querySwgdOrderReceiveLog",
        headers=FLOW_HEADERS,
        body=FLOW_RECEIVE_QUERY_BODY,
        assertions=pagination_assertions(),
        precondition="日志库中存在满足条件的收单日志。",
        data="组合使用流水号、状态、提单号、代理、日期和分页参数。",
        expected="HTTP 200，业务码 200，返回 total 和 rows。",
        markers=["api", "swgd", "smoke"],
    ),
    case(
        title="FC-14 收单日志分页查询-空结果",
        group=FLOW_GROUP,
        case_id="FC-14",
        priority="P1",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/optLog/querySwgdOrderReceiveLog",
        headers=FLOW_HEADERS,
        body={
            "bizType": "swgd_receice_order",
            "serialNo": "NOT_EXIST_SERIAL_987654321",
            "offset": 1,
            "limit": 10,
        },
        assertions=pagination_assertions(
            assertion("json_path", "eq", "0", "P1", "$.data.total"),
        ),
        precondition="测试流水号不存在。",
        data="serialNo=NOT_EXIST_SERIAL_987654321。",
        expected="HTTP 200，业务码 200，total=0 且 rows 为空数组。",
        markers=["api", "swgd", "boundary"],
    ),
    case(
        title="FC-15 收单日志分页查询-单页边界",
        group=FLOW_GROUP,
        case_id="FC-15",
        priority="P2",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/optLog/querySwgdOrderReceiveLog",
        headers=FLOW_HEADERS,
        body={
            "bizType": "swgd_receice_order",
            "offset": 1,
            "limit": 1,
        },
        assertions=pagination_assertions(),
        precondition="日志库中存在至少一条收单日志。",
        data="offset=1，limit=1。",
        expected="HTTP 200，业务码 200，返回总计和不超过一页的数组结构。",
        markers=["api", "swgd", "boundary"],
    ),
    case(
        title="FC-16 查询单个流程号日志列表-命中结果",
        group=FLOW_GROUP,
        case_id="FC-16",
        priority="P0",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/optLog/getSwgdOrderReceiveLog",
        headers=FLOW_HEADERS,
        body={
            "bizType": "swgd_receice_order",
            "serialNo": "0012345678I20240507235744000",
        },
        assertions=success_assertions(
            assertion("json_path", "type", "array", "P1", "$.data"),
            assertion(
                "json_path",
                "eq",
                "0012345678I20240507235744000",
                "P1",
                "$.data[0].serialNo",
            ),
        ),
        precondition="日志库中存在该流程号。",
        data="serialNo=0012345678I20240507235744000。",
        expected="HTTP 200，业务码 200，返回该流程号的日志列表。",
        markers=["api", "swgd", "smoke"],
    ),
    case(
        title="FC-17 查询单个流程号日志列表-流程号不存在",
        group=FLOW_GROUP,
        case_id="FC-17",
        priority="P1",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/optLog/getSwgdOrderReceiveLog",
        headers=FLOW_HEADERS,
        body={
            "bizType": "swgd_receice_order",
            "serialNo": "NOT_EXIST_SERIAL_987654321",
        },
        assertions=success_assertions(
            assertion("json_path", "eq", "[]", "P1", "$.data"),
        ),
        precondition="测试流程号不存在。",
        data="serialNo=NOT_EXIST_SERIAL_987654321。",
        expected="HTTP 200，业务码 200，data 为空数组。",
        markers=["api", "swgd", "boundary"],
    ),
    case(
        title="FC-18 查询单个流程号日志列表-流程号缺失",
        group=FLOW_GROUP,
        case_id="FC-18",
        priority="P1",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/optLog/getSwgdOrderReceiveLog",
        headers=FLOW_HEADERS,
        body={"bizType": "swgd_receice_order"},
        assertions=error_assertions(),
        precondition="flow-center 可用。",
        data="不传 serialNo。",
        expected="HTTP 200，业务码非 200。",
        markers=["api", "swgd", "negative"],
    ),
    case(
        title="FC-19 补充提单号-有效流水号",
        group=FLOW_GROUP,
        case_id="FC-19",
        priority="P0",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/optLog/suppLementBillNo",
        headers=FLOW_HEADERS,
        body={
            "serialNo": "SWGD202609200001",
            "billNo": "BL20260920001",
        },
        assertions=success_assertions(
            assertion("json_path", "type", "null", "P1", "$.data"),
        ),
        precondition="流水号 SWGD202609200001 存在且允许补充提单号。",
        data="serialNo=SWGD202609200001，billNo=BL20260920001。",
        expected="HTTP 200，业务码 200，data 为空，原日志提单号被更新。",
        markers=["api", "swgd", "smoke", "write"],
    ),
    case(
        title="FC-20 补充提单号-流水号缺失",
        group=FLOW_GROUP,
        case_id="FC-20",
        priority="P1",
        method="POST",
        url="{{baseUrl}}/swgd-imap-flow-center/optLog/suppLementBillNo",
        headers=FLOW_HEADERS,
        body={"billNo": "BL20260920001"},
        assertions=error_assertions(),
        precondition="flow-center 可用。",
        data="只传 billNo，不传 serialNo。",
        expected="HTTP 200，业务码非 200，原日志不被修改。",
        markers=["api", "swgd", "negative"],
    ),
]


MONITOR_CASES: list[dict[str, Any]] = [
    case(
        title="IM-01 FTP目录监控-触发扫描",
        group=MONITOR_GROUP,
        case_id="IM-01",
        priority="P1",
        method="GET",
        url="{{mbaseUrl}}/swgd-imap-monitor/ftpMonitor/ftpMonitor",
        headers=MONITOR_GET_HEADERS,
        assertions=[
            assertion("status_code", "eq", "200", "P0", order=0),
        ],
        precondition="监控服务及被监控 FTP 可达，并在允许触发扫描的测试窗口内。",
        data="无请求参数。",
        expected="HTTP 200，扫描任务执行完成。",
        markers=["api", "swgd", "side-effect"],
        note="会触发真实目录扫描，不应在业务高峰或生产窗口直接执行。",
    ),
    case(
        title="IM-02 查询FTP监控配置-命中结果",
        group=MONITOR_GROUP,
        case_id="IM-02",
        priority="P0",
        method="POST",
        url="{{mbaseUrl}}/swgd-imap-monitor/ftpMonitor/queryFtpMonitor",
        headers=MONITOR_JSON_HEADERS,
        body={"ftpIp": "192.168.115.18", "offset": 1, "limit": 10},
        assertions=pagination_assertions(),
        precondition="FTP_MONITOR 中存在该 IP 的配置。",
        data="ftpIp=192.168.115.18，offset=1，limit=10。",
        expected="HTTP 200，业务码 200，返回 total 和 rows。",
        markers=["api", "swgd", "smoke"],
    ),
    case(
        title="IM-03 查询FTP监控配置-空结果",
        group=MONITOR_GROUP,
        case_id="IM-03",
        priority="P1",
        method="POST",
        url="{{mbaseUrl}}/swgd-imap-monitor/ftpMonitor/queryFtpMonitor",
        headers=MONITOR_JSON_HEADERS,
        body={"ftpIp": "203.0.113.254", "offset": 1, "limit": 10},
        assertions=pagination_assertions(
            assertion("json_path", "eq", "0", "P1", "$.data.total"),
        ),
        precondition="不存在 ftpIp=203.0.113.254 的配置。",
        data="ftpIp=203.0.113.254，offset=1，limit=10。",
        expected="HTTP 200，业务码 200，total=0 且 rows 为空数组。",
        markers=["api", "swgd", "boundary"],
    ),
    case(
        title="IM-04 新增FTP监控配置-有效请求",
        group=MONITOR_GROUP,
        case_id="IM-04",
        priority="P0",
        method="POST",
        url="{{mbaseUrl}}/swgd-imap-monitor/ftpMonitor/saveFtpMonitor",
        headers=MONITOR_JSON_HEADERS,
        body=FTP_MONITOR_NEW,
        assertions=success_assertions(),
        precondition="FTP_MONITOR 可写，测试 IP 和目录尚未配置。",
        data="使用 TEST-NET 地址 192.0.2.10 和临时测试账号。",
        expected="HTTP 200，业务码 200，配置写入 FTP_MONITOR。",
        markers=["api", "swgd", "write", "side-effect"],
        note="执行后应通过删除接口清理，避免留下临时监控配置。",
    ),
    case(
        title="IM-05 新增FTP监控配置-必填参数缺失",
        group=MONITOR_GROUP,
        case_id="IM-05",
        priority="P0",
        method="POST",
        url="{{mbaseUrl}}/swgd-imap-monitor/ftpMonitor/saveFtpMonitor",
        headers=MONITOR_JSON_HEADERS,
        body={},
        assertions=error_assertions(),
        precondition="监控服务可用。",
        data="请求体为空对象。",
        expected="HTTP 200，业务码非 200，不写入 FTP_MONITOR。",
        markers=["api", "swgd", "negative"],
    ),
    case(
        title="IM-06 批量删除FTP监控配置-主键不存在",
        group=MONITOR_GROUP,
        case_id="IM-06",
        priority="P1",
        method="POST",
        url="{{mbaseUrl}}/swgd-imap-monitor/ftpMonitor/deleteFtpMonitor",
        headers=MONITOR_JSON_HEADERS,
        body=[987654321],
        assertions=success_assertions(
            assertion("json_path", "type", "null", "P1", "$.data"),
        ),
        precondition="主键 987654321 不存在。",
        data="主键数组 [987654321]。",
        expected="HTTP 200，业务码 200，无数据受到删除影响。",
        markers=["api", "swgd", "boundary", "write"],
    ),
    case(
        title="IM-07 批量删除FTP监控配置-空主键数组",
        group=MONITOR_GROUP,
        case_id="IM-07",
        priority="P1",
        method="POST",
        url="{{mbaseUrl}}/swgd-imap-monitor/ftpMonitor/deleteFtpMonitor",
        headers=MONITOR_JSON_HEADERS,
        body=[],
        assertions=error_assertions(),
        precondition="监控服务可用。",
        data="空数组 []。",
        expected="HTTP 200，业务码非 200，不执行删除。",
        markers=["api", "swgd", "negative", "write"],
    ),
    case(
        title="IM-08 查询SQL监控配置-命中结果",
        group=MONITOR_GROUP,
        case_id="IM-08",
        priority="P0",
        method="POST",
        url="{{mbaseUrl}}/swgd-imap-monitor/sqlMonitor/querySqlMonitor",
        headers=MONITOR_JSON_HEADERS,
        body={
            "monitorSchema": "SWGDIMAP",
            "monitorName": "关务系统收单情况",
            "offset": 1,
            "limit": 10,
        },
        assertions=pagination_assertions(),
        precondition="SQL_MONITOR 中存在匹配配置。",
        data="按 monitorSchema 和 monitorName 查询，offset=1，limit=10。",
        expected="HTTP 200，业务码 200，返回 total 和 rows。",
        markers=["api", "swgd", "smoke"],
    ),
    case(
        title="IM-09 查询SQL监控配置-空结果",
        group=MONITOR_GROUP,
        case_id="IM-09",
        priority="P1",
        method="POST",
        url="{{mbaseUrl}}/swgd-imap-monitor/sqlMonitor/querySqlMonitor",
        headers=MONITOR_JSON_HEADERS,
        body={"monitorSchema": "NOT_EXIST_SCHEMA", "offset": 1, "limit": 10},
        assertions=pagination_assertions(
            assertion("json_path", "eq", "0", "P1", "$.data.total"),
        ),
        precondition="不存在 monitorSchema=NOT_EXIST_SCHEMA 的配置。",
        data="monitorSchema=NOT_EXIST_SCHEMA，offset=1，limit=10。",
        expected="HTTP 200，业务码 200，total=0 且 rows 为空数组。",
        markers=["api", "swgd", "boundary"],
    ),
    case(
        title="IM-10 新增SQL监控配置-有效请求",
        group=MONITOR_GROUP,
        case_id="IM-10",
        priority="P0",
        method="POST",
        url="{{mbaseUrl}}/swgd-imap-monitor/sqlMonitor/saveSqlMonitor",
        headers=MONITOR_JSON_HEADERS,
        body=SQL_MONITOR_NEW,
        assertions=success_assertions(),
        precondition="SQL_MONITOR 可写，测试配置名称尚不存在。",
        data="创建阈值为 100、比较符为 > 的数字型 SQL 监控配置。",
        expected="HTTP 200，业务码 200，配置写入 SQL_MONITOR。",
        markers=["api", "swgd", "write", "side-effect"],
        note="执行后应删除临时配置；即使命中阈值也不应向真实收件人发送邮件。",
    ),
    case(
        title="IM-11 新增SQL监控配置-必填参数缺失",
        group=MONITOR_GROUP,
        case_id="IM-11",
        priority="P0",
        method="POST",
        url="{{mbaseUrl}}/swgd-imap-monitor/sqlMonitor/saveSqlMonitor",
        headers=MONITOR_JSON_HEADERS,
        body={},
        assertions=error_assertions(),
        precondition="监控服务可用。",
        data="请求体为空对象。",
        expected="HTTP 200，业务码非 200，不写入 SQL_MONITOR。",
        markers=["api", "swgd", "negative"],
    ),
    case(
        title="IM-12 批量删除SQL监控配置-主键不存在",
        group=MONITOR_GROUP,
        case_id="IM-12",
        priority="P1",
        method="POST",
        url="{{mbaseUrl}}/swgd-imap-monitor/sqlMonitor/deleteSqlMonitor",
        headers=MONITOR_JSON_HEADERS,
        body=[987654321],
        assertions=success_assertions(
            assertion("json_path", "type", "null", "P1", "$.data"),
        ),
        precondition="主键 987654321 不存在。",
        data="主键数组 [987654321]。",
        expected="HTTP 200，业务码 200，无数据受到删除影响。",
        markers=["api", "swgd", "boundary", "write"],
    ),
    case(
        title="IM-13 批量删除SQL监控配置-空主键数组",
        group=MONITOR_GROUP,
        case_id="IM-13",
        priority="P1",
        method="POST",
        url="{{mbaseUrl}}/swgd-imap-monitor/sqlMonitor/deleteSqlMonitor",
        headers=MONITOR_JSON_HEADERS,
        body=[],
        assertions=error_assertions(),
        precondition="监控服务可用。",
        data="空数组 []。",
        expected="HTTP 200，业务码非 200，不执行删除。",
        markers=["api", "swgd", "negative", "write"],
    ),
    case(
        title="IM-14 执行SQL监控配置-指定主键",
        group=MONITOR_GROUP,
        case_id="IM-14",
        priority="P0",
        method="GET",
        url="{{mbaseUrl}}/swgd-imap-monitor/sqlMonitor/excuteSqlMonitor/1",
        headers=MONITOR_GET_HEADERS,
        assertions=success_assertions(
            assertion("json_path", "type", "null", "P1", "$.data"),
        ),
        precondition="主键 1 的 SQL 监控配置存在，邮件告警配置处于安全测试状态。",
        data="路径参数 id=1。",
        expected="HTTP 200，业务码 200，执行结果按阈值处理。",
        markers=["api", "swgd", "side-effect"],
        note="会真实执行 SQL，并可能发送告警邮件。",
    ),
    case(
        title="IM-15 执行SQL监控配置-主键不存在",
        group=MONITOR_GROUP,
        case_id="IM-15",
        priority="P1",
        method="GET",
        url="{{mbaseUrl}}/swgd-imap-monitor/sqlMonitor/excuteSqlMonitor/987654321",
        headers=MONITOR_GET_HEADERS,
        assertions=error_assertions(),
        precondition="主键 987654321 不存在。",
        data="路径参数 id=987654321。",
        expected="HTTP 200，业务码非 200，返回执行失败原因。",
        markers=["api", "swgd", "negative"],
    ),
    case(
        title="IM-16 用户余额监控-触发检查",
        group=MONITOR_GROUP,
        case_id="IM-16",
        priority="P1",
        method="GET",
        url="{{mbaseUrl}}/swgd-imap-monitor/orderMonitor/userBalanceMonitor",
        headers=MONITOR_GET_HEADERS,
        assertions=[
            assertion("status_code", "eq", "200", "P0", order=0),
        ],
        precondition="用户余额和账单数据处于测试可变更状态。",
        data="无请求参数。",
        expected="HTTP 200，完成余额检查及必要的账单余额更新。",
        markers=["api", "swgd", "side-effect"],
        note="会更新余额不为 0 的用户账单余额，需准备可回滚数据。",
    ),
    case(
        title="IM-17 计费记录与调用记录对比-触发检查",
        group=MONITOR_GROUP,
        case_id="IM-17",
        priority="P1",
        method="GET",
        url="{{mbaseUrl}}/swgd-imap-monitor/chargeMonitor/recordCompareMonitor",
        headers=MONITOR_GET_HEADERS,
        assertions=[
            assertion("status_code", "eq", "200", "P0", order=0),
        ],
        precondition="计费库与调用记录库可用，对比任务允许在测试窗口执行。",
        data="无请求参数。",
        expected="HTTP 200，完成计费记录与调用记录对比。",
        markers=["api", "swgd", "side-effect"],
        note="该接口历史执行偶发超时，执行时应单独设置较长超时并记录耗时。",
    ),
]


ALL_CASES = FLOW_CASES + MONITOR_CASES


class ApiClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        query: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(
                f"{method} {url} -> HTTP {exc.code}: {detail[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{method} {url} -> {exc.reason}") from exc


def login(client: ApiClient, username: str, password: str) -> str:
    payload = client.request(
        "POST", "/auth/login", {"username": username, "password": password}
    )
    token = payload.get("data", {}).get("access_token")
    if not token:
        raise RuntimeError("登录成功响应中缺少 access_token")
    return token


def existing_titles(client: ApiClient, project_id: str, group: str) -> set[str]:
    payload = client.request(
        "GET",
        "/test-cases",
        query={"project_id": project_id, "group_path": group, "page_size": 500},
    )
    return {item["title"] for item in payload.get("data", [])}


def validate_definitions() -> None:
    titles = [item["title"] for item in ALL_CASES]
    if len(titles) != len(set(titles)):
        raise RuntimeError("用例标题存在重复")
    for item in ALL_CASES:
        if item["group_path"] not in (FLOW_GROUP, MONITOR_GROUP):
            raise RuntimeError(f"未知分组: {item['group_path']}")
        if not item["assertions"]:
            raise RuntimeError(f"用例缺少断言: {item['title']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base",
        default=os.getenv("AIRETEST_API_BASE", "http://127.0.0.1:8000/api/v1"),
        help="AIRETEST API base URL",
    )
    parser.add_argument(
        "--project-id",
        default=os.getenv("AIRETEST_PROJECT_ID"),
        help="target project UUID",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="create missing cases; without this flag only preview",
    )
    args = parser.parse_args()

    validate_definitions()
    project_id = args.project_id
    if not project_id:
        print(
            "缺少 AIRETEST_PROJECT_ID 或 --project-id。\n"
            "请先指定用例所属项目，避免写入错误工作空间。",
            file=sys.stderr,
        )
        return 2

    client = ApiClient(args.api_base)
    username = os.getenv("AIRETEST_USERNAME")
    password = os.getenv("AIRETEST_PASSWORD")
    if args.apply and (not username or not password):
        print(
            "写入用例需要 AIRETEST_USERNAME 和 AIRETEST_PASSWORD。",
            file=sys.stderr,
        )
        return 2

    titles: dict[str, set[str]] = {
        FLOW_GROUP: set(),
        MONITOR_GROUP: set(),
    }
    if args.apply:
        client.token = login(client, username, password)
        for group in titles:
            titles[group] = existing_titles(client, project_id, group)

    created = 0
    skipped = 0
    for item in ALL_CASES:
        title = item["title"]
        if title in titles[item["group_path"]]:
            skipped += 1
            print(f"SKIP {title}")
            continue
        if not args.apply:
            print(f"PLAN {title}")
            continue
        payload = {**item, "project_id": project_id}
        response = client.request("POST", "/test-cases", payload)
        case_id = response.get("data", {}).get("id")
        if not case_id:
            raise RuntimeError(f"创建用例后未返回 ID: {title}")
        created += 1
        titles[item["group_path"]].add(title)
        print(f"CREATE {title} [{case_id}]")

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"{mode}: total={len(ALL_CASES)} created={created} skipped={skipped} "
        f"pending={len(ALL_CASES) - created - skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
