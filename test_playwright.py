"""容器内 playwright 最小验证：launch + 渲染 + 截图"""
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content("<h1>playwright ok</h1>")
        await page.screenshot(path="/tmp/test.png")
        await browser.close()
    print("PLAYWRIGHT_OK")


asyncio.run(main())
