"""录制五分钟无声系统演示；用于后续配合全组发言制作答辩录像。"""
from pathlib import Path
import time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / "课程设计报告"


def record():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            record_video_dir=str(ROOT / "docs/evidence/browser-video"),
            record_video_size={"width": 1440, "height": 1000},
        )
        page = context.new_page()
        page.goto("http://127.0.0.1:5000", wait_until="networkidle")
        video = page.video
        started = time.monotonic()

        def caption(text):
            page.evaluate(
                """text => {
                let label = document.querySelector('#demo-caption');
                if (!label) {
                    label = document.createElement('div');
                    label.id = 'demo-caption';
                    label.style = 'position:fixed;bottom:20px;left:280px;right:35px;z-index:9999;background:#173e49ee;color:white;padding:15px 24px;border-radius:8px;font:18px Microsoft YaHei;pointer-events:none';
                    document.body.append(label);
                }
                label.textContent = text;
            }""",
                text,
            )

        def until(seconds):
            page.wait_for_timeout(max(0, seconds - (time.monotonic() - started)) * 1000)

        caption("社区居家养老智慧服务平台  ·  系统操作演示（无声）")
        until(8)
        page.locator("input[name=username]").fill("admin")
        page.locator("input[name=password]").fill("Care2026!")
        page.locator("#login-form button[type=submit]").click()
        page.locator("#workspace").wait_for(state="visible")
        page.wait_for_load_state("networkidle")

        steps = [
            ("overview", 30, "服务总览：查看老人、订单、工时与应急处理进度。"),
            ("elders", 70, "老人档案：身份证脱敏显示，评估和计划保留有效期；个人信息按角色授权访问。"),
            ("orders", 115, "服务订单：预约、派单、签到、确认和结算沿同一订单追踪，改派保留历史。"),
            ("shifts", 150, "护工排班：班次覆盖服务时间，容量与已用名额在同一事务内校验。"),
            ("vitals", 185, "健康监测：读数按采集时刻关联设备绑定，异常指标进入待核实队列。"),
            ("events", 220, "应急响应：响应、到场、关闭依次记录；超时事件由维护进程升级。"),
            ("claims", 260, "补贴申报：按自然月归集已完成服务，街道初审、民政终审后登记拨付。"),
            ("quality", 290, "质量监管：抽查记录连接服务与护工，整改由监管复核后解除限制。"),
        ]
        for section, deadline, text in steps:
            page.locator(f"a[data-section={section}]").click()
            page.wait_for_function(
                "name => document.querySelector('#workspace').dataset.section === name",
                arg=section,
            )
            caption(text)
            if section in {"elders", "orders", "events", "claims", "quality"}:
                page.wait_for_timeout(4500)
                page.locator("#table-body .row-button").first.click()
                page.locator("#detail-dialog").wait_for(state="visible")
                page.wait_for_timeout(9000)
                page.locator("#detail-dialog .close-dialog").click()
            print(section, flush=True)
            until(deadline)
        page.locator("a[data-section=overview]").click()
        page.wait_for_load_state("networkidle")
        caption("33 张表 · 17 个视图 · 11 个过程 · 14 个触发器 · 64 项测试通过")
        until(301)
        context.close()
        destination = OUTPUT / "系统演示录屏（无声）.webm"
        video.save_as(str(destination))
        browser.close()
        print(destination, flush=True)


if __name__ == "__main__":
    record()
