import sys
import os
import threading
from datetime import date, datetime
from typing import List, Dict, Optional, Any
import json
from models.evaluation_result import EvaluationResult

from lib.table_category import TableCategory
from .base_repository import BaseRepository
import numpy as np
import logging

# DDLの実行を排他制御するためのグローバルロック
DDL_LOCK = threading.Lock()

class StockRepository(BaseRepository):
    def __init__(self):
        """
        株価データリポジトリクラスの初期化
        """
        super().__init__()
        # 業種名キャッシュの初期化
        self.industry_name_cache = {}
        
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
            AND code NOT LIKE '%A%'
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
            fetch_range = int(os.getenv("FETCH_DATA_RANGE", "1"))*230  # 範囲は年数。デフォルトは1年*230営業日
            
            query = """
            WITH price_data AS (
                SELECT p.*, 
                       i.macd, i.stoch_k, i.stoch_d, i.rsi, 
                       i.bb_lower, i.bb_middle, i.bb_upper, i.atr,
                       i.adx, i.ichimoku_tenkan, i.ichimoku_kijun, 
                       i.ichimoku_senkou_a, i.ichimoku_senkou_b,
                       i.dynamic_threshold, i.weekly_trend, i.pca_signal
                FROM {}_price p
                LEFT JOIN {}_indicator i ON p.code = i.code AND p.date = i.date
                WHERE p.code = %s
                AND p.date BETWEEN (CURRENT_DATE - (%s || ' days')::interval) AND CURRENT_DATE
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
                    'atr': row[14],
                    'adx': row[15],
                    'ichimoku_tenkan': row[16],
                    'ichimoku_kijun': row[17],
                    'ichimoku_senkou_a': row[18],
                    'ichimoku_senkou_b': row[19],
                    'dynamic_threshold': row[20],
                    'weekly_trend': row[21],
                    'pca_signal': row[22]
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
            fetch_range = int(os.getenv("FETCH_DATA_RANGE", "1"))*230  # 範囲は年数。デフォルトは1年*230営業日
            
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

    def get_latest_api_response(self, code: str) -> Optional[Dict[str, Any]]:
        """
        指定された銘柄コードに対して、api_responseテーブルから最新のAPI応答を取得して返します。
        取得したデータは、AIプロンプト生成時に使用する形式に変換します。

        Args:
            code (str): 銘柄コード（4桁）

        Returns:
            Optional[Dict[str, Any]]: 最新のAPI応答データを含む辞書、取得失敗時は None
        """
        try:
            query = """
            SELECT 
                date, code, close, rule_entry_price, rule_stop_limit, 
                rule_top_price, rule_period, risk_reward, no_entry_span, 
                entry_score, expected_return, reason, 
                entry_conditions, exit_conditions, 
                market_analysis, technical_patterns, indicator_analysis
            FROM api_response
            WHERE code = %s
            ORDER BY date DESC, update_when DESC
            LIMIT 1;
            """
            
            self.cur.execute(query, (code,))
            row = self.cur.fetchone()
            
            if not row:
                return None
                
            # JSONフィールドを処理
            market_analysis = row[14]
            if market_analysis and isinstance(market_analysis, str):
                try:
                    market_analysis = json.loads(market_analysis)
                except (json.JSONDecodeError, TypeError):
                    self.logger.warning(f"market_analysis JSONパース失敗: {market_analysis}")
                    market_analysis = {}
            else:
                market_analysis = {}
                
            # 結果を返却用の辞書形式に変換
            return {
                'date': row[0].strftime('%Y-%m-%d') if row[0] else None,
                'code': row[1],
                'close': float(row[2]) if row[2] else None,
                'rule': {
                    'entryPrice': row[3],
                    'stop_loss': row[4],
                    'target_price': row[5],
                    'period': row[6],
                    'risk_reward': row[7]
                },
                'no_entry_span': row[8],
                'entry_score': row[9],
                'expected_return': float(row[10]) if row[10] else None,
                'reason': row[11],
                'entry_conditions': row[12],
                'exit_conditions': row[13],
                'market_analysis': market_analysis,
                'technical_patterns': row[15],
                'indicator_analysis': row[16]
            }
            
        except Exception as e:
            self.logger.error(f"最新API応答データ取得エラー: {e}")
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
                    # 日付フォーマットの検証
                    if 'date' not in data or not isinstance(data['date'], str):
                        self.logger.warning(f"日付データが不正です: {data.get('date', 'None')}")
                        continue
                        
                    # 日付フォーマットがYYYY-MM-DDであることを確認
                    date_str = data['date']
                    if not (len(date_str.split('-')) == 3 and len(date_str) == 10):
                        self.logger.warning(f"日付フォーマットが不正です: {date_str}")
                        continue
                    
                    # インジケーターデータの検証
                    if any(data.get(key) is None for key in required_keys):
                        self.logger.warning(f"インジケーター計算に必要なデータが不足しているため、銘柄 {code} のデータ挿入をスキップします: {data}")
                        continue
                    filtered_data.append(data)
                indicator_data = filtered_data
                if not indicator_data:
                    return False
            else:
                # 単一のデータの場合の日付検証
                if 'date' not in indicator_data or not isinstance(indicator_data['date'], str):
                    self.logger.warning(f"単一データの日付が不正です: {indicator_data.get('date', 'None')}")
                    return False
                    
                # 日付フォーマットがYYYY-MM-DDであることを確認
                date_str = indicator_data['date']
                if not (len(date_str.split('-')) == 3 and len(date_str) == 10):
                    self.logger.warning(f"単一データの日付フォーマットが不正です: {date_str}")
                    return False
                
                if any(indicator_data.get(key) is None for key in required_keys):
                    self.logger.warning(f"インジケーター計算に必要なデータが不足しているため、銘柄 {code} のデータ挿入をスキップします: {indicator_data}")
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
                    # 全ての値のログを書き出し（デバッグ用）
                    self.logger.debug(f"挿入データ: date={data.get('date')}, code={code}")
                    
                    params = {
                        'code': code,
                        'date': data.get('date'),  # 検証済みの日付文字列
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
                    'date': indicator_data.get('date'),  # 検証済みの日付文字列
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

    def bulk_insert_indicator_data(self, indicators_batch: List[Dict], industry_name: str) -> bool:
        """
        複数の指標データを一括で挿入します
        
        Args:
            indicators_batch (List[Dict]): 挿入する指標データのリスト。各要素は以下の形式:
                {
                    'code': 証券コード,
                    'indicators': インジケーターデータのリスト
                }
            industry_name (str): 業種名
            
        Returns:
            bool: 挿入成功でTrue
        """
        if not indicators_batch:
            return True
            
        table_name = f"{industry_name}_indicator"
        try:
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
            
            # バッチ処理用のパラメータリストを作成
            params_list = []
            
            for batch_item in indicators_batch:
                code = batch_item['code']
                indicators = batch_item['indicators']
                
                if not indicators:
                    continue
                    
                for data in indicators:
                    params = {
                        'code': code,
                        'date': data.get('date'),
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
                    params_list.append(params)
            
            # バルクインサートの実行
            if params_list:
                self.cur.executemany(upsert_query, params_list)
                self.conn.commit()
                self.logger.info(f"{len(params_list)}件のインジケーターデータを一括挿入しました")
                return True
            else:
                self.logger.warning("挿入するデータがありません")
                return False
                
        except Exception as e:
            self.logger.error(f"インジケーターデータ一括挿入エラー: {e}")
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
                rule_top_price, rule_period, risk_reward, no_entry_span, update_when, 
                entry_score, expected_return, reason,
                entry_conditions, exit_conditions, short_term_trend, mid_term_trend,
                long_term_trend, support_resistance, technical_patterns, indicator_analysis
            ) VALUES (
                %(date)s, %(code)s, %(close)s, %(rule_entry_price)s, %(rule_stop_limit)s,
                %(rule_top_price)s, %(rule_period)s, %(risk_reward)s, %(no_entry_span)s, NOW(), 
                %(entry_score)s, %(expected_return)s, %(reason)s,
                %(entry_conditions)s, %(exit_conditions)s, %(short_term_trend)s, %(mid_term_trend)s,
                %(long_term_trend)s, %(support_resistance)s, %(technical_patterns)s, %(indicator_analysis)s
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
                reason = EXCLUDED.reason,
                entry_conditions = EXCLUDED.entry_conditions,
                exit_conditions = EXCLUDED.exit_conditions,
                short_term_trend = EXCLUDED.short_term_trend,
                mid_term_trend = EXCLUDED.mid_term_trend,
                long_term_trend = EXCLUDED.long_term_trend,
                support_resistance = EXCLUDED.support_resistance,
                technical_patterns = EXCLUDED.technical_patterns,
                indicator_analysis = EXCLUDED.indicator_analysis;
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
        キャッシュを利用して重複DB接続を削減します
        """
        # キャッシュにあればそれを返す
        if code in self.industry_name_cache:
            return self.industry_name_cache[code]
            
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
                    
                    # キャッシュに保存
                    self.industry_name_cache[code] = table_prefix
                    
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
            
    def preload_industry_names(self, codes: List[str]) -> None:
        """
        複数の証券コードの業種名を一括で事前ロードしてキャッシュに保存します
        
        Args:
            codes (List[str]): 証券コードのリスト
        """
        if not codes:
            return
            
        try:
            # コードのリストをカンマ区切りの文字列に変換
            code_list = "','".join(codes)
            
            query = f"""
            SELECT code, industry_name
            FROM companies
            WHERE code IN ('{code_list}')
            ORDER BY date DESC;
            """
            
            self.cur.execute(query)
            results = self.cur.fetchall()
            
            # 結果をキャッシュに保存
            for code, industry_name in results:
                try:
                    industry_name = industry_name.strip()
                    table_prefix = TableCategory.get_table_prefix(industry_name)
                    self.industry_name_cache[code] = table_prefix
                except ValueError as e:
                    self.logger.error(f"業種名の変換に失敗: {str(e)}")
                    continue
                    
            self.logger.info(f"{len(self.industry_name_cache)}件の業種名をキャッシュにロードしました")
            
        except Exception as e:
            self.logger.error(f"業種名の一括ロードエラー: {e}")

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

    def fetch_latest_indicators(self, code: str, industry_name: str, limit: int = 1) -> List[Dict]:
        """
        指定された銘柄の最新のインジケーターデータを取得
        
        Args:
            code (str): 銘柄コード（4桁）
            industry_name (str): 業種名のテーブルプレフィックス
            limit (int): 取得する件数（デフォルト: 1）
            
        Returns:
            List[Dict]: インジケーターデータのリスト
        """
        try:
            query = f"""
            SELECT date, ichimoku_tenkan, ichimoku_kijun, ichimoku_senkou_a,
                   ichimoku_senkou_b, adx, bb_lower, bb_middle, bb_upper,
                   stoch_k, stoch_d, atr, rsi, macd, dynamic_threshold, 
                   weekly_trend, pca_signal
            FROM {industry_name}_indicator
            WHERE code = %s
            ORDER BY date DESC
            LIMIT %s;
            """
            
            # SQLクエリの内容を確認
            formatted_query = self.cur.mogrify(query, (code, limit)).decode('utf-8')
            self.logger.debug(f"実行SQL: {formatted_query}")
            
            self.cur.execute(query, (code, limit))
            rows = self.cur.fetchall()
            
            self.logger.debug(f"取得した行数: {len(rows)}")
            
            return [
                {
                    'date': row[0].strftime('%Y%m%d') if row[0] else None,
                    'ichimoku_tenkan': float(row[1]) if row[1] is not None else None,
                    'ichimoku_kijun': float(row[2]) if row[2] is not None else None,
                    'ichimoku_senkou_a': float(row[3]) if row[3] is not None else None,
                    'ichimoku_senkou_b': float(row[4]) if row[4] is not None else None,
                    'adx': float(row[5]) if row[5] is not None else None,
                    'bb_lower': float(row[6]) if row[6] is not None else None,
                    'bb_middle': float(row[7]) if row[7] is not None else None,
                    'bb_upper': float(row[8]) if row[8] is not None else None,
                    'stoch_k': float(row[9]) if row[9] is not None else None,
                    'stoch_d': float(row[10]) if row[10] is not None else None,
                    'atr': float(row[11]) if row[11] is not None else None,
                    'rsi': float(row[12]) if row[12] is not None else None,
                    'macd': float(row[13]) if row[13] is not None else None,
                    'dynamic_threshold': float(row[14]) if row[14] is not None else None,
                    'weekly_trend': row[15],
                    'pca_signal': float(row[16]) if row[16] is not None else None
                }
                for row in rows
            ]
            
        except Exception as e:
            self.logger.error(f"最新インジケーター取得エラー（コード: {code}）: {str(e)}")
            return []


    def get_sector_stock_prices(self, sector_table: str, days: int = 90) -> Dict[str, List[Dict]]:
        try:
            query = f"""
            SELECT p.code, p.date, p.open, p.high, p.low, p.close, p.volume
            FROM {sector_table}_price p
            WHERE p.date > CURRENT_DATE - INTERVAL '{days} days'
            ORDER BY p.code, p.date
            """
            self.cur.execute(query)
            rows = self.cur.fetchall()
            result = {}
            
            for row in rows:
                code, date, open_price, high, low, close, volume = row
                if code not in result:
                    result[code] = []
                result[code].append({
                    'date': date,
                    'open': open_price,
                    'high': high,
                    'low': low,
                    'close': close,
                    'volume': volume
                })
            
            return result
            
        except Exception as e:
            self.logger.error(f"セクター株価データ取得エラー: {e}")
            return {}

    def get_latest_price(self, code: str, industry_name: str) -> Optional[Dict]:
        """
        指定された銘柄の最新の株価情報を取得します
        
        Args:
            code (str): 銘柄コード
            industry_name (str): 業種名（英語のテーブル接頭辞）
            
        Returns:
            Optional[Dict]: 最新の株価情報、データがない場合はNone
        """
        try:
            # 業種名は既に英語のテーブル接頭辞として扱う
            table_prefix = industry_name
            query = f"""
            SELECT * FROM {table_prefix}_price 
            WHERE code = %s 
            ORDER BY date DESC 
            LIMIT 1;
            """
            self.cur.execute(query, (code,))
            result = self.cur.fetchone()
            
            if result:
                return {
                    'date': result[1],
                    'open': float(result[2]),
                    'high': float(result[3]),
                    'low': float(result[4]),
                    'close': float(result[5]),
                    'volume': int(result[6])
                }
            return None
        except Exception as e:
            logging.error(f"最新の株価情報取得エラー: {e}")
            return None

    def get_average_volume(self, code: str, industry_name: str, days: int = 20) -> float:
        """
        指定した銘柄の過去n日間の平均出来高を計算します
        
        Args:
            code (str): 銘柄コード (4桁)
            industry_name (str): 業種名（英語のテーブル接頭辞）
            days (int): 計算対象日数 (デフォルト: 20日)
            
        Returns:
            float: 平均出来高。データがない場合は0を返します。
        """
        try:
            # 業種名は既に英語のテーブル接頭辞として扱う
            table_prefix = industry_name
            query = f"""
            SELECT volume FROM {table_prefix}_price 
            WHERE code = %s 
            ORDER BY date DESC 
            LIMIT %s;
            """
            self.cur.execute(query, (code, days))
            results = self.cur.fetchall()
            
            if not results:
                return 0
                
            volumes = [int(row[0]) for row in results]
            avg_volume = sum(volumes) / len(volumes)
            return avg_volume
            
        except Exception as e:
            logging.error(f"平均出来高計算エラー: code={code}, industry_name={industry_name}, error={e}")
            return 0
            
    def check_price_limit_days(self, code: str, industry_name: str) -> int:
        """
        指定した銘柄のストップ高・ストップ安が連続している日数を確認します
        
        Args:
            code (str): 銘柄コード (4桁)
            industry_name (str): 業種名（英語のテーブル接頭辞）
            
        Returns:
            int: ストップ高・ストップ安が連続している日数。連続していない場合は0を返します。
        """
        try:
            # 業種名は既に英語のテーブル接頭辞として扱う
            table_prefix = industry_name
            
            # 最新の5営業日分の株価データを取得
            query = f"""
            SELECT date, open, high, low, close 
            FROM {table_prefix}_price 
            WHERE code = %s 
            ORDER BY date DESC 
            LIMIT 5;
            """
            self.cur.execute(query, (code,))
            results = self.cur.fetchall()
            
            if not results or len(results) < 2:
                return 0
                
            # ストップ高・ストップ安の判定基準
            # 前日比±30%以上の変動があった場合をストップ高・ストップ安とみなす
            consecutive_days = 0
            
            for i in range(len(results) - 1):
                current_day = results[i]
                prev_day = results[i + 1]
                
                current_close = float(current_day[4])  # close
                prev_close = float(prev_day[4])    # close
                
                # 前日比の変化率を計算
                change_rate = abs(current_close - prev_close) / prev_close
                
                # 30%以上の変動があるかチェック
                if change_rate >= 0.3:
                    consecutive_days += 1
                else:
                    # 連続していない場合はここで終了
                    break
                    
            return consecutive_days
                
        except Exception as e:
            logging.error(f"ストップ高・ストップ安チェックエラー: code={code}, industry_name={industry_name}, error={e}")
            return 0

    def get_stock_price_data(self, code: str, industry_name: str, start_date: str = None, end_date: str = None) -> List[Dict]:
        """
        指定された銘柄の株価データを取得します
        
        Args:
            code (str): 銘柄コード
            industry_name (str): 業種名（英語のテーブル接頭辞）
            start_date (str, optional): 開始日（YYYY-MM-DD形式）
            end_date (str, optional): 終了日（YYYY-MM-DD形式）
            
        Returns:
            List[Dict]: 株価データのリスト
        """
        try:
            # 業種名は既に英語のテーブル接頭辞として扱う
            table_prefix = industry_name
            self.logger.debug(f"株価データ取得: コード={code}, テーブル接頭辞={table_prefix}")
                
            # クエリの基本部分
            query = f"""
            SELECT date, open, high, low, close, volume
            FROM {table_prefix}_price
            WHERE code = %s
            """
            
            params = [code]
            
            # 日付条件の追加
            if start_date:
                query += " AND date >= %s"
                params.append(start_date)
                
            if end_date:
                query += " AND date <= %s"
                params.append(end_date)
                
            # 日付順にソート
            query += " ORDER BY date ASC"
            
            self.logger.debug(f"実行SQL: {self.cur.mogrify(query, params).decode('utf-8')}")
            self.cur.execute(query, params)
            results = self.cur.fetchall()
            
            self.logger.debug(f"取得行数: {len(results)}")
            
            # 結果を辞書のリストに変換
            price_data = []
            for row in results:
                price_data.append({
                    'date': row[0],
                    'open': float(row[1]),
                    'high': float(row[2]),
                    'low': float(row[3]),
                    'close': float(row[4]),
                    'volume': int(row[5])
                })
                
            return price_data
            
        except Exception as e:
            self.logger.error(f"株価データの取得中にエラーが発生しました: {e}", exc_info=True)
            return []
            
    def get_stock_indicator_data(self, code: str, industry_name: str, start_date: str = None, end_date: str = None) -> List[Dict]:
        """
        指定された銘柄のインジケーターデータを取得します
        
        Args:
            code (str): 銘柄コード
            industry_name (str): 業種名（英語のテーブル接頭辞）
            start_date (str, optional): 開始日（YYYY-MM-DD形式）
            end_date (str, optional): 終了日（YYYY-MM-DD形式）
            
        Returns:
            List[Dict]: インジケーターデータのリスト
        """
        try:
            # 業種名は既に英語のテーブル接頭辞として扱う
            table_prefix = industry_name
            self.logger.debug(f"インジケーターデータ取得: コード={code}, テーブル接頭辞={table_prefix}")
            
            # クエリの基本部分
            query = f"""
            SELECT date, ichimoku_tenkan, ichimoku_kijun, ichimoku_senkou_a, ichimoku_senkou_b, 
                   adx, bb_lower, bb_middle, bb_upper, stoch_k, stoch_d, atr, rsi, macd, 
                   dynamic_threshold, weekly_trend, pca_signal
            FROM {table_prefix}_indicator
            WHERE code = %s
            """
            
            params = [code]
            
            # 日付条件の追加
            if start_date:
                query += " AND date >= %s"
                params.append(start_date)
                
            if end_date:
                query += " AND date <= %s"
                params.append(end_date)
                
            # 日付順にソート
            query += " ORDER BY date ASC"
            
            self.logger.debug(f"実行SQL: {self.cur.mogrify(query, params).decode('utf-8')}")
            self.cur.execute(query, params)
            results = self.cur.fetchall()
            
            self.logger.debug(f"取得行数: {len(results)}")
            
            # 結果を辞書のリストに変換
            indicator_data = []
            for row in results:
                data = {
                    'date': row[0],
                    'ichimoku_tenkan': float(row[1]) if row[1] is not None else None,
                    'ichimoku_kijun': float(row[2]) if row[2] is not None else None,
                    'ichimoku_senkou_a': float(row[3]) if row[3] is not None else None,
                    'ichimoku_senkou_b': float(row[4]) if row[4] is not None else None,
                    'adx': float(row[5]) if row[5] is not None else None,
                    'bb_lower': float(row[6]) if row[6] is not None else None,
                    'bb_middle': float(row[7]) if row[7] is not None else None,
                    'bb_upper': float(row[8]) if row[8] is not None else None,
                    'stoch_k': float(row[9]) if row[9] is not None else None,
                    'stoch_d': float(row[10]) if row[10] is not None else None,
                    'atr': float(row[11]) if row[11] is not None else None,
                    'rsi': float(row[12]) if row[12] is not None else None,
                    'macd': float(row[13]) if row[13] is not None else None,
                    'dynamic_threshold': float(row[14]) if row[14] is not None else None,
                    'weekly_trend': row[15],
                    'pca_signal': float(row[16]) if row[16] is not None else None
                }
                indicator_data.append(data)
                
            return indicator_data
            
        except Exception as e:
            self.logger.error(f"インジケーターデータの取得中にエラーが発生しました: {e}", exc_info=True)
            return []

    def get_active_holdings(self, is_test: bool = False) -> Optional[Dict[str, str]]:
        """
        entriesテーブルからアクティブな保有証券情報を取得
        
        Args:
            is_test (bool): テストモードかどうか
            
        Returns:
            Dict[str, str]: {証券コード: 現在価格} の形式、取得失敗時はNone
        """
        try:
            query = """
                SELECT e.code, sp.close as current_price
                FROM entries e
                JOIN (
                    SELECT code, close, date
                    FROM all_stock_prices
                    WHERE date = (SELECT MAX(date) FROM all_stock_prices)
                ) sp ON e.code = sp.code
                WHERE e.status = 'active' AND e.is_test = %s
            """
            
            with self.get_connection() as conn:
                with conn.cursor() as cur:  # 通常のカーソルを使用
                    cur.execute(query, (is_test,))
                    results = cur.fetchall()
                    
                    if not results:
                        return {}
                        
                    # タプルの添字でアクセス（0:code, 1:current_price）
                    return {row[0]: str(row[1]) for row in results}
                    
        except Exception as e:
            self.logger.error(f"保有証券情報の取得に失敗: {e}")
            return None

    def get_previous_evaluation(self, code: str) -> Optional[Dict[str, Any]]:
        """
        api_responseテーブルから最新の評価結果を取得
        
        Args:
            code (str): 証券コード
            
        Returns:
            Optional[Dict[str, Any]]: 評価結果の辞書、取得失敗時はNone
        """
        try:
            query = """
                SELECT 
                    code, 
                    close, 
                    rule_stop_limit as stop_loss, 
                    rule_top_price as target_price,
                    reason,
                    entry_score as confidence_score
                FROM api_response
                WHERE code = %s
                ORDER BY update_when DESC
                LIMIT 1
            """
            
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (code,))
                    result = cur.fetchone()
                    
                    if not result:
                        return None
                    
                    # タプルの添字でアクセス
                    return {
                        'code': result[0],
                        'close': result[1],
                        'stop_loss': result[2] if result[2] else 'NG',
                        'target_price': result[3] if result[3] else 'NG',
                        'reason': result[4] if result[4] else '',
                        'confidence_score': int(result[5]) if result[5] is not None else 0,
                        'decision': 'HOLD'  # デフォルト値
                    }
                    
        except Exception as e:
            logging.error(f"前回評価結果の取得に失敗: {e}")
            return None

    def save_holding_evaluation(self, result: 'EvaluationResult', is_test: bool = False) -> bool:
        """
        保有判断の評価結果を保存
        
        Args:
            result (EvaluationResult): 評価結果
            is_test (bool): テストモードかどうか
        
        Returns:
            bool: 保存成功時はTrue、失敗時はFalse
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # メインテーブルへの保存（UPSERT）
                    query = """
                        INSERT INTO holding_evaluations (
                            date, code, close, stop_loss, target_price,
                            decision, confidence_score, reason,
                            stop_loss_update_reason, target_update_reason,
                            is_test
                        ) VALUES (
                            CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (code, date, is_test) DO UPDATE SET
                            close = EXCLUDED.close,
                            stop_loss = EXCLUDED.stop_loss,
                            target_price = EXCLUDED.target_price,
                            decision = EXCLUDED.decision,
                            confidence_score = EXCLUDED.confidence_score,
                            reason = EXCLUDED.reason,
                            stop_loss_update_reason = EXCLUDED.stop_loss_update_reason,
                            target_update_reason = EXCLUDED.target_update_reason,
                            update_when = CURRENT_TIMESTAMP
                        RETURNING id;
                    """
                    
                    cur.execute(query, (
                        result.code,
                        result.close,
                        result.stop_loss if result.stop_loss != "NG" else None,
                        result.target_price if result.target_price != "NG" else None,
                        result.decision,
                        result.confidence_score,
                        result.reason,
                        result.stop_loss_update_reason,
                        result.target_update_reason,
                        is_test
                    ))
                    
                    evaluation_id = cur.fetchone()[0]
                    
                    # 履歴テーブルへの保存
                    history_query = """
                        INSERT INTO holding_evaluations_history (
                            evaluation_id, date, code, close, stop_loss, target_price,
                            decision, confidence_score, reason,
                            stop_loss_update_reason, target_update_reason,
                            update_when, is_test
                        )
                        SELECT id, date, code, close, stop_loss, target_price,
                               decision, confidence_score, reason,
                               stop_loss_update_reason, target_update_reason,
                               update_when, is_test
                        FROM holding_evaluations
                        WHERE id = %s;
                    """
                    
                    cur.execute(history_query, (evaluation_id,))
                    conn.commit()
                    return True
                    
        except Exception as e:
            self.logger.error(f"保有判断の保存に失敗: {e}")
            return False 