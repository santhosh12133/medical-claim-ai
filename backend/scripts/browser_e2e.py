"""Browser end-to-end test of the deployed web app (Playwright + Chromium).

Runs on the host against the stack started with ``docker compose``:

    pip install playwright && python -m playwright install --with-deps chromium
    python backend/scripts/browser_e2e.py --frontend http://localhost:8080 --bill browser_bill.png --out browser-e2e

Flow: employee signs in, uploads a bill, watches it get processed, opens the claim status page and asks
the Coverage Assistant a question; admin signs in, opens the dashboard, the review queue (with evidence),
the policies page and the retrieval debugger. Fails on any browser page error, failed API call (HTTP 5xx)
or missing UI element. Screenshots of every step are written to ``--out``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def run(frontend: str, bill: Path, out: Path, timeout_ms: int) -> dict:
    from playwright.sync_api import expect, sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    steps: list[str] = []

    def watch(page) -> None:
        page.on("pageerror", lambda error: problems.append(f"page error: {error}"))
        page.on("response", lambda response: problems.append(f"HTTP {response.status} {response.url}")
                if response.status >= 500 else None)

    def step(page, name: str) -> None:
        page.screenshot(path=str(out / f"{len(steps) + 1:02d}-{name}.png"), full_page=True)
        steps.append(name)
        print(f"[PASS] {name}", flush=True)

    def sign_in(page, role: str, email: str, password: str) -> None:
        page.goto(f"{frontend}/{role}/login")
        page.locator("input").first.fill(email)
        page.locator('input[type="password"]').fill(password)
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url(f"**/{role}/dashboard", timeout=20_000)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()

        # ---------------------------------------------------------------- employee
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        watch(page)
        page.goto(f"{frontend}/employee/login")
        expect(page.locator('input[type="password"]')).to_have_value("")  # no pre-filled demo password
        step(page, "employee-login-page-empty")
        sign_in(page, "employee", os.getenv("E2E_EMPLOYEE_EMAIL", "employee@demo.com"),
                os.getenv("E2E_EMPLOYEE_PASSWORD", "employee123"))
        step(page, "employee-dashboard")

        page.goto(f"{frontend}/employee/upload")
        page.locator('input[type="file"]').set_input_files(str(bill))
        page.get_by_role("button", name="Upload & submit claim").click()
        expect(page.locator(".result-heading strong")).to_be_visible(timeout=20_000)
        step(page, "employee-upload-queued")
        # "Claim #N is being processed" -> "Claim #N processed" once the worker has finished
        expect(page.locator(".result-heading strong")).to_have_text(re.compile(r"Claim #\d+ processed"), timeout=timeout_ms)
        expect(page.locator(".detail-grid")).to_contain_text("7,000")
        step(page, "employee-upload-processed")

        page.goto(f"{frontend}/employee/status")
        expect(page.get_by_text("Root canal treatment").first).to_be_visible(timeout=20_000)
        step(page, "employee-claim-status")

        page.goto(f"{frontend}/employee/assistant")
        page.locator(".chip").first.click()
        expect(page.locator(".answer .citation").first).to_be_visible(timeout=60_000)
        step(page, "employee-coverage-assistant")
        page.close()

        # ------------------------------------------------------------------- admin
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        watch(page)
        sign_in(page, "admin", os.getenv("E2E_ADMIN_EMAIL", "admin@demo.com"), os.getenv("E2E_ADMIN_PASSWORD", "admin123"))
        expect(page.locator(".metric-card").first).to_be_visible()
        step(page, "admin-dashboard")

        page.goto(f"{frontend}/admin/review")
        card = page.locator(".review-card").first
        expect(card).to_be_visible(timeout=20_000)
        card.get_by_role("button", name="Review details").click()
        expect(card.locator(".evidence, .hint").first).to_be_visible(timeout=20_000)
        step(page, "admin-review-queue")

        page.goto(f"{frontend}/admin/policies")
        expect(page.locator("table.claims-table tbody tr").first).to_be_visible(timeout=20_000)
        page.fill('input[aria-label="Retrieval test query"]', "root canal limit")
        page.get_by_role("button", name="Search").click()
        expect(page.get_by_text("Dental Care Reimbursement Policy").first).to_be_visible(timeout=60_000)
        step(page, "admin-policies-and-retrieval-debugger")

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{frontend}/admin/review")
        expect(page.locator(".review-card").first).to_be_visible(timeout=20_000)
        step(page, "admin-review-mobile")
        browser.close()

    return {"steps_passed": steps, "problems": problems}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frontend", default="http://localhost:8080")
    parser.add_argument("--bill", required=True, type=Path, help="Bill image to upload (see stack_smoke_test.py --make-bill)")
    parser.add_argument("--out", default="browser-e2e", type=Path)
    parser.add_argument("--timeout", type=int, default=300, help="Seconds to wait for claim processing")
    args = parser.parse_args()
    try:
        result = run(args.frontend, args.bill, args.out, args.timeout * 1000)
    except Exception as exc:  # report the failing step clearly, then fail the job
        print(f"[FAIL] {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    if result["problems"]:
        print("[FAIL] browser reported errors", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
