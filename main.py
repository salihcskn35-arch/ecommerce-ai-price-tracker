import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright
from database import get_db_connection
from scrapers.trendyol_scraper import TrendyolScraper
from scrapers.amazon_scrapper import AmazonScraper
from scrapers.n11_scrapper import N11Scraper


def _is_valid_price(price) -> bool:
    try:
        val = float(price)
        return 0 < val <= 500000
    except (TypeError, ValueError):
        return False


async def get_product_urls(platform: str, search_url: str, max_pages: int = 5) -> list:
    """Seçilen platforma göre arama sayfalarından ürün linkleri toplar."""
    product_urls = set()

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

        for page_num in range(1, max_pages + 1):
            # Platforma özel sayfalama URL yapısı
            if platform == "trendyol":
                paged_url = f"{search_url}&pi={page_num}" if "?" in search_url else f"{search_url}?pi={page_num}"
            elif platform == "amazon":
                paged_url = f"{search_url}&page={page_num}" if "?" in search_url else f"{search_url}?page={page_num}"
            elif platform == "n11":
                paged_url = f"{search_url}&pg={page_num}" if "?" in search_url else f"{search_url}?pg={page_num}"
            else:
                paged_url = search_url

            print(f"📄 [{platform.upper()}] Arka planda taranıyor (Sayfa {page_num}/{max_pages}): {paged_url}")

            try:
                await page.goto(paged_url, timeout=35000)
                await page.wait_for_load_state("domcontentloaded")
                
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

                links = await page.eval_on_selector_all("a", "elements => elements.map(e => e.href)")
                
                for href in links:
                    if platform == "trendyol" and "-p-" in href:
                        product_urls.add(href.split("?")[0])
                    elif platform == "amazon" and "/dp/" in href:
                        base_url = href.split("/ref=")[0]
                        if "amazon.com.tr" in base_url:
                            product_urls.add(base_url)
                    elif platform == "n11" and "/urun/" in href:
                        clean_url = href.split("?")[0]
                        if "n11.com" in clean_url:
                            product_urls.add(clean_url)

                print(f"   ↳ Bu sayfadan sonra toplam benzersiz ürün linki: {len(product_urls)}")

            except Exception as e:
                print(f"❌ [{platform.upper()}] Sayfa tarama hatası (Sayfa {page_num}): {e}")
                break

        await browser.close()

    return list(product_urls)


def save_product_to_db(cursor, data: dict, platform_name: str, category_name: str):
    """Dim_product tablosuna upsert yapar ve Smart Delta Check ile fiyat geçmişini kaydeder."""
    try:
        if not _is_valid_price(data.get("price")):
            print(f"⚠️ [{platform_name.upper()}] Geçersiz/anormal fiyat atlandı -> {data.get('price')} TL")
            return

        upsert_product_query = """
            INSERT INTO dim_product (platform, platform_product_id, title, category, url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (platform, platform_product_id) 
            DO UPDATE SET title = EXCLUDED.title, category = EXCLUDED.category, url = EXCLUDED.url
            RETURNING product_id;
        """
        cursor.execute(upsert_product_query, (
            platform_name, data["platform_product_id"], data["title"], category_name, data["url"]
        ))
        product_id = cursor.fetchone()[0]

        cursor.execute("""
            SELECT price FROM fact_price_history 
            WHERE product_id = %s 
            ORDER BY recorded_at DESC 
            LIMIT 1;
        """, (product_id,))
        
        last_record = cursor.fetchone()
        last_price = last_record[0] if last_record else None

        if last_price is None or last_price != data["price"]:
            insert_price_query = """
                INSERT INTO fact_price_history (product_id, price, original_price, discount_percentage, in_stock)
                VALUES (%s, %s, %s, %s, %s);
            """
            cursor.execute(insert_price_query, (
                product_id, data["price"], data["original_price"], data["discount_percentage"], data["in_stock"]
            ))
            print(f"💾 [{platform_name.upper()}] Kaydedildi -> {data['title'][:30]}... | Fiyat: {data['price']} TL")
        else:
            print(f"💤 [{platform_name.upper()}] Fiyat aynı ({data['price']} TL), pas geçildi.")

    except Exception as e:
        print(f"❌ Veritabanı kayıt hatası: {e}")


