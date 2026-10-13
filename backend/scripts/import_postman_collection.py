"""从命令行导入 Postman Collection v2.x.

用法：
    python scripts/import_postman_collection.py <collection.json> \
        --project-id <项目ID> [--variables env.json] [--default-header epToken=xxx]

示例：
    python scripts/import_postman_collection.py "swgd-imap-content - enterprise.postman_collection.json" \
        --project-id 6edc17b9-8c9b-40b6-a130-a5f3e28c96d5 \
        --variables "enterprise.postman_environment.json"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _bootstrap_database_url() -> None:
    """让命令行导入与后端服务使用同一个 SQLite 数据库.

    后端通常从仓库根目录启动（DATABASE_URL=sqlite:///./airetest-lite.db），
    而脚本可能从任意目录执行；这里优先读取根目录 `.env`，并把相对路径解析到仓库根目录。
    """
    if os.environ.get("DATABASE_URL"):
        return
    for env_path in (REPO_ROOT / ".env", BACKEND_DIR / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "DATABASE_URL":
                os.environ["DATABASE_URL"] = value.strip().strip('"').strip("'")
                return


_bootstrap_database_url()

from app.database import SessionLocal  # noqa: E402
from app.models.global_variable import GlobalVariable  # noqa: E402
from app.models.test_case import AssertionRule, TestCase  # noqa: E402
from app.services.postman_importer import parse_postman_collection  # noqa: E402

VARIABLE_KEYS_TO_IMPORT = {
    "contentProtocol",
    "contentHost",
    "contentPort",
    "contentContext",
    "enterpriseProtocol",
    "enterpriseHost",
    "enterprisePort",
    "version",
}


def _load_json(path: str) -> dict:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def _parse_header(values: list[str] | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"请求头格式应为 key=value：{value}")
        key, header_value = value.split("=", 1)
        headers[key.strip()] = header_value
    return headers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection", help="Postman Collection JSON 路径")
    parser.add_argument("--project-id", required=True, help="导入到的项目 ID")
    parser.add_argument("--variables", help="Postman 环境变量 JSON 路径")
    parser.add_argument(
        "--default-header",
        action="append",
        help="补充请求头，可重复，如 --default-header epToken=xxx",
    )
    parser.add_argument(
        "--no-import-variables",
        action="store_true",
        help="不写入工作区变量",
    )
    args = parser.parse_args()

    collection = _load_json(args.collection)
    variables = _load_json(args.variables) if args.variables else {}
    endpoints, warnings, merged = parse_postman_collection(
        collection,
        variables=variables,
        default_headers=_parse_header(args.default_header),
    )
    if not endpoints:
        print("未解析到任何请求", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        created = 0
        for endpoint in endpoints:
            case = TestCase(
                title=endpoint["suggested_name"],
                description=f"Postman 导入：{endpoint['group_path'] or '未分组'}",
                group_path=endpoint["group_path"] or None,
                method=endpoint["method"],
                url=endpoint["url"],
                headers=endpoint["headers"],
                params=endpoint["params"],
                body=endpoint["body"],
                files=endpoint["files"],
                project_id=args.project_id,
                markers=["api", "postman_imported"],
            )
            db.add(case)
            db.flush()
            db.add(
                AssertionRule(
                    test_case_id=case.id,
                    assertion_type="status_code",
                    operator="eq",
                    expected="200",
                    priority="P0",
                    order=0,
                )
            )
            created += 1

        imported_variables = 0
        if not args.no_import_variables:
            for name, value in merged.items():
                if name not in VARIABLE_KEYS_TO_IMPORT or value == "":
                    continue
                exists = (
                    db.query(GlobalVariable)
                    .filter(
                        GlobalVariable.name == name,
                        GlobalVariable.scope == "workspace",
                        GlobalVariable.project_id == args.project_id,
                    )
                    .first()
                )
                if exists:
                    continue
                db.add(
                    GlobalVariable(
                        name=name,
                        value=value,
                        var_type="string",
                        description="Postman 集合导入",
                        scope="workspace",
                        project_id=args.project_id,
                    )
                )
                imported_variables += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"创建用例：{created}")
    print(f"写入工作区变量：{imported_variables}")
    missing = sorted(
        {
            variable
            for endpoint in endpoints
            for variable in endpoint.get("variables", [])
        }
    )
    print(f"待补充变量：{missing}")
    if warnings:
        print(f"解析提示：{warnings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
