import psycopg
from dotenv import load_dotenv
import os
import sys

def create_companies_table(cur):
    """companiesテーブルの作成"""
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
        category_name VARCHAR(255)
    );
    """
    cur.execute(create_table_query)

def insert_company_data(cur, company_data):
    """企業データの挿入"""
    insert_query = """
    INSERT INTO companies (
        date, company_name, code, company_name_en, 
        industry_code, industry_name, market_code, market_name,
        scale, category_code, category_name
    ) VALUES (
        %(Date)s, %(CompanyName)s, %(Code)s, %(CompanyNameEnglish)s,
        %(Sector17Code)s, %(Sector17CodeName)s, %(MarketCode)s, %(MarketCodeName)s,
        %(ScaleCategory)s, %(Sector33Code)s, %(Sector33CodeName)s
    );
    """
    cur.execute(insert_query, company_data)

def main():
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
        
        # テーブル作成
        create_companies_table(cur)
        
        # データ挿入（APIレスポンスデータを想定）
        for company in api_response_data:
            insert_company_data(cur, company)
        
        conn.commit()
        print("データの挿入が完了しました")
        
    except Exception as e:
        print(f"エラー発生: {e}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()