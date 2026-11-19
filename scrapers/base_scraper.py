from abc import ABC, abstractmethod

class BaseScraper(ABC):
    """
    Tüm e-ticaret scraper'larının türemesi gereken soyut üst sınıf (Interface).
    Strategy Pattern mimarisinin temelini oluşturur.
    """
    
    def __init__(self, url: str):
        self.url = url

    @abstractmethod
    def fetch_product_data(self) -> dict:
        """
        Hedef URL'den HTML içeriğini çeker ve ayrıştırır (parse eder).
        Geriye standart bir ürün sözlüğü (dictionary) döndürmelidir:
        {
            "platform_product_id": str,
            "title": str,
            "category": str,
            "price": float,
            "original_price": float,
            "discount_percentage": int,
            "in_stock": bool,
            "url": str
        }
        """
        pass

    def validate_data(self, data: dict) -> bool:
        """Çekilen verinin eksik veya hatalı olup olmadığını kontrol eden ortak metot."""
        required_keys = ["platform_product_id", "title", "price", "url"]
        for key in required_keys:
            if not data.get(key):
                print(f"⚠️ Uyarı: '{key}' alanı eksik veya boş!")
                return False
        return True