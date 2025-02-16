import sys
import os
import threading
from datetime import date, datetime
from typing import List, Dict, Optional
from .base_repository import BaseRepository

# DDLの実行を排他制御するためのグローバルロック
DDL_LOCK = threading.Lock()

class StockRepository(BaseRepository):
    def insert_company_data(self, company_data: Dict) -> bool:
        """企業情報をデータベースに挿入または更新します"""
        try:
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
            ON CONFLICT (code) DO UPDATE SET
                date = EXCLUDED.date,
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
            self.conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"企業情報の挿入エラー: {e}")
            return False

    def fetch_company_code_list(self) -> List[str]:
        """その他市場を除く全上場企業のコードを取得します"""
        try:
            select_query = """
            SELECT code FROM companies
            WHERE market_name NOT IN ('その他')
            ORDER BY code;
            """
            self.cur.execute(select_query)
            codes = self.cur.fetchall()
            return [code[0] for code in codes]
        except Exception as e:
            self.logger.error(f"企業コード取得エラー: {e}")
            return []

    def insert_stock_price_data(self, stock_price_data: Dict, industry_name: str) -> bool:
        """株価データを業種別テーブルに挿入します"""
        table_name = f"{industry_name}_price"
        try:
            threshold = 100_000_000
            for key in ["open", "high", "low", "close"]:
                if abs(stock_price_data.get(key, 0)) >= threshold:
                    self.logger.warning(f"異常な株価データが検出されたため、インサートをスキップします: {stock_price_data}")
                    return False

            upsert_query = f"""
            INSERT INTO {table_name} (
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
            self.cur.execute(upsert_query, stock_price_data)
            self.conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"株価データ挿入エラー: {e}")
            self.conn.rollback()
            return False 