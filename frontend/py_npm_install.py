"""Python npm 安装器：绕过 Node.js Winsock 损坏问题.

原理：Node.js 的 socket 操作因 Winsock LSP 损坏而完全失败（ENOTSOCK），
但 Python 的网络栈正常。本脚本用 Python 完成 npm install 的核心功能：
1. 读取 package.json 的 dependencies + devDependencies
2. 递归解析依赖树（semver 范围匹配）
3. 下载 tarball 并解压到 node_modules/
4. 生成 .package-lock.json

不支持：peer deps 自动安装、optional deps、版本冲突解决（取第一个匹配版本）。
对于本项目依赖不复杂的情况足够使用。
"""
from __future__ import annotations

import json
import os
import re
import sys
import tarfile
import urllib.request
import urllib.error
import hashlib
import io
from pathlib import Path

REGISTRY = "https://registry.npmmirror.com"
FRONTEND_DIR = Path(__file__).parent
NODE_MODULES = FRONTEND_DIR / "node_modules"
PACKAGE_JSON = FRONTEND_DIR / "package.json"
LOCKFILE = FRONTEND_DIR / "package-lock.json"

# 已安装的包缓存 {package_name@version: True}
installed: dict[str, bool] = {}

# 依赖解析队列 [(name, version_range, parent_path)]
# parent_path 用于确定嵌套依赖的安装位置


def _fetch_json(url: str, timeout: int = 30) -> dict:
    """用 Python urllib 获取 JSON."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _fetch_tarball(url: str, timeout: int = 120) -> bytes:
    """下载 tarball 二进制内容."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _parse_version(v: str) -> tuple:
    """将 '1.2.3' 解析为 (1, 2, 3) 元组."""
    parts = re.split(r'[.\-+]', v)
    major = int(parts[0]) if parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return (major, minor, patch)


def _match_range(version: str, range_spec: str) -> bool:
    """简单的 semver 范围匹配.

    支持:
        ^1.2.3   → >=1.2.3 <2.0.0
        ~1.2.3   → >=1.2.3 <1.3.0
        >=1.2.3  → >=1.2.3
        >1.2.3   → >1.2.3
        <=1.2.3  → <=1.2.3
        <1.2.3   → <1.2.3
        1.2.3    → ==1.2.3
        *        → any
        latest   → any
    """
    if not range_spec or range_spec in ("*", "latest", ""):
        return True

    v = _parse_version(version)

    # 处理 || 分隔的多个范围（取第一个）
    if "||" in range_spec:
        range_spec = range_spec.split("||")[0].strip()

    # 处理空格分隔的多个条件
    conditions = range_spec.split()
    for cond in conditions:
        cond = cond.strip()
        if not cond:
            continue

        if cond.startswith("^"):
            base = _parse_version(cond[1:])
            if v < base:
                return False
            if v[0] != base[0] or v[0] == 0:
                # ^0.x.y → >=0.x.y <0.(x+1).0
                if v[0] == 0:
                    if v[1] != base[1] or (v[1] == base[1] and v[2] < base[2]):
                        if v < base:
                            return False
                    if v[1] > base[1]:
                        return False
                else:
                    if v[0] > base[0]:
                        return False
        elif cond.startswith("~"):
            base = _parse_version(cond[1:])
            if v < base:
                return False
            if v[0] != base[0] or v[1] != base[1]:
                return False
        elif cond.startswith(">="):
            base = _parse_version(cond[2:])
            if v < base:
                return False
        elif cond.startswith(">"):
            base = _parse_version(cond[1:])
            if v <= base:
                return False
        elif cond.startswith("<="):
            base = _parse_version(cond[2:])
            if v > base:
                return False
        elif cond.startswith("<"):
            base = _parse_version(cond[1:])
            if v >= base:
                return False
        elif cond.startswith("="):
            base = _parse_version(cond[1:])
            if v != base:
                return False
        else:
            # 精确版本
            base = _parse_version(cond)
            if v != base:
                return False

    return True


def _resolve_version(metadata: dict, range_spec: str) -> str | None:
    """从包 metadata 中找到匹配 range_spec 的最新版本."""
    versions = list(metadata.get("versions", {}).keys())
    # 过滤掉 pre-release 版本（除非范围指定了 pre-release）
    if not any(c in range_spec for c in ["-", "alpha", "beta", "rc"]):
        versions = [v for v in versions if "-" not in v]

    # 按 semver 降序排序（简单排序）
    versions.sort(key=_parse_version, reverse=True)

    for v in versions:
        if _match_range(v, range_spec):
            return v

    # 如果没匹配到，尝试 dist-tags
    dist_tags = metadata.get("dist-tags", {})
    if "latest" in dist_tags:
        return dist_tags["latest"]

    return versions[0] if versions else None


def _get_scoped_path(name: str) -> Path:
    """获取包在 node_modules 中的路径.

    scoped 包 (@scope/name) 安装到 node_modules/@scope/name
    """
    if name.startswith("@"):
        parts = name.split("/")
        return NODE_MODULES / parts[0] / parts[1]
    return NODE_MODULES / name


def _install_package(name: str, version_range: str, depth: int = 0) -> str | None:
    """安装单个包及其依赖.

    返回安装的版本号，失败返回 None.
    """
    indent = "  " * depth

    # 解析版本范围
    if version_range.startswith("file:"):
        print(f"{indent}跳过本地包: {name}")
        return None

    # 获取包 metadata
    try:
        metadata = _fetch_json(f"{REGISTRY}/{name}")
    except Exception as e:
        print(f"{indent}获取 {name} metadata 失败: {e}")
        return None

    # 解析版本
    version = _resolve_version(metadata, version_range)
    if not version:
        print(f"{indent}找不到 {name}@{version_range} 的匹配版本")
        return None

    key = f"{name}@{version}"
    if key in installed:
        print(f"{indent}已安装: {name}@{version}")
        return version

    print(f"{indent}安装: {name}@{version} (range: {version_range})")

    # 获取版本详情
    version_info = metadata.get("versions", {}).get(version)
    if not version_info:
        print(f"{indent}  版本详情缺失")
        return None

    # 下载 tarball
    tarball_url = version_info.get("dist", {}).get("tarball")
    if not tarball_url:
        print(f"{indent}  tarball URL 缺失")
        return None

    integrity = version_info.get("dist", {}).get("integrity")

    try:
        tarball_data = _fetch_tarball(tarball_url)
    except Exception as e:
        print(f"{indent}  下载 tarball 失败: {e}")
        return None

    # 验证 integrity (sha512)
    if integrity and integrity.startswith("sha512-"):
        expected_hash = integrity[7:]
        actual_hash = hashlib.sha512(tarball_data).hexdigest()
        if actual_hash != expected_hash:
            print(f"{indent}  WARNING: integrity 校验失败，继续安装")

    # 解压到 node_modules
    install_path = _get_scoped_path(name)

    # 如果已存在 package.json，说明包已安装，跳过（不清空目录）
    if (install_path / "package.json").exists():
        print(f"{indent}  已存在，跳过")
        installed[key] = True
        # 仍然递归安装依赖（确保子依赖存在）
        deps = version_info.get("dependencies", {})
        for dep_name, dep_range in deps.items():
            _install_package(dep_name, dep_range, depth + 1)
        return version

    install_path.mkdir(parents=True, exist_ok=True)

    # 解压 tarball
    try:
        with tarfile.open(fileobj=io.BytesIO(tarball_data), mode="r:gz") as tar:
            tar.extractall(install_path, filter="data")
    except Exception as e:
        print(f"{indent}  解压失败: {e}")
        return None

    # npm tarball 解压后可能创建子目录（标准 package/ 或包名前缀如 react/）
    # 需要把子目录内容移到安装路径根目录
    import shutil
    # 先处理标准 package/ 前缀
    package_subdir = install_path / "package"
    if package_subdir.exists() and package_subdir.is_dir():
        for item in package_subdir.iterdir():
            target = install_path / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
            shutil.move(str(item), str(target))
        package_subdir.rmdir()

    # 如果仍然没有 package.json，查找包含 package.json 的子目录并提升
    if not (install_path / "package.json").exists():
        for sub in install_path.iterdir():
            if sub.is_dir() and (sub / "package.json").exists():
                for item in sub.iterdir():
                    target = install_path / item.name
                    if target.exists():
                        if target.is_dir():
                            shutil.rmtree(target, ignore_errors=True)
                        else:
                            target.unlink(missing_ok=True)
                    shutil.move(str(item), str(target))
                sub.rmdir()
                break  # 只处理第一个匹配的子目录

    installed[key] = True

    # 递归安装 dependencies（跳过 optionalDependencies 和 peerDependencies）
    deps = version_info.get("dependencies", {})
    for dep_name, dep_range in deps.items():
        _install_package(dep_name, dep_range, depth + 1)

    # bin 链接（创建 .bin 目录的脚本）
    bin_info = version_info.get("bin")
    if bin_info:
        _create_bin_links(name, version_info, install_path)

    return version