async def scrape_on_demand_for_query(query: str, category_name: str = "Özel Arama"):
    """
    🧠 ÇÖZÜM 1 (JIT Scraping): Veritabanında bulunmayan bir ürün istendiğinde 
    anlık olarak tüm platformlarda arama yapıp veritabanını besler.
    """
    print(f"🔄 [JIT SCRAPING] Veritabanında bulunamadı. '{query}' için anlık tarama başlatılıyor...")
    
    q_encoded = query.replace(" ", "+")
    dynamic_targets = [
        {"platform": "trendyol", "category": category_name, "url": f"https://www.trendyol.com/sr?q={q_encoded}"},
        {"platform": "amazon", "category": category_name, "url": f"https://www.amazon.com.tr/s?k={q_encoded}"},
        {"platform": "n11", "category": category_name, "url": f"https://www.n11.com/arama?q={q_encoded}"}
    ]
    
    conn = get_db_connection()
    if not conn:
        print("❌ Veritabanı bağlantısı kurulamadı.")
        return 0
    cursor = conn.cursor()

    total_saved = 0
    for target in dynamic_targets:
        plat = target["platform"]
        cat_name = target["category"]
        search_url = target["url"]
        
        # Anlık aramada hız için 1 sayfa ve en fazla ilk 12 link taranır
        urls = await get_product_urls(plat, search_url, max_pages=1)
        urls = urls[:12]
        
        for index, url in enumerate(urls, 1):
            if plat == "trendyol":
                scraper = TrendyolScraper(url)
            elif plat == "amazon":
                scraper = AmazonScraper(url)
            elif plat == "n11":
                scraper = N11Scraper(url)
            else:
                continue
            
            try:
                product_data = await scraper.fetch_product_data()
            except Exception:
                product_data = None
            
            if product_data:
                save_product_to_db(cursor, product_data, plat, cat_name)
                conn.commit()
                total_saved += 1

    cursor.close()
    conn.close()
    print(f"✨ [JIT SCRAPING] Tamamlandı! '{query}' için {total_saved} yeni ürün sisteme kazandırıldı.")
    return total_saved


async def main():
    # 📌 Trendyol, Amazon ve N11 İçin Kapsamlı Tüm Kategoriler Matrisi (Her biri 5'er sayfa)
    targets = [
        # --- TRENDYOL ---
        {"platform": "trendyol", "category": "Elektronik", "url": "https://www.trendyol.com/sr?q=laptop"},
        {"platform": "trendyol", "category": "Elektronik", "url": "https://www.trendyol.com/sr?q=kablosuz+kulaklik"},
        {"platform": "trendyol", "category": "Spor", "url": "https://www.trendyol.com/sr?q=kosu+ayakkabisi"},
        {"platform": "trendyol", "category": "Giyim", "url": "https://www.trendyol.com/sr?q=erkek+mont"},
        {"platform": "trendyol", "category": "Kozmetik", "url": "https://www.trendyol.com/sr?q=gunes+kremi"},

        # --- AMAZON TÜRKİYE ---
        {"platform": "amazon", "category": "Elektronik", "url": "https://www.amazon.com.tr/s?k=laptop"},
        {"platform": "amazon", "category": "Elektronik", "url": "https://www.amazon.com.tr/s?k=kablosuz+kulaklik"},
        {"platform": "amazon", "category": "Spor", "url": "https://www.amazon.com.tr/s?k=kosu+ayakkabisi"},
        {"platform": "amazon", "category": "Giyim", "url": "https://www.amazon.com.tr/s?k=erkek+mont"},
        {"platform": "amazon", "category": "Kozmetik", "url": "https://www.amazon.com.tr/s?k=gunes+kremi"},

        # --- N11 ---
        {"platform": "n11", "category": "Elektronik", "url": "https://www.n11.com/arama?q=laptop"},
        {"platform": "n11", "category": "Elektronik", "url": "https://www.n11.com/arama?q=kablosuz+kulaklik"},
        {"platform": "n11", "category": "Spor", "url": "https://www.n11.com/arama?q=kosu+ayakkabisi"},
        {"platform": "n11", "category": "Giyim", "url": "https://www.n11.com/arama?q=erkek+mont"},
        {"platform": "n11", "category": "Kozmetik", "url": "https://www.n11.com/arama?q=gunes+kremi"}
    ]
    
    print("🚀 Tam Donanımlı Çoklu Platform (Trendyol + Amazon + N11) ETL Boru Hattı Başlatıldı...\n")
    
    conn = get_db_connection()
    if not conn:
        print("❌ Veritabanı bağlantısı kurulamadı.")
        return
    cursor = conn.cursor()

    total_saved = 0
    for target in targets:
        plat = target["platform"]
        cat_name = target["category"]
        search_url = target["url"]
        
        print(f"\n📂 Platform: {plat.upper()} | Kategori: {cat_name}")
        
        urls = await get_product_urls(plat, search_url, max_pages=5)
        print(f"📦 Toplam {len(urls)} ürün linki bulundu. Veritabanına işleniyor...\n")

        for index, url in enumerate(urls, 1):
            print(f"  [{index}/{len(urls)}] Taranıyor ({plat.upper()}): {url}")
            
            if plat == "trendyol":
                scraper = TrendyolScraper(url)
            elif plat == "amazon":
                scraper = AmazonScraper(url)
            elif plat == "n11":
                scraper = N11Scraper(url)
            else:
                continue
            
            try:
                product_data = await scraper.fetch_product_data()
            except Exception:
                product_data = None
            
            if product_data:
                save_product_to_db(cursor, product_data, plat, cat_name)
                conn.commit()
                total_saved += 1
            else:
                print("  ⚠️ Veri çekilemedi atlanıyor.")

    cursor.close()
    conn.close()
    print(f"\n✨ İşlem Tamamlandı! Toplam {total_saved} ürün tüm platformlardan veritabanına işlendi.")


if __name__ == "__main__":
    asyncio.run(main())