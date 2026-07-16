"""SEC-03 迁移脚本：将 api_tokens 表的明文 token 改为 HMAC-SHA256 哈希存储.

变更内容：
    - 新增 token_hash 列（HMAC-SHA256 哈希，唯一索引）
    - 新增 token_prefix 列（前 8 位，用于展示）
    - 将现有 token 明文哈希后填入 token_hash，前 8 位填入 token_prefix
    - 将原 token 列重命名为 token_legacy（保留备份）

幂等：若 token_hash 列已存在则跳过。

用法（在 backend 目录执行）：
    python migrations/migrate_token_hash.py

仅支持 SQLite。
"""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
import sys
from pathlib import Path

# 将 backend 目录加入 sys.path 以便导入 app.config
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.config import get_settings  # noqa: E402

TOKEN_PREFIX_LEN = 8


def _db_path() -> str:
    """从 DATABASE_URL 解析 SQLite 文件路径."""
    url = get_settings().DATABASE_URL
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "", 1)
    raise RuntimeError(f"仅支持 SQLite，当前 DATABASE_URL={url}")


def _hash_token(token: str) -> str:
    """使用 HMAC-SHA256 对 token 做哈希，密钥为应用 SECRET_KEY.

    与 app.services.ci_cd_service._hash_token 逻辑一致。
    """
    secret_key = get_settings().SECRET_KEY
    return hmac.new(
        secret_key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def _column_exists(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cur.fetchall()]
    return column in columns


def main() -> None:
    db_path = _db_path()
    print(f"[SEC-03 迁移] 数据库文件: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        if not _table_exists(cur, "api_tokens"):
            print("[SEC-03 迁移] api_tokens 表不存在，跳过（将由 ORM 自动建表）")
            return

        # 已迁移过则跳过
        if _column_exists(cur, "api_tokens", "token_hash"):
            print("[SEC-03 迁移] token_hash 列已存在，跳过（已迁移）")
            return

        if not _column_exists(cur, "api_tokens", "token"):
            print("[SEC-03 迁移] token 列不存在且 token_hash 也不存在，跳过")
            return

        # 1. 新增 token_hash 和 token_prefix 列
        cur.execute("ALTER TABLE api_tokens ADD COLUMN token_hash VARCHAR(128)")
        cur.execute("ALTER TABLE api_tokens ADD COLUMN token_prefix VARCHAR(16)")
        print("[SEC-03 迁移] 已添加 token_hash、token_prefix 列")

        # 2. 将现有明文 token 哈希后填入 token_hash，前 8 位填入 token_prefix
        cur.execute("SELECT id, token FROM api_tokens")
        rows = cur.fetchall()
        migrated_count = 0
        for row_id, plaintext in rows:
            if not plaintext:
                continue
            token_hash = _hash_token(plaintext)
            token_prefix = plaintext[:TOKEN_PREFIX_LEN]
            cur.execute(
                "UPDATE api_tokens SET token_hash=?, token_prefix=? WHERE id=?",
                (token_hash, token_prefix, row_id),
            )
            migrated_count += 1
        print(f"[SEC-03 迁移] 已哈希 {migrated_count} 条现有 token 记录")

        # 3. 创建唯一索引（token_hash）和普通索引（token_prefix）
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_api_tokens_token_hash "
            "ON api_tokens (token_hash)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_api_tokens_token_prefix "
            "ON api_tokens (token_prefix)"
        )
        print("[SEC-03 迁移] 已创建 token_hash 唯一索引、token_prefix 索引")

        # 4. 删除旧的 token 列上的索引（按名称精确匹配，避免误删 name 等列的索引）
        cur.execute("DROP INDEX IF EXISTS ix_api_tokens_token")
        print("[SEC-03 迁移] 已删除旧索引: ix_api_tokens_token（如存在）")

        # 5. 重命名 token 列为 token_legacy（保留备份）
        cur.execute(
            "ALTER TABLE api_tokens RENAME COLUMN token TO token_legacy"
        )
        print("[SEC-03 迁移] 已将 token 列重命名为 token_legacy（备份保留）")

        conn.commit()
        print("[SEC-03 迁移] 完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
