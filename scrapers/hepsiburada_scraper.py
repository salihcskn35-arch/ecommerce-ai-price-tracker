import re
import asyncio
from playwright.async_api import async_playwright

class HepsiburadaScraper:
    def __init__(self, url: str):
        self.url = url

    async def fetch_product_data(self) -> dict:
        """Asenkron Playwright kullanarak Hepsiburada ürün detay sayfasından güvenli veri çeker."""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--start-maximized"
                    ]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800}
                )
                page = await context.new_page()
                
                await page.goto(self.url, timeout=45000)
                
                # KRİTİK DÜZELTME: Hepsiburada'nın dinamik fiyat/başlık scriptlerinin yüklenmesi için bekliyoruz
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except:
                    await asyncio.sleep(3) # Eğer networkidle takılırsa manuel 3 saniye bekle

                # Başlık bulma (Sayfadaki ilk h1 etiketi genellikle ürün adıdır)
                title = ""
                try:
                    h1_el = page.locator("h1").first
                    if await h1_el.count() > 0:
                        title = (await h1_el.inner_text()).strip()
                except:
                    pass

                # Fiyat bulma (Alternatif seçicilerle arama)
                price = 0.0
                price_text = ""
                price_selectors = [
                    "[data-test-id='price-current-price']",
                    "span[data-test-id='price']",
                    ".price-value",
                    "#offering-price",
                    "span.price",
                    "div[class*='price']"
                ]

                for sel in price_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.count() > 0:
                            price_text = await el.inner_text()
                            if price_text and any(char.isdigit() for char in price_text):
                                break
                    except:
                        continue

                # Eğer standart seçiciler kaçırdıysa metin içinde TL geçen kısa alanları tara
                if not price_text:
                    try:
                        all_spans = await page.locator("span").all_inner_texts()
                        for text in all_spans:
                            if "TL" in text and any(d.isdigit() for d in text) and len(text) < 15:
                                price_text = text
                                break
                    except:
                        pass

                # Fiyat metnini sayıya (float) çevir
                if price_text:
                    clean_text = re.sub(r'[^\d,\.]', '', price_text)
                    if ',' in clean_text and '.' in clean_text:
                        clean_text = clean_text.replace('.', '').replace(',', '.')
                    elif ',' in clean_text:
                        clean_text = clean_text.replace(',', '.')
                    try:
                        price = float(clean_text)
                    except:
                        price = 0.0

                match = re.search(r'-p-([A-Z0-9]+)', self.url)
                platform_product_id = match.group(1) if match else self.url.split('/')[-1].split('?')[0]

                await browser.close()

                # Hangi ürünün çekilip çekilemediğini görmek için debug çıktısı
                if not title or price == 0:
                    print(f"  ⚠️ Bulunamadı -> Başlık: '{title}' | Fiyat Metni: '{price_text}'")
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
            print(f"❌ Hepsiburada scraper kritik hata: {e}")
            return None