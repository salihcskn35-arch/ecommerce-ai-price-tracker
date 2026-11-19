import asyncio
import concurrent.futures
import os
import re
import sys
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db_connection
from main import scrape_on_demand_for_query
from backend.llm_service import parse_shopping_intent, generate_assistant_reply

app = FastAPI(title="AI Alışveriş Asistanı API", version="3.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _query_db(cursor, keyword: str, max_price: float | None, limit: int):
    tokens = [t for t in re.split(r"\s+", keyword.strip().lower()) if len(t) > 1]
    if not tokens:
        tokens = [keyword.strip().lower()]

    conditions = ["f.price > 0 AND f.price <= 500000"]
    params = []

    for token in tokens:
        term = f"%{token}%"
        conditions.append("(p.title ILIKE %s OR p.category ILIKE %s)")
        params.extend([term, term])

    if max_price is not None:
        conditions.append("f.price <= %s")
        params.append(max_price)

    sql = f"""
        SELECT 
            p.platform,
            p.title,
            f.price,
            p.url,
            p.category
        FROM dim_product p
        JOIN LATERAL (
            SELECT price FROM fact_price_history 
            WHERE product_id = p.product_id 
            ORDER BY recorded_at DESC LIMIT 1
        ) f ON true
        WHERE {" AND ".join(conditions)}
        ORDER BY f.price ASC
        LIMIT %s;
    """
    params.append(limit)
    cursor.execute(sql, tuple(params))
    return cursor.fetchall()


def _run_jit_scrape_sync(keyword: str, category_name: str = "Akıllı Arama"):
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                scrape_on_demand_for_query(keyword, category_name=category_name)
            )
        finally:
            loop.close()
    return asyncio.run(scrape_on_demand_for_query(keyword, category_name=category_name))


@app.get("/")
def read_root():
    return {"message": "Gemini Destekli AI Alışveriş Asistanı Backend Aktif!"}


@app.get("/api/search")
async def search_products(q: str = Query(..., description="Kullanıcının doğal dildeki isteği")):
    intent = parse_shopping_intent(q)
    clean_keyword = intent.search_query
    max_price = intent.max_price
    limit = intent.limit

    print(f"🤖 [Gemini Niyet] q='{q}' -> keyword='{clean_keyword}', max_price={max_price}, limit={limit}")

    conn = get_db_connection()
    if not conn:
        return {"error": "Veritabanı bağlantısı kurulamadı."}

    cursor = conn.cursor()
    rows = _query_db(cursor, clean_keyword, max_price, limit)

    # DB'de sonuç yoksa JIT scraping tetikle
    if not rows:
        cursor.close()
        conn.close()

        print(f"⚠️ Veritabanında '{clean_keyword}' bulunamadı. JIT Tarama başlatılıyor...")
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            await loop.run_in_executor(pool, _run_jit_scrape_sync, clean_keyword, "Akıllı Arama")

        conn = get_db_connection()
        cursor = conn.cursor()
        rows = _query_db(cursor, clean_keyword, max_price, limit)

    fallback_used = False
    # Bütçe kısıtı yüzünden hiç ürün çıkmadıysa bütçesiz en uygunları getir
    if not rows and max_price is not None:
        rows = _query_db(cursor, clean_keyword, None, limit)
        if rows:
            fallback_used = True

    cursor.close()
    conn.close()

    products = [
        {
            "platform": r[0],
            "title": r[1],
            "price": r[2],
            "url": r[3],
            "category": r[4],
        }
        for r in rows
    ]

    reply = generate_assistant_reply(q, products, clean_keyword)
    if fallback_used and products:
        reply = (
            f"{int(max_price) if max_price.is_integer() else max_price} TL bütçenin altında ürün bulamadım ama "
            f"en uygun seçenekleri listeledim: {reply}"
        )

    return {
        "query": q,
        "clean_keyword": clean_keyword,
        "max_price": max_price,
        "fallback_used": fallback_used,
        "reply": reply,
        "count": len(products),
        "products": products,
    }