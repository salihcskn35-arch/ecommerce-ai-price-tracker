import json
import re
import requests
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper

class TrendyolScraper(BaseScraper):
    def fetch_product_data(self) -> dict:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Referer": "https://www.trendyol.com/"
        }

        try:
            response = requests.get(self.url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"❌ Trendyol HTTP Hatası: {response.status_code} - URL: {self.url}")
                return None

            soup = BeautifulSoup(response.text, "html.parser")
            product_id = self._extract_product_id(self.url)

            title = "Bilinmeyen Ürün"
            price = 0.0
            original_price = 0.0
            discount_percentage = 0
            in_stock = True

            # 1. YÖNTEM: Sayfadaki JSON-LD (Schema.org) verisini yakala (En Sağlam Yöntem)
            json_ld_script = soup.find("script", type="application/ld+json")
            if json_ld_script:
                try:
                    ld_data = json.loads(json_ld_script.string)
                    if isinstance(ld_data, list):
                        ld_data = ld_data[0]
                    
                    if "name" in ld_data:
                        title = ld_data["name"]
                    
                    if "offers" in ld_data:
                        offers = ld_data["offers"]
                        if isinstance(offers, list):
                            offers = offers[0]
                        if "price" in offers:
                            price = float(offers["price"])
                            original_price = price
                        if "availability" in offers and "OutOfStock" in offers["availability"]:
                            in_stock = False
                except Exception as e:
                    print(f"⚠️ JSON-LD parse uyarısı: {e}")

            # 2. YÖNTEM (Fallback): Eğer JSON-LD'den fiyat gelmediyse klasik CSS seçicileri dene
            if price == 0.0:
                price_selectors = [
                    "span.prc-dsc", 
                    "div.prc-box-dsc", 
                    "span[class*='price']",
                    ".product-price-container span"
                ]
                for sel in price_selectors:
                    elem = soup.select_one(sel)
                    if elem:
                        price = self._parse_price(elem.get_text(strip=True))
                        if price > 0:
                            break

            if original_price == 0.0 or original_price < price:
                original_price = price

            if original_price > price and original_price > 0:
                discount_percentage = int(round((original_price - price) / original_price * 100))

            product_data = {
                "platform_product_id": product_id,
                "title": title,
                "category": "Genel",
                "price": price,
                "original_price": original_price,
                "discount_percentage": discount_percentage,
                "in_stock": in_stock,
                "url": self.url
            }

            if self.validate_data(product_data):
                return product_data
            
            return None

        except Exception as e:
            print(f"❌ Trendyol Scraper Çalışma Hatası ({self.url}): {e}")
            return None

    def _extract_product_id(self, url: str) -> str:
        match = re.search(r"-p-(\d+)", url)
        if match:
            return match.group(1)
        return url.split("/")[-1].split("?")[0]

    def _parse_price(self, price_str: str) -> float:
        try:
            # TL, ₺ ve boşlukları temizle
            clean_str = price_str.replace("TL", "").replace("₺", "").strip()
            # Noktaları (binlik ayracı) kaldır, virgülü (ondalık ayracı) noktaya çevir
            clean_str = clean_str.replace(".", "").replace(",", ".")
            numeric_str = re.sub(r"[^\d.]", "", clean_str)
            return float(numeric_str) if numeric_str else 0.0
        except Exception:
            return 0.0