import psycopg
from dotenv import load_dotenv
import os
import sys

class StockDAO:
    def __init__(self):
        load_dotenv()
        host = os.environ.get("DB_HOST")
        database = os.environ.get("DB_NAME")
        user = os.environ.get("DB_USER")
        password = os.environ.get("DB_PASSWORD")

        try:
            conn = psycopg.connect(
                host=host,
                dbname=database,
                user=user,
                password=password
            )
            cur = conn.cursor()
            self.cur = cur
        except Exception as e:
            print(f"エラー発生: {e}")

    def create_companies_table(self):
        """companiesテーブルの作成（プライマリキー追加）"""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS companies (
            date DATE,
            company_name VARCHAR(255),
            code VARCHAR(10),
            company_name_en VARCHAR(255),
            industry_code VARCHAR(10),
            industry_name VARCHAR(255),
            market_code VARCHAR(10),
            market_name VARCHAR(255),
            scale VARCHAR(50),
            category_code VARCHAR(10),
            category_name VARCHAR(255),
            PRIMARY KEY (code, date)
        );
        """
        self.cur.execute(create_table_query)

    def insert_company_data(self, company_data):
        """企業データの挿入または更新"""
        upsert_query = """
        INSERT INTO companies (
            date, company_name, code, company_name_en, 
            industry_code, industry_name, market_code, market_name,
            scale, category_code, category_name
        ) VALUES (
            %(Date)s, %(CompanyName)s, %(Code)s, %(CompanyNameEnglish)s,
            %(Sector17Code)s, %(Sector17CodeName)s, %(MarketCode)s, %(MarketCodeName)s,
            %(ScaleCategory)s, %(Sector33Code)s, %(Sector33CodeName)s
        )
        ON CONFLICT (code, date) DO UPDATE SET
            company_name = EXCLUDED.company_name,
            company_name_en = EXCLUDED.company_name_en,
            industry_code = EXCLUDED.industry_code,
            industry_name = EXCLUDED.industry_name,
            market_code = EXCLUDED.market_code,
            market_name = EXCLUDED.market_name,
            scale = EXCLUDED.scale,
            category_code = EXCLUDED.category_code,
            category_name = EXCLUDED.category_name;
        """
        self.cur.execute(upsert_query, company_data)

    def fetch_company_code_list(self):
        """全上場企業のコードを取得"""

        try:
            # companiesテーブルから全てのコードを取得
            select_query = """
            SELECT code FROM companies
            WHERE market_name NOT IN ('その他');
            """
            self.cur.execute(select_query)
            codes = self.cur.fetchall()
            print(codes)
            return [code[0] for code in codes]

        except Exception as e:
            print(f"エラー発生: {e}")
            return None
        finally:
            if 'cur' in locals():
                self.cur.close()
            if 'conn' in locals():
                self.conn.close()

               
    def insert_stock_price_data(self, stock_price_data):
        industry_name = "test";
        """
        株価データの挿入または更新
        stock_price_dataは以下のキーを含む辞書である必要があります:
        - code: 株式コード
        - date: 日付 (YYYY-MM-DD 形式またはDATE型にキャスト可能な文字列)
        - open: 始値
        - high: 高値
        - low: 安値
        - close: 終値
        - volume: 出来高
        """
        upsert_query = """
        INSERT INTO stock_prices (
            code, date, open, high, low, close, volume
        ) VALUES (
            %(code)s, %(date)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s
        )
        ON CONFLICT (code, date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume;
        """
        self.cur.execute(upsert_query, stock_price_data,{"industry_name":industry_name})
                    
    def close(self):
        """クローズ処理をまとめたメソッド"""
        try:
            if self.cur and not self.cur.closed:
                self.cur.close()
            if self.conn and not self.conn.closed:
                self.conn.close()
        except Exception as e:
            print(f"クローズ時エラー: {e}")
            
    def fetch_company_info(self, code):
        code = code + "0" # 会社情報取得時は末尾の0を追加
        select_query = """
        SELECT * FROM companies WHERE code = %(code)s
        """
        self.cur.execute(select_query, {"code":code})
        return self.cur.fetchall()[0] # 1件のみ取得


if __name__ == "__main__":
    dao = StockDAO()
    company_info = dao.fetch_company_info("7203")
    print("company_info:", company_info)
    print("indutrty_name:", company_info[3])