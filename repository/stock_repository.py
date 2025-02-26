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
                    'code': str(row[0]) if not isinstance(row[0], str) else row[0],
                    'date': row[1].strftime('%Y%m%d') if isinstance(row[1], (datetime, date)) else row[1],
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

    def get_stock_price_only(self, code: str, industry_name: str) -> List[Dict]:
        """
        指定された証券コードの株価データのみを取得します
        
        Args:
            code (str): 証券コード（4桁）
            industry_name (str): 業種名
            
        Returns:
            List[Dict]: 株価データのリスト
        """
        try:
            # 接続状態を確認し、必要に応じて再接続
            if not self.is_connected():
                self.reconnect()
            
            # 環境変数から取得日数を取得
            fetch_range = os.getenv("FETCH_DATA_RANGE", "1")  # 範囲は年数。デフォルトは1年
            
            query = """
            SELECT code, date, open, high, low, close, volume
            FROM {}_price
            WHERE code = %s
            AND date BETWEEN (CURRENT_DATE - (%s || ' years')::interval) AND CURRENT_DATE
            ORDER BY date ASC;
            """.format(industry_name)
            
            self.cur.execute(query, (code, fetch_range))
            rows = self.cur.fetchall()
            
            if not rows:
                self.logger.error(f"株価データが取得できませんでした: code={code}, industry_name={industry_name}")
                return []
            
            result = []
            for row in rows:
                data = {
                    'code': str(row[0]) if not isinstance(row[0], str) else row[0],
                    'date': row[1].strftime('%Y%m%d') if isinstance(row[1], (datetime, date)) else row[1],
                    'open': float(row[2]),
                    'high': float(row[3]),
                    'low': float(row[4]),
                    'close': float(row[5]),
                    'volume': int(row[6])
                }
                result.append(data)
            
            return result
            
        except Exception as e:
            self.logger.error(f"株価データ取得エラー: {e}")
            # エラー発生時に再接続を試みる
            try:
                self.reconnect()
            except Exception as reconnect_error:
                self.logger.error(f"データベース再接続エラー: {reconnect_error}")
            return []

    def is_connected(self) -> bool:
        """
        データベース接続が有効かどうかを確認します
        
        Returns:
            bool: 接続が有効な場合はTrue
        """
        try:
            # 簡単なクエリを実行してみる
            self.cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    def reconnect(self):
        """データベース接続を再確立します"""
        try:
            if self.conn:
                if not self.conn.closed:
                    self.conn.close()
            if self.cur:
                self.cur.close()
            
            self.conn = self.get_connection()
            self.cur = self.conn.cursor()
            self.logger.info("データベース接続を再確立しました")
        except Exception as e:
            self.logger.error(f"データベース再接続失敗: {e}")
            raise

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
            required_keys = ['ichimoku_tenkan', 'ichimoku_kijun', 'ichimoku_senkou_a', 'ichimoku_senkou_b',
                             'adx', 'bb_lower', 'bb_middle', 'bb_upper', 'stoch_k', 'stoch_d',
                             'atr', 'rsi', 'macd', 'dynamic_threshold', 'weekly_trend', 'pca_signal']
            # 入力がリストの場合は各要素に対してチェックし、必要なデータが揃っているものだけ残す
            if isinstance(indicator_data, list):
                filtered_data = []
                for data in indicator_data:
                    if any(data.get(key) is None for key in required_keys):
                        logging.warning(f"インジケーター計算に必要なデータが不足しているため、銘柄 {code} のデータ挿入をスキップします: {data}")
                        continue
                    filtered_data.append(data)
                indicator_data = filtered_data
                if not indicator_data:
                    return False
            else:
                if any(indicator_data.get(key) is None for key in required_keys):
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
                date, code, close, rule_entry_price, rule_stop_limit,
                rule_top_price, rule_period, risk_reward, no_entry_span, update_when, entry_score, expected_return, reason
            ) VALUES (
                %(date)s, %(code)s, %(close)s, %(rule_entry_price)s, %(rule_stop_limit)s,
                %(rule_top_price)s, %(rule_period)s, %(risk_reward)s, %(no_entry_span)s, NOW(), %(entry_score)s, %(expected_return)s, %(reason)s
            )
            ON CONFLICT (code) DO UPDATE SET
                date = EXCLUDED.date,
                close = EXCLUDED.close,
                rule_entry_price = EXCLUDED.rule_entry_price,
                rule_stop_limit = EXCLUDED.rule_stop_limit,
                rule_top_price = EXCLUDED.rule_top_price,
                rule_period = EXCLUDED.rule_period,
                risk_reward = EXCLUDED.risk_reward,
                no_entry_span = EXCLUDED.no_entry_span,
                update_when = NOW(),
                entry_score = EXCLUDED.entry_score,
                expected_return = EXCLUDED.expected_return,
                reason = EXCLUDED.reason;
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
        """
        try:
            query = """
            SELECT industry_name, code, date
            FROM companies
            WHERE code = %s
            ORDER BY date DESC
            LIMIT 1;
            """
            # SQLクエリの内容を確認
            formatted_query = self.cur.mogrify(query, (code,)).decode('utf-8')
            self.logger.debug(f"実行SQL: {formatted_query}")
            
            self.cur.execute(query, (code,))
            result = self.cur.fetchone()
            
            if result:
                industry_name = result[0]
                db_code = result[1]
                db_date = result[2]
                self.logger.debug(f"DBから取得した結果: industry_name='{industry_name}', code='{db_code}', date='{db_date}'")
                
                # 空白文字を除去
                industry_name = industry_name.strip()
                self.logger.debug(f"空白除去後の業種名: '{industry_name}' (len={len(industry_name)})")
                
                try:
                    # 利用可能なカテゴリーを出力
                    available_categories = [c.japanese for c in TableCategory]
                    self.logger.debug(f"利用可能なカテゴリー: {available_categories}")
                    
                    table_prefix = TableCategory.get_table_prefix(industry_name)
                    self.logger.debug(f"変換後のテーブル接頭辞: {table_prefix}")
                    return table_prefix
                except ValueError as e:
                    self.logger.error(f"業種名の変換に失敗: {str(e)}")
                    return None
            else:
                self.logger.warning(f"コード {code} の業種情報が見つかりません")
                return None
            
        except Exception as e:
            self.logger.error(f"業種名取得エラー（コード: {code}）: {e}")
            return None

    def fetch_stock_prices(self, code: str, industry_name: str, limit: int = 100) -> List[Dict]:
        """
        指定された銘柄の株価データを取得
        
        Args:
            code (str): 銘柄コード（4桁）
            industry_name (str): 業種名のテーブルプレフィックス
            limit (int): 取得する日数
            
        Returns:
            List[Dict]: 株価データのリスト
        """
        try:
            query = f"""
            SELECT date, open, high, low, close, volume
            FROM {industry_name}_price
            WHERE code = %s  -- 4桁コードをそのまま使用
            ORDER BY date DESC
            LIMIT %s;
            """
            
            # SQLクエリの内容を確認
            formatted_query = self.cur.mogrify(query, (code, limit)).decode('utf-8')
            self.logger.debug(f"実行SQL: {formatted_query}")
            
            self.cur.execute(query, (code, limit))  # 4桁コードをそのまま使用
            rows = self.cur.fetchall()
            
            self.logger.debug(f"取得した行数: {len(rows)}")
            
            return [
                {
                    'date': row[0].strftime('%Y%m%d'),
                    'open': float(row[1]),
                    'high': float(row[2]),
                    'low': float(row[3]),
                    'close': float(row[4]),
                    'volume': int(row[5])
                }
                for row in rows
            ]
            
        except Exception as e:
            self.logger.error(f"株価データ取得エラー（コード: {code}）: {str(e)}")
            return []

    def insert_indicators(self, code: str, industry_name: str, indicators: List[Dict]) -> bool:
        """
        計算したインジケーターをDBに保存
        
        Args:
            code (str): 銘柄コード（4桁）
            industry_name (str): 業種名のテーブルプレフィックス
            indicators (List[Dict]): インジケーターのリスト
            
        Returns:
            bool: 保存成功でTrue
        """
        try:
            query = f"""
            INSERT INTO {industry_name}_indicator (
                code, date, ichimoku_tenkan, ichimoku_kijun, ichimoku_senkou_a,
                ichimoku_senkou_b, adx, bb_lower, bb_middle, bb_upper,
                stoch_k, stoch_d, atr, rsi, macd,
                dynamic_threshold, weekly_trend, pca_signal
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
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
            
            for indicator in indicators:
                values = (
                    code,  # 4桁コードをそのまま使用
                    indicator['date'],
                    indicator['ichimoku_tenkan'],
                    indicator['ichimoku_kijun'],
                    indicator['ichimoku_senkou_a'],
                    indicator['ichimoku_senkou_b'],
                    indicator['adx'],
                    indicator['bb_lower'],
                    indicator['bb_middle'],
                    indicator['bb_upper'],
                    indicator['stoch_k'],
                    indicator['stoch_d'],
                    indicator['atr'],
                    indicator['rsi'],
                    indicator['macd'],
                    indicator['dynamic_threshold'],
                    indicator['weekly_trend'],
                    indicator['pca_signal']
                )
                # クエリ内容を確認
                formatted_query = self.cur.mogrify(query, values).decode('utf-8')
                self.logger.debug(f"実行SQL: {formatted_query}")
                
                self.cur.execute(query, values)
            
            self.conn.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"インジケーター保存エラー（コード: {code}）: {str(e)}")
            self.conn.rollback()
            return False 