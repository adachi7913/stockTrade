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

    def fetch_company_info(self, code: str) -> Optional[tuple]:
        """
        指定された証券コードの企業情報を取得します
        
        Args:
            code (str): 証券コード
            
        Returns:
            Optional[tuple]: 企業情報のタプル、取得失敗時はNone
        """
        try:
            query = """
            SELECT 
                date, company_name, code, company_name_en,
                industry_code, industry_name, market_code, market_name,
                scale, category_code, category_name
            FROM companies
            WHERE code = %s;
            """
            self.cur.execute(query, (code,))
            result = self.cur.fetchone()
            return result
        except Exception as e:
            self.logger.error(f"企業情報取得エラー: {e}")
            return None

    def update_market_cap(self, code: str, market_cap: int) -> bool:
        """
        企業の時価総額を更新します
        
        Args:
            code (str): 証券コード
            market_cap (int): 時価総額
            
        Returns:
            bool: 更新成功でTrue
        """
        try:
            # 4桁の場合は末尾に "0" を追加
            companies_code = code + "0" if len(code) == 4 else code

            query = """
            UPDATE companies 
            SET market_cap = %s 
            WHERE code = %s
            """
            self.cur.execute(query, (market_cap, companies_code))
            self.conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"時価総額更新エラー: {e}")
            self.conn.rollback()
            return False

    def get_stock_full_data_period(self, code: str, industry_name: str) -> List[Dict]:
        """
        指定された証券コードの株価データと指標データを取得します
        
        Args:
            code (str): 証券コード
            industry_name (str): 業種名
            
        Returns:
            List[Dict]: 株価データと指標データのリスト
        """
        try:
            query = f"""
            WITH price_data AS (
                SELECT p.*, i.macd, i.signal, i.rsi, i.stoch, i.bb, i.atr
                FROM {industry_name}_price p
                LEFT JOIN {industry_name}_indicator i ON p.code = i.code AND p.date = i.date
                WHERE p.code = %s
                ORDER BY p.date DESC
                LIMIT 100
            )
            SELECT * FROM price_data ORDER BY date ASC;
            """
            
            self.cur.execute(query, (code,))
            rows = self.cur.fetchall()
            
            result = []
            for row in rows:
                data = {
                    'date': row[1],
                    'open': float(row[2]),
                    'high': float(row[3]),
                    'low': float(row[4]),
                    'close': float(row[5]),
                    'volume': int(row[6]),
                    'macd': row[7],
                    'signal': row[8],
                    'rsi': row[9],
                    'stoch': row[10],
                    'bb': row[11],
                    'atr': row[12]
                }
                result.append(data)
            
            return result
            
        except Exception as e:
            self.logger.error(f"株価データ取得エラー: {e}")
            return []

    def fetch_market_cap(self, code: str) -> Optional[int]:
        """
        指定された証券コードの時価総額を取得します
        
        Args:
            code (str): 証券コード
            
        Returns:
            Optional[int]: 時価総額、取得失敗時はNone
        """
        try:
            # 4桁の場合は末尾に "0" を追加
            companies_code = code + "0" if len(code) == 4 else code
            
            query = """
            SELECT market_cap 
            FROM companies 
            WHERE code = %s;
            """
            self.cur.execute(query, (companies_code,))
            result = self.cur.fetchone()
            return result[0] if result else None
            
        except Exception as e:
            self.logger.error(f"時価総額取得エラー: {e}")
            return None

    def fetch_no_entry_info(self, code: str) -> Optional[tuple]:
        """
        指定された証券コードのエントリー不可情報を取得します
        
        Args:
            code (str): 証券コード
            
        Returns:
            Optional[tuple]: (最終エントリー日, エントリー不可期間)のタプル、取得失敗時はNone
        """
        try:
            query = """
            SELECT last_entry_date, no_entry_span
            FROM no_entry_info
            WHERE code = %s;
            """
            self.cur.execute(query, (code,))
            result = self.cur.fetchone()
            return result if result else None
            
        except Exception as e:
            self.logger.error(f"エントリー不可情報取得エラー: {e}")
            return None

    def insert_indicator_data(self, indicator_data: Dict, code: str, industry_name: str) -> bool:
        """
        指標データを業種別テーブルに挿入します
        
        Args:
            indicator_data (Dict): 挿入する指標データ
            code (str): 証券コード
            industry_name (str): 業種名
            
        Returns:
            bool: 挿入成功でTrue
        """
        table_name = f"{industry_name}_indicator"
        try:
            upsert_query = f"""
            INSERT INTO {table_name} (
                code, date, macd, signal, rsi, stoch, bb, atr
            ) VALUES (
                %(code)s, %(date)s, %(macd)s, %(signal)s, 
                %(rsi)s, %(stoch)s, %(bb)s, %(atr)s
            )
            ON CONFLICT (code, date) DO UPDATE SET
                macd = EXCLUDED.macd,
                signal = EXCLUDED.signal,
                rsi = EXCLUDED.rsi,
                stoch = EXCLUDED.stoch,
                bb = EXCLUDED.bb,
                atr = EXCLUDED.atr;
            """
            
            self.cur.execute(upsert_query, indicator_data)
            self.conn.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"指標データ挿入エラー: {e}")
            self.conn.rollback()
            return False

    def insert_api_response(self, response_data: Dict) -> bool:
        """
        API応答データをデータベースに挿入します
        
        Args:
            response_data (Dict): 挿入するAPI応答データ
            
        Returns:
            bool: 挿入成功でTrue
        """
        try:
            query = """
            INSERT INTO api_response (
                code, date, close, rule_entry_price, rule_stop_limit,
                rule_top_price, rule_period, risk_reward, entry_score,
                expected_return, reason
            ) VALUES (
                %(code)s, %(date)s, %(close)s, %(entry_price)s, %(stop_loss)s,
                %(target_price)s, %(period)s, %(risk_reward)s, %(entry_score)s,
                %(expected_return)s, %(reason)s
            );
            """
            
            self.cur.execute(query, response_data)
            self.conn.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"API応答データ挿入エラー: {e}")
            self.conn.rollback()
            return False 