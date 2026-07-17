"""Open every frontend route and fail on blank pages or HTTP/runtime errors."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from sqlalchemy import select


ROUTES = [
    "/dashboard",
    "/jobs",
    "/quick-test",
    "/api-list",
    "/projects",
    "/import",
    "/environments",
    "/variables",
    "/test-cases",
    "/test-plans",
    "/reports",
    "/coverage",
    "/api-docs",
    "/scheduled-tasks",
    "/mock-service",
    "/history",
    "/ai",
    "/ui-test-cases",
    "/ui-test-suites",
    "/step-library",
    "/ui-elements",
    "/ui-test-records",
    "/ui-test-logs",
    "/perf-tests",
    "/perf-reports",
    "/perf-dashboard",
    "/users",
    "/roles",
    "/api-tokens",
    "/ci-cd",
    "/test-data",
    "/notifications",
    "/knowledge/defects",
    "/knowledge/rules",
    "/knowledge/interfaces",
    "/audit-logs",
    "/ai-ops",
    "/quality-gates",
    "/defects",
]


def local_token(repository: Path, username: str) -> str:
    backend_dir = repository / "backend"
    database = repository / "airetest-lite.db"
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{database.as_posix()}")
    sys.path.insert(0, str(backend_dir))

    from app.database import SessionLocal
    from app.models.user import User
    from app.services.auth_service import create_user_token

    with SessionLocal() as db:
        user = db.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()
        if user is None:
            raise RuntimeError(f"Local user does not exist: {username}")
        return create_user_token(user)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--token", default=os.getenv("AIRETEST_SMOKE_TOKEN", ""))
    parser.add_argument("--username", default="admin")
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    args = parser.parse_args()

    repository = Path(__file__).resolve().parent.parent
    token = args.token or local_token(repository, args.username)
    failures: list[str] = []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 900}
            )
            context.add_init_script(
                f"localStorage.setItem('access_token', {token!r});"
            )

            for route in ROUTES:
                page = context.new_page()
                runtime_errors: list[str] = []
                response_errors: list[str] = []

                page.on(
                    "pageerror",
                    lambda error, target=runtime_errors: target.append(
                        str(error).splitlines()[0]
                    ),
                )

                def record_response(response, target=response_errors):
                    if response.status >= 400 and "/api/" in response.url:
                        target.append(f"{response.status} {response.url}")

                page.on("response", record_response)

                try:
                    page.goto(
                        f"{args.base_url.rstrip('/')}{route}",
                        wait_until="networkidle",
                        timeout=args.timeout_ms,
                    )
                    body_text = page.locator("body").inner_text().strip()
                    if len(body_text) < 10:
                        runtime_errors.append("page body is blank")
                except PlaywrightError as exc:
                    runtime_errors.append(str(exc).splitlines()[0])
                finally:
                    page.close()

                if runtime_errors or response_errors:
                    details = runtime_errors + response_errors
                    failures.append(f"{route}: {'; '.join(details)}")

            browser.close()
    except PlaywrightError as exc:
        print(f"Unable to launch Chromium: {exc}", file=sys.stderr)
        print(
            "Install it with: python -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    if failures:
        print(f"Route smoke failed: {len(failures)}/{len(ROUTES)}")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(f"Route smoke passed: {len(ROUTES)}/{len(ROUTES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
