import psycopg
from dotenv import load_dotenv
import os
import sys

def create_companies_table(cur):
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
    cur.execute(create_table_query)

def insert_company_data(cur, company_data):
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
    cur.execute(upsert_query, company_data)

def fetch_company_code_list():
    """全上場企業のコードを取得"""
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

        # companiesテーブルから全てのコードを取得
        select_query = """
        SELECT code FROM companies
        WHERE market_name NOT IN ('その他');
        """
        cur.execute(select_query)
        codes = cur.fetchall()
        print(codes)
        return [code[0] for code in codes]

    except Exception as e:
        print(f"エラー発生: {e}")
        return None
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

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
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()
