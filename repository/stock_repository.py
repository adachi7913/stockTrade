import sys
import os
import threading
from datetime import date, datetime
from typing import List, Dict, Optional

from lib.table_category import TableCategory
from .base_repository import BaseRepository
import numpy as np
import logging

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
            code (str): 証券コード（4桁）
            industry_name (str): 業種名
            
        Returns:
            List[Dict]: 株価データと指標データのリスト
        """
        try:
            # 環境変数から取得日数を取得
            fetch_range = os.getenv("FETCH_DATA_RANGE", "1")  # 範囲は年数。デフォルトは1年
            
            query = """
            WITH price_data AS (
                SELECT p.*, i.macd, i.stoch_k, i.stoch_d, i.rsi, i.bb_lower, i.bb_middle, i.bb_upper, i.atr
                FROM {}_price p
                LEFT JOIN {}_indicator i ON p.code = i.code AND p.date = i.date
                WHERE p.code = %s
                AND p.date BETWEEN (CURRENT_DATE - (%s || ' years')::interval) AND CURRENT_DATE
                ORDER BY p.date DESC
            )
            SELECT * FROM price_data ORDER BY date ASC;
            """.format(industry_name, industry_name)
            
            
            self.cur.execute(query, (code, fetch_range))
            rows = self.cur.fetchall()
            
            if not rows:
                self.logger.error(f"データが取得できませんでした: code={code}, industry_name={industry_name}")
                return []
                
            
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
                    'stoch_k': row[8],
                    'stoch_d': row[9],
                    'rsi': row[10],
                    'bb_lower': row[11],
                    'bb_middle': row[12],
                    'bb_upper': row[13],
                    'atr': row[14]
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
        指定された銘柄コードに対して、api_responseテーブルから最新のAPI応答の date と rule_period を
        no_entry_span として取得して返します。

        Args:
            code (str): 銘柄コード

        Returns:
            Optional[tuple]: (最新のAPI応答の日付, no_entry_span) のタプル、取得失敗時は None
        """
        try:
            query = """
            SELECT date, no_entry_span
            FROM api_response
            WHERE code = %s
            ORDER BY date DESC
            LIMIT 1;
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
            # 追加：インジケーター計算に必要なデータが不足している場合は、INSERTをスキップしログ出力する
            if (indicator_data.get('ichimoku_tenkan', None) == 0 or
                indicator_data.get('ichimoku_kijun', None) == 0 or
                indicator_data.get('ichimoku_senkou_a', None) == 0 or
                indicator_data.get('ichimoku_senkou_b', None) == 0 or
                indicator_data.get('adx', None) == 0 or
                indicator_data.get('bb_lower', None) == 0 or
                indicator_data.get('bb_middle', None) == 0 or
                indicator_data.get('bb_upper', None) == 0 or
                indicator_data.get('stoch_k', None) == 0 or
                indicator_data.get('stoch_d', None) == 0 or
                indicator_data.get('atr', None) == 0 or
                indicator_data.get('rsi', None) == 0 or
                indicator_data.get('macd', None) == 0 or
                indicator_data.get('dynamic_threshold', None) == 0 or
                indicator_data.get('pca_signal', None) == 0 or
                indicator_data.get('weekly_trend', None) == 'UNKNOWN'):
                logging.warning(f"インジケーター計算に必要なデータが不足しているため、銘柄 {code} のデータ挿入をスキップします: {indicator_data}")
                return False

            # 安全に丸めるヘルパー関数
            def safe_round(value, ndigits=2):
                try:
                    if isinstance(value, (int, float)) and not np.isnan(value):
                        return round(value, ndigits)
                    return 0
                except Exception:
                    return 0

            upsert_query = f"""
            INSERT INTO {table_name} (
                code, date, ichimoku_tenkan, ichimoku_kijun, ichimoku_senkou_a, ichimoku_senkou_b,
                adx, bb_lower, bb_middle, bb_upper, stoch_k, stoch_d, atr, rsi, macd,
                dynamic_threshold, weekly_trend, pca_signal
            ) VALUES (
                %(code)s, %(date)s, %(ichimoku_tenkan)s, %(ichimoku_kijun)s, 
                %(ichimoku_senkou_a)s, %(ichimoku_senkou_b)s, %(adx)s,
                %(bb_lower)s, %(bb_middle)s, %(bb_upper)s,
                %(stoch_k)s, %(stoch_d)s, %(atr)s, %(rsi)s, %(macd)s,
                %(dynamic_threshold)s, %(weekly_trend)s, %(pca_signal)s
            )
            ON CONFLICT (code, date) DO UPDATE SET
                ichimoku_tenkan = EXCLUDED.ichimoku_tenkan,
                ichimoku_kijun = EXCLUDED.ichimoku_kijun,
                ichimoku_senkou_a = EXCLUDED.ichimoku_senkou_a,
                ichimoku_senkou_b = EXCLUDED.ichimoku_senkou_b,
                adx = EXCLUDED.adx,
                bb_lower = EXCLUDED.bb_lower,
                bb_middle = EXCLUDED.bb_middle,
                bb_upper = EXCLUDED.bb_upper,
                stoch_k = EXCLUDED.stoch_k,
                stoch_d = EXCLUDED.stoch_d,
                atr = EXCLUDED.atr,
                rsi = EXCLUDED.rsi,
                macd = EXCLUDED.macd,
                dynamic_threshold = EXCLUDED.dynamic_threshold,
                weekly_trend = EXCLUDED.weekly_trend,
                pca_signal = EXCLUDED.pca_signal;
            """

            # リスト形式のデータを辞書形式に変換
            if isinstance(indicator_data, list):
                for data in indicator_data:
                    params = {
                        'code': code,
                        'date': data[0] if isinstance(data, (list, tuple)) else data.get('date'),
                        'ichimoku_tenkan': safe_round(data.get('ichimoku_tenkan', 0)),
                        'ichimoku_kijun': safe_round(data.get('ichimoku_kijun', 0)),
                        'ichimoku_senkou_a': safe_round(data.get('ichimoku_senkou_a', 0)),
                        'ichimoku_senkou_b': safe_round(data.get('ichimoku_senkou_b', 0)),
                        'adx': safe_round(data.get('adx', 0)),
                        'bb_lower': safe_round(data.get('bb_lower', 0)),
                        'bb_middle': safe_round(data.get('bb_middle', 0)),
                        'bb_upper': safe_round(data.get('bb_upper', 0)),
                        'stoch_k': safe_round(data.get('stoch_k', 0)),
                        'stoch_d': safe_round(data.get('stoch_d', 0)),
                        'atr': safe_round(data.get('atr', 0)),
                        'rsi': safe_round(data.get('rsi', 0)),
                        'macd': safe_round(data.get('macd', 0)),
                        'dynamic_threshold': data.get('dynamic_threshold', None),
                        'weekly_trend': data.get('weekly_trend', None),
                        'pca_signal': data.get('pca_signal', None)
                    }
                    self.cur.execute(upsert_query, params)
            else:
                # 単一のデータの場合
                params = {
                    'code': code,
                    'date': indicator_data.get('date'),
                    'ichimoku_tenkan': safe_round(indicator_data.get('ichimoku_tenkan', 0)),
                    'ichimoku_kijun': safe_round(indicator_data.get('ichimoku_kijun', 0)),
                    'ichimoku_senkou_a': safe_round(indicator_data.get('ichimoku_senkou_a', 0)),
                    'ichimoku_senkou_b': safe_round(indicator_data.get('ichimoku_senkou_b', 0)),
                    'adx': safe_round(indicator_data.get('adx', 0)),
                    'bb_lower': safe_round(indicator_data.get('bb_lower', 0)),
                    'bb_middle': safe_round(indicator_data.get('bb_middle', 0)),
                    'bb_upper': safe_round(indicator_data.get('bb_upper', 0)),
                    'stoch_k': safe_round(indicator_data.get('stoch_k', 0)),
                    'stoch_d': safe_round(indicator_data.get('stoch_d', 0)),
                    'atr': safe_round(indicator_data.get('atr', 0)),
                    'rsi': safe_round(indicator_data.get('rsi', 0)),
                    'macd': safe_round(indicator_data.get('macd', 0)),
                    'dynamic_threshold': indicator_data.get('dynamic_threshold', None),
                    'weekly_trend': indicator_data.get('weekly_trend', None),
                    'pca_signal': indicator_data.get('pca_signal', None)
                }
                self.cur.execute(upsert_query, params)
            
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

    def fetch_industry_name_prefix(self, code: str) -> Optional[str]:
        """
        指定された証券コードの業種名のテーブルプレフィックスを取得します
        
        Args:
            code (str): 証券コード
            
        Returns:
            Optional[str]: 業種名のテーブルプレフィックス、取得失敗時はNone
        """
        try:
            query = """
            SELECT industry_name
            FROM companies
            WHERE code = %s;
            """
            self.cur.execute(query, (code,))
            result = self.cur.fetchone()
            if result:
                return TableCategory.get_table_prefix(result[0])
            return None
        except Exception as e:
            self.logger.error(f"業種名取得エラー: {e}")
            return None 