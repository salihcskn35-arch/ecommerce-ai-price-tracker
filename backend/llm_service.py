import os
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

load_dotenv()

MODEL_NAME = "gemini-3.5-flash-lite"


class SearchIntent(BaseModel):
    search_query: str = Field(
        description="E-ticaret sitesinde aranacak net ürün adı veya anahtar kelimesi (örn: 'v yaka t-shirt', 'oyuncu kulakligi', 'laptop')"
    )
    max_price: Optional[float] = Field(
        default=None,
        description="Kullanıcının belirttiği maksimum bütçe (TL cinsinden sayı). Belirtilmemişse None."
    )
    limit: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Getirilecek ürün sayısı. Kullanıcı özel sayı belirtmezse 3."
    )


def _get_client() -> Optional[genai.Client]:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def parse_shopping_intent(user_message: str) -> SearchIntent:
    """Kullanıcının doğal dildeki mesajını yapılandırılmış arama niyetine çevirir."""
    client = _get_client()
    if not client:
        return SearchIntent(search_query=user_message.strip(), max_price=None, limit=3)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=f"Kullanıcı mesajı: {user_message}",
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Sen bir e-ticaret alışveriş asistanının niyet analiz motorusun. "
                    "Kullanıcının mesajından e-ticaret aramasında kullanılacak en uygun ürün anahtar kelimesini, "
                    "varsa TL cinsinden maksimum bütçeyi ve istenen ürün adedini çıkar. "
                    "Gereksiz sohbet kelimelerini ('en ucuz', 'bana bul', 'var mı', 'istiyorum') search_query içine koyma."
                ),
                response_mime_type="application/json",
                response_schema=SearchIntent,
                temperature=0.1,
            ),
        )
        if response.parsed:
            return response.parsed
    except Exception as e:
        print(f"⚠️ Gemini niyet analizi hatası, düz metne düşülüyor: {e}")

    return SearchIntent(search_query=user_message.strip(), max_price=None, limit=3)


def generate_assistant_reply(user_message: str, products: list[dict], search_query: str) -> str:
    """Bulunan ürünlere göre kullanıcıya kısa ve yardımcı bir sohbet özeti yazar."""
    if not products:
        return f"'{search_query}' için şu an kriterlerine uygun ürün bulamadım."

    client = _get_client()
    cheapest = products[0]
    fallback_msg = (
        f"'{search_query}' araması için {len(products)} seçenek buldum. "
        f"En uygun fiyatlı seçenek {cheapest['platform'].upper()} üzerinde {cheapest['price']} TL."
    )

    if not client:
        return fallback_msg

    try:
        compact_items = [
            {
                "platform": p["platform"],
                "title": p["title"],
                "price": float(p["price"]) if p["price"] is not None else None,
            }
            for p in products[:5]
        ]
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=(
                f"Kullanıcı sorusu: {user_message}\n"
                f"Bulunan ürünler (fiyata göre sıralı): {compact_items}\n"
                "Kullanıcıya en fazla 2-3 cümlelik, samimi ve net bir Türkçe özet yaz. "
                "Fiyatları ve platformları uydurma, sadece listedeki verileri kullan."
            ),
            config=types.GenerateContentConfig(
                temperature=0.4,
            ),
        )
        return response.text.strip() if response.text else fallback_msg
    except Exception:
        return fallback_msg