# 🛍️ AI E-Commerce Price Tracker & Shopping Assistant

Trendyol, Amazon Türkiye ve N11 platformlarından gerçek zamanlı (Just-In-Time) ve toplu ürün verisi toplayan, PostgreSQL veri ambarı mimarisiyle fiyat geçmişi tutan ve **Gemini API** ile doğal dildeki kullanıcı sorgularını analiz eden yapay zeka destekli alışveriş asistanı.

## 🚀 Öne Çıkan Özellikler

* **Doğal Dil Niyet Analizi (Gemini API):** *"Bütçem 3000 TL, bana en uygun 3 oyuncu kulaklığı getirir misin?"* gibi doğal dil sorgularından ürün anahtar kelimesini, bütçe sınırını (`max_price`) ve ürün adedini (`limit`) yapılandırılmış JSON şemasıyla çıkarır.
* **Hibrit Veri Toplama (ETL + JIT Scraping):** Ürün veritabanında mevcutsa milisaniyeler içinde döner; yoksa arka planda asenkron Playwright tarayıcılarıyla Trendyol, Amazon ve N11 üzerinde canlı arama yapıp veritabanını besler.
* **Star Schema Veri Ambarı & Smart Delta Check:** `dim_product` ve `fact_price_history` tabloları ile yalnızca fiyat değiştiğinde yeni kayıt atarak veri tekrarını önler.
* **Akıllı Fiyat Temizleme ve Anomali Filtresi:** Türkiye e-ticaret formatındaki binlik/ondalık ayraçlarını (`1.199 TL`, `1.299,50 TL`) normalize eder ve hatalı/uçuk fiyat verilerini filtreler.

## 🛠️ Teknoloji Yığını

* **Backend:** Python, FastAPI, Uvicorn
* **AI / LLM:** Google GenAI SDK (`gemini-3.5-flash-lite`), Pydantic Structured Outputs
* **Web Scraping:** Playwright (Async), BeautifulSoup4, Requests
* **Veritabanı:** PostgreSQL (`psycopg2`)
* **Frontend:** HTML5, CSS3, Vanilla JavaScript

## ⚙️ Kurulum ve Çalıştırma

1. **Repoyu klonlayın:**
   ```bash
   git clone [https://github.com/KULLANICI_ADIN/ecommerce-ai-price-tracker.git](https://github.com/KULLANICI_ADIN/ecommerce-ai-price-tracker.git)
   cd ecommerce-ai-price-tracker