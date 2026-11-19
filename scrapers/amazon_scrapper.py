import re
from playwright.async_api import async_playwright

class AmazonScraper:
    def __init__(self, url: str):
        self.url = url

    async def fetch_product_data(self) -> dict:

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--no-sandbox",
                        "--disable-setuid-sandbox"
                    ]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                    locale="tr-TR"
                )
                page = await context.new_page()
                
                
                await page.goto(self.url, timeout=15000, wait_until="domcontentloaded")

                # 1. Başlık
                title = ""
                try:
                    title_el = page.locator("#productTitle").first
                    if await title_el.count() > 0:
                        title = (await title_el.inner_text()).strip()
                except:
                    pass

                # 2. Fiyat
                price = 0.0
                price_text = ""
                price_selectors = [
                    ".a-price .a-offscreen",
                    "#corePrice_feature_div .a-price-whole",
                    "#priceblock_ourprice"
                ]

                for sel in price_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.count() > 0:
                            price_text = await el.inner_text()
                            if price_text:
                                break
                    except:
                        continue

                if price_text:
                    clean_text = re.sub(r'[^\d,\.]', '', price_text)
                    if ',' in clean_text and '.' in clean_text:
                        clean_text = clean_text.replace('.', '').replace(',', '.')
                    elif ',' in clean_text:
                        clean_text = clean_text.replace(',', '.')
                    elif '.' in clean_text:
                        clean_text = clean_text.replace('.', '')  # <-- Sadece nokta varsa binlik ayracıdır, kaldırılır
                        
                    try:
                        price = float(clean_text)
                    except:
                        price = 0.0

                match = re.search(r'/dp/([A-Z0-9]{10})', self.url)
                platform_product_id = match.group(1) if match else self.url.split('/')[-1].split('?')[0]

                await browser.close()

                if not title or price == 0:
                    return None

                return {
                    "platform_product_id": platform_product_id,
                    "title": title,
                    "price": price,
                    "original_price": price,
                    "discount_percentage": 0.0,
                    "in_stock": True,
                    "url": self.url
                }

        except Exception as e:
            return None