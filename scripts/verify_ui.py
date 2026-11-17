"""使用真实浏览器检查本地界面，保存报告所用的原始 PNG 截图。"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/evidence/screenshots"
OUTPUT.mkdir(parents=True, exist_ok=True)


def verify():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000}, device_scale_factor=1
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:5000", wait_until="networkidle")
        page.screenshot(path=str(OUTPUT / "01-login.png"), full_page=False)
        page.locator("input[name=username]").fill("admin")
        page.locator("input[name=password]").fill("Care2026!")
        page.locator("#login-form button[type=submit]").click()
        page.locator("#workspace").wait_for(state="visible")
        def navigate(name):
            page.locator(f"a[data-section={name}]").click()
            page.wait_for_selector(f'#workspace[data-section="{name}"]')

        page.wait_for_selector('#workspace[data-section="overview"]')
        for name in [
            "overview",
            "elders",
            "orders",
            "shifts",
            "vitals",
            "events",
            "claims",
            "quality",
        ]:
            navigate(name)
            page.screenshot(path=str(OUTPUT / f"{name}.png"), full_page=False)
            if name != "overview":
                assert page.locator("#table-body .row-button").count() > 0
                assert page.locator("#table-title").inner_text() == (
                    page.locator("#page-title").inner_text() + "列表"
                )
        # 让旧页响应晚于新页，验证快速切换不会覆盖当前列表。
        page.evaluate("""() => {
            window.savedFetch = window.fetch;
            window.fetch = (url, options) => String(url).includes('/api/list/elders')
                ? new Promise(resolve => setTimeout(() => resolve(savedFetch(url, options)), 600))
                : savedFetch(url, options);
        }""")
        page.locator("a[data-section=elders]").click()
        page.wait_for_timeout(60)
        navigate("orders")
        page.wait_for_timeout(800)
        assert page.locator("#table-title").inner_text() == "服务订单列表"
        assert page.locator("#table-body .row-button").first.get_attribute("data-kind") == "orders"
        page.evaluate("window.fetch = window.savedFetch; delete window.savedFetch")
        page.locator("#table-body .row-button").first.click()
        page.locator("#detail-dialog").wait_for(state="visible")
        page.screenshot(path=str(OUTPUT / "order-detail.png"), full_page=False)
        page.locator("#detail-dialog").screenshot(
            path=str(OUTPUT / "order-detail-panel.png")
        )
        page.locator("#detail-dialog .close-dialog").click()
        navigate("elders")
        page.get_by_role("button", name="＋ 新建档案", exact=True).click()
        page.locator("#form-dialog").wait_for(state="visible")
        page.screenshot(path=str(OUTPUT / "elder-form.png"), full_page=False)
        page.locator("#form-dialog .icon-button").click()
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(OUTPUT / "mobile.png"), full_page=False)
        assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
        browser.close()
    result = {
        "pages": 8,
        "javascript_errors": errors,
        "mobile_viewport": "390x844",
        "delayed_navigation": "passed",
        "result": "passed" if not errors else "failed",
    }
    (ROOT / "docs/evidence/browser-check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    assert not errors, errors
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    verify()
