import os
import psycopg2
from dotenv import load_dotenv


load_dotenv()

def get_db_connection():
    """PostgreSQL veritabanına güvenli bağlantı nesnesi döndürür."""
    try:
        connection = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=os.getenv("DB_PORT", 5432)
        )
        return connection
    except Exception as e:
        print(f"❌ Veritabanı bağlantı hatası: {e}")
        return None

if __name__ == "__main__":

    conn = get_db_connection()
    if conn:
        print("✅ PostgreSQL veritabanına başarıyla bağlandı!")
        conn.close()