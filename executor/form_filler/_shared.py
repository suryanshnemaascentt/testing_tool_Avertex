async def _wait(page, ms):
    await page.wait_for_timeout(ms)
