import asyncio
from playwright.async_api import async_playwright

async def test_indeed():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) # To see what happens
        page = await browser.new_page()

        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        print("Naviagting to Indeed")
        await page.goto("https://www.indeed.com/jobs?q=software+engineer&l=remote", wait_until="networkidle")

        await page.wait_for_timeout(3000)

        # Check info
        title = await page.title()
        print(f"Page title: {title}")

        # Try to find job cards
        cards = await page.query_selector_all('[class*="job_seen_beacon"]')
        print(f"Job cards found: {len(cards)}")

        if cards:
            first = cards[0]
            text = await first.inner_text()
            print(f"\nFirst card text:\n{text[:300]}")
        else:
            # Dump a snippet of HTML to see what we got instead
            html = await page.content()
            print(f"\nNo cards found. HTML snippet:\n{html[:1000]}")

        await browser.close()

async def test_glassdoor():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        print("Navigating to Glassdoor...")
        await page.goto("https://www.glassdoor.com/Job/remote-software-engineer-jobs-SRCH_IL.0,6_IS11047_KO7,24.htm", wait_until="networkidle")

        await page.wait_for_timeout(3000)

        title = await page.title()
        print(f"Page title: {title}")

        cards = await page.query_selector_all('[data-test="jobListing"]')
        print(f"Job cards found: {len(cards)}")

        if cards:
            first = cards[0]
            text = await first.inner_text()
            print(f"\nFirst card text:\n{text[:300]}")
        else:
            html = await page.content()
            print(f"\nNo cards found. HTML snippet:\n{html[:2000]}")

        await browser.close()

asyncio.run(test_glassdoor())