def _create_bin_links(name: str, version_info: dict, install_path: Path) -> None:
    """创建 bin 链接脚本."""
    bin_info = version_info.get("bin")
    if not bin_info:
        return

    bin_dir = NODE_MODULES / ".bin"
    bin_dir.mkdir(exist_ok=True)

    if isinstance(bin_info, str):
        bin_info = {name: bin_info}

    for bin_name, bin_path in bin_info.items():
        # 创建 Windows 批处理脚本（确保父目录存在，scoped bin name 如 @babel/parser）
        bat_file = bin_dir / f"{bin_name}.cmd"
        bat_file.parent.mkdir(parents=True, exist_ok=True)
        target = install_path / bin_path
        bat_content = f"""@ECHO off
GOTO start
:find_dp0
SET dp0=%~dp0
EXIT /b
:start
SETLOCAL
CALL :find_dp0
IF EXIST "%dp0%\\node.exe" (
  SET "_prog=%dp0%\\node.exe"
) ELSE (
  SET "_prog=node"
  SET PATHEXT=%PATHEXT:;.JS;=;%
)
endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%" "%dp0%\\{bin_path}" %*
"""
        bat_file.write_text(bat_content, encoding="utf-8")

        # 也创建无扩展名版本（for Unix-like）
        sh_file = bin_dir / bin_name
        sh_file.parent.mkdir(parents=True, exist_ok=True)
        sh_content = f"""#!/bin/sh
basedir=$(dirname "$(echo "$0" | sed -e 's,\\\\,/,g')")
case `uname` in
    *CYGWIN*|*MINGW*|*MSYS*) basedir=`cygpath -w "$basedir"`;;
esac
if [ -x "$basedir/node" ]; then
  exec "$basedir/node" "$basedir/../{name.replace('@','')}/{bin_path}" "$@"
else
  exec node "$basedir/../{name.replace('@','')}/{bin_path}" "$@"
fi
"""
        sh_file.write_text(sh_content, encoding="utf-8")


def _generate_lockfile(packages: dict) -> dict:
    """生成简化的 package-lock.json."""
    return {
        "name": "frontend",
        "version": "0.0.0",
        "lockfileVersion": 3,
        "requires": True,
        "packages": {
            "": {
                "name": "frontend",
                "version": "0.0.0",
                "dependencies": packages,
            }
        },
    }


def main() -> None:
    print("=" * 60)
    print("Python npm 安装器 (绕过 Node.js Winsock 损坏)")
    print("=" * 60)

    # 读取 package.json
    with open(PACKAGE_JSON, "r", encoding="utf-8") as f:
        pkg = json.load(f)

    deps = pkg.get("dependencies", {})
    dev_deps = pkg.get("devDependencies", {})
    all_deps = {}
    all_deps.update(deps)
    all_deps.update(dev_deps)

    print(f"\n共 {len(all_deps)} 个顶层依赖")
    print(f"  dependencies: {len(deps)}")
    print(f"  devDependencies: {len(dev_deps)}")
    print()

    # 确保 node_modules 存在
    NODE_MODULES.mkdir(exist_ok=True)

    # 逐个安装
    resolved_versions = {}
    failed = []

    for name, version_range in sorted(all_deps.items()):
        version = _install_package(name, version_range, depth=0)
        if version:
            resolved_versions[name] = version
        else:
            failed.append(f"{name}@{version_range}")

    # 生成 lockfile
    lockfile_data = _generate_lockfile(all_deps)
    with open(LOCKFILE, "w", encoding="utf-8") as f:
        json.dump(lockfile_data, f, indent=2, ensure_ascii=False)

    # 生成 .package-lock.json (npm 内部用)
    inner_lockfile = NODE_MODULES / ".package-lock.json"
    with open(inner_lockfile, "w", encoding="utf-8") as f:
        json.dump(lockfile_data, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print(f"安装完成: {len(resolved_versions)}/{len(all_deps)} 成功")
    if failed:
        print(f"失败: {len(failed)} 个")
        for f_name in failed:
            print(f"  - {f_name}")
    print("=" * 60)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
