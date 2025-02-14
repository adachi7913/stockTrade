import sys
import os

# プロジェクトのルートディレクトリをsys.pathに追加する
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import time
import psycopg
from dotenv import load_dotenv
from datetime import date, timedelta, datetime
import threading
import math




# DDLの実行を排他制御するためのグローバルロック
DDL_LOCK = threading.Lock()

class StockDAO:
    def __init__(self):
        load_dotenv()
        host = os.environ.get("DB_HOST")
        database = os.environ.get("DB_NAME")
        user = os.environ.get("DB_USER")
        password = os.environ.get("DB_PASSWORD")

        try:
            self.conn = psycopg.connect(
                host=host, dbname=database, user=user, password=password
            )
            cur = self.conn.cursor()
            self.cur = cur
        except Exception as e:
            print(f"エラー発生: {e}")

    def insert_company_data(self, company_data):
        try:
            # companiesテーブルにデータを挿入
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
        except Exception as e:
            print(f"エラー発生: {e}")

    def fetch_company_code_list(self):
        """全上場企業のコードを取得"""

        try:
            # companiesテーブルから全てのコードを取得
            select_query = """
            SELECT code FROM companies
            WHERE market_name NOT IN ('その他')
            ORDER BY code;
            """
            self.cur.execute(select_query)
            codes = self.cur.fetchall()
            # print(codes)
            return [code[0] for code in codes]

        except Exception as e:
            print(f"エラー発生: {e}")
            return None

    def insert_stock_price_data(self, stock_price_data, industry_name):
        table_name = f"{industry_name}_price"
        try:
            """
            株価データの挿入または更新
            stock_price_data は以下のキーを含む辞書である必要があります:
              - code: 株式コード
              - date: 日付 (YYYY-MM-DD 形式または DATE 型にキャスト可能な文字列)
              - open: 始値
              - high: 高値
              - low: 安値
              - close: 終値
              - volume: 出来高
              
            ※numeric(10,2) のカラム設定のため、絶対値が 1e8 (100,000,000) 以上の場合は、
               異常な値とみなしインサートをスキップします。
            """
            # 異常値チェック: 株価（open, high, low, close）の各値が閾値以上なら挿入しない
            threshold = 100_000_000  # 10^8
            for key in ["open", "high", "low", "close"]:
                if abs(stock_price_data.get(key, 0)) >= threshold:
                    print(f"異常な株価データが検出されたため、インサートをスキップします: {stock_price_data}")
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
            print(f"エラー発生: {e}")
            self.conn.rollback()  # トランザクションをロールバックして状態をリセットする

    def insert_indicator_data(self, indicator_data, stock_code, industry_name):
        table_name = f"{industry_name}_indicator"
        stock_code = stock_code[:-1] if stock_code.endswith("0") else stock_code
        try:
            """
            日付ごとのインジケーターのデータをDBにINSERTする関数

            :param cur: psycopgのカーソルオブジェクト
            :param indicator_data: インジケーター計算結果の辞書。
            例:
            {
                '20250205': {
                    'ichimoku': {'tenkan': 4190.0, 'kijun': 4170.0, 'senkou_a': 4021.25, 'senkou_b': 4115.0},
                    'adx': 20.927303503014947,
                    'bb': {'lower': 3802.553885568217, 'middle': 4034.5, 'upper': 4266.446114431783},
                    'stoch': {'stoch_k': 70.69781371668164, 'stoch_d': 82.12339023659776},
                    'atr': 80.49761579915365
                },
                '20250206': {
                    'ichimoku': {'tenkan': 4210.0, 'kijun': 4170.0, 'senkou_a': 4013.75, 'senkou_b': 4115.0},
                    'adx': 23.469471470247406,
                    'bb': {'lower': 3784.9085522752057, 'middle': 4051.5, 'upper': 4318.091447724794},
                    'stoch': {'stoch_k': 70.52040942163028, 'stoch_d': 74.30744205438988},
                    'atr': 85.81921474528401
                }
            }
            :param stock_code: 対象の銘柄コード
            :param table_name: 挿入先のインジケーター・テーブル名（例: "retail_indicator"）
            """
            # 安全に丸めるヘルパー関数を定義
            def safe_round(value, ndigits):
                try:
                    r = round(value, ndigits)
                    return r if (isinstance(r, float) and __import__('math').isfinite(r)) else (r if not isinstance(r, float) else 0)
                except Exception:
                    return 0
            
            query = f"""
            INSERT INTO {table_name} (
                code, date,
                ichimoku_tenkan, ichimoku_kijun, ichimoku_senkou_a, ichimoku_senkou_b,
                adx, bb_lower, bb_middle, bb_upper, stoch_k, stoch_d, atr, rsi, macd,
                dynamic_threshold, weekly_trend, pca_signal
            ) VALUES (
                %(code)s, %(date)s,
                %(tenkan)s, %(kijun)s, %(senkou_a)s, %(senkou_b)s,
                %(adx)s, %(bb_lower)s, %(bb_middle)s, %(bb_upper)s, %(stoch_k)s, %(stoch_d)s, %(atr)s, %(rsi)s, %(macd)s,
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
            
            for record in indicator_data:
                date_str = record.get("date", "")
                if len(date_str) == 8:
                    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                else:
                    formatted_date = date_str

                params = {
                    "code": stock_code,
                    "date": formatted_date,
                    "tenkan": safe_round(record.get("ichimoku_tenkan", 0), 2),
                    "kijun": safe_round(record.get("ichimoku_kijun", 0), 2),
                    "senkou_a": safe_round(record.get("ichimoku_senkou_a", 0), 2),
                    "senkou_b": safe_round(record.get("ichimoku_senkou_b", 0), 2),
                    "adx": safe_round(record.get("adx", 0), 2),
                    "bb_lower": safe_round(record.get("bb_lower", 0), 2),
                    "bb_middle": safe_round(record.get("bb_middle", 0), 2),
                    "bb_upper": safe_round(record.get("bb_upper", 0), 2),
                    "stoch_k": safe_round(record.get("stoch_k", 0), 2),
                    "stoch_d": safe_round(record.get("stoch_d", 0), 2),
                    "atr": safe_round(record.get("atr", 0), 2),
                    "rsi": safe_round(record.get("rsi", 0), 2),
                    "macd": safe_round(record.get("macd", 0), 2),
                    "dynamic_threshold": record.get("dynamic_threshold", 0),
                    "weekly_trend": record.get("weekly_trend", "UNKNOWN"),
                    "pca_signal": safe_round(record.get("pca_signal", 0), 2)
                }

                self.cur.execute(query, params)
            self.conn.commit()
        except Exception as e:
            print(f"エラー発生: {e}")    
    

    def get_stock_full_data_period(self,stock_code, industry_name):
        stock_code = stock_code[:-1] if stock_code.endswith("0") else stock_code
        """
        株価コードと業種名を引数に、DBから現在から1年前までのデータを配列で取得し、
        以下の構成でレスポンスする:

        {
            'code': '1301',
            'date': 'yyyymmdd',
            'open': xxxx,
            'high': xxxx,
            'low': xxxx,
            'close': xxxx,
            'volume': xxxx,
            'ichimoku': {
                'tenkan': xxxx,
                'kijun': xxxx,
                'senkou_a': xxxx,
                'senkou_b': xxxx
            },
            'adx': xxxx,
            'bb': {
                'lower': xxxx,
                'middle': xxxx,
                'upper': xxxx
            },
            'stoch': {
                'stoch_k': xxxx,
                'stoch_d': xxxx
            },
            'atr': xxxx
        }

        ※期間は「現在の日付」から「1年前」まで（日付型で直接比較）とします。
        """
        # レスポンス用の配列に、各行を必要な構成の辞書に変換
        try:
            results = []    
            # テーブル名の動的生成
            price_table = f"{industry_name}_price"
            indicator_table = f"{industry_name}_indicator"
                
            # 期間設定：本日から1年前まで
            today = date.today()
            one_year_ago = today - timedelta(days=(int(os.getenv("FETCH_DATA_RANGE"))-1)*365) # 2年分
                
            # SQL：価格テーブルと指標テーブルをcode, dateで結合
            query = f"""
                SELECT
                    p.code,
                    to_char(p.date, 'YYYYMMDD') AS date,
                    p.open, p.high, p.low, p.close, p.volume,
                    i.ichimoku_tenkan, i.ichimoku_kijun, i.ichimoku_senkou_a, i.ichimoku_senkou_b,
                    i.adx,
                    i.bb_lower, i.bb_middle, i.bb_upper,
                    i.stoch_k, i.stoch_d,
                    i.atr,
                    i.rsi,
                    i.macd,
                    i.dynamic_threshold,
                    i.weekly_trend,
                    i.pca_signal
                FROM {price_table} p
                INNER JOIN {indicator_table} i ON p.code = i.code AND p.date = i.date
                WHERE p.code = %(code)s
                AND p.date BETWEEN %(start_date)s AND %(end_date)s
                ORDER BY p.date ASC;
            """
                
            self.cur.execute(query, {
                "code": stock_code,
                "start_date": one_year_ago,
                "end_date": today
            })
            rows = self.cur.fetchall()
                
            if not rows:
                print("該当するデータが見つかりません。")
                return []
                
            
            for row in rows:
                # rowの順番:
                # 0: code, 1: date, 2: open, 3: high, 4: low, 5: close, 6: volume,
                # 7: ichimoku_tenkan, 8: ichimoku_kijun, 9: ichimoku_senkou_a, 10: ichimoku_senkou_b,
                # 11: adx, 12: bb_lower, 13: bb_middle, 14: bb_upper,
                # 15: stoch_k, 16: stoch_d, 17: atr, 18: rsi, 19: macd
                # 20: dynamic_threshold, 21: weekly_trend, 22: pca_signal
                record = {
                    "code": row[0],
                    "date": row[1],
                    "open": row[2],
                    "high": row[3],
                    "low": row[4],
                    "close": row[5],
                    "volume": row[6],
                    "ichimoku": {
                        "tenkan": row[7],
                        "kijun": row[8],
                        "senkou_a": row[9],
                        "senkou_b": row[10]
                    },
                    "adx": row[11],
                    "bb": {
                        "lower": row[12],
                        "middle": row[13],
                        "upper": row[14]
                    },
                    "stoch": {
                        "stoch_k": row[15],
                        "stoch_d": row[16]
                    },
                    "atr": row[17],
                    "rsi": row[18],
                    "macd": row[19],
                    "dynamic_threshold": row[20],
                    "weekly_trend": row[21],
                    "pca_signal": row[22]
                }
                results.append(record)
                
            return results
            
        except Exception as e:
            print(f"DB取得エラー: {e}")
            return []

    

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
        try:
            # companiesテーブルから企業情報を取得
            select_query = """
            SELECT * FROM companies WHERE code = %(code)s
            """
            self.cur.execute(select_query, {"code": code})
            return self.cur.fetchall()[0]  # 1件のみ取得
        except Exception as e:
            print(f"エラー発生: {e}")
            return None

    def insert_api_response(self, response_data):
        """
        APIレスポンスのデータを挿入または更新するメソッド
        
        response_data は以下のキーを含む辞書である必要があります:
          - date: 日付 (例: "2023-10-12") ※ YYYY-MM-DD 形式
          - code: 証券コード (例: "7203")
          - close: 前日の終値 (例: 1500.25)
          - entry_score: エントリー判断スコア (例: 850)
          - reason: エントリー判断の理由 (例: "各指標が好調で、リスクリワード比も2.5と良好...")
          - rule_entry_price: エントリー価格帯 (例: "1360-1370")
          - rule_stop_limit: SL価格 (例: "1330")
          - rule_top_price: 利確目標 (例: "1390-1395")
          - rule_period: 推奨保有期間 (例: "数日～1週間")
          - riskReward: リスクリワード (例: "2.5")
          - no_entry_span: 再評価までの期間（日数、例: 7）
        """
        query = """
        INSERT INTO api_response (
            date, code, close, entry_score, reason, 
            rule_entry_price, rule_stop_limit, rule_top_price, rule_period, risk_reward, no_entry_span, update_when
        ) VALUES (
            %(date)s, %(code)s, %(close)s, %(entry_score)s, %(reason)s, 
            %(rule_entry_price)s, %(rule_stop_limit)s, %(rule_top_price)s, %(rule_period)s, %(riskReward)s, %(no_entry_span)s, %(update_when)s
        )
        ON CONFLICT (code) DO UPDATE SET
            date = EXCLUDED.date,
            close = EXCLUDED.close,
            entry_score = EXCLUDED.entry_score,
            reason = EXCLUDED.reason,
            rule_entry_price = EXCLUDED.rule_entry_price,
            rule_stop_limit = EXCLUDED.rule_stop_limit,
            rule_top_price = EXCLUDED.rule_top_price,
            rule_period = EXCLUDED.rule_period,
            risk_reward = EXCLUDED.risk_reward,
            no_entry_span = EXCLUDED.no_entry_span,
            update_when = EXCLUDED.update_when;
        """
        
        from datetime import datetime
        response_data["update_when"] = datetime.now()
        try:
            self.cur.execute(query, response_data)
            self.conn.commit()
        except Exception as e:
            print("APIレスポンスのデータ挿入エラー:", e)
    
    def fetch_ok_api_responses(self):
        """
        api_response テーブルからエントリースコアが高いレコードのみを取得するメソッド
        戻り値は取得したレコードのリスト（タプルのリスト）です。
        """
        query = """
        SELECT *
        FROM api_response
        WHERE entry_score >= 700;  -- エントリースコアが700以上のものを「有望」とみなす
        """
        try:
            self.cur.execute(query)
            records = self.cur.fetchall()
            return records
        except Exception as e:
            print("api_responseテーブルから有望なレコード取得エラー:", e)
            return []
        
    def update_market_cap(self, code, market_cap):
        try:
            # companies テーブルに market_cap カラムが存在する前提で処理を実行します。
            # 4桁の場合は末尾に "0" を追加
            companies_code = code + "0" if len(code) == 4 else code

            # 既存のレコードがある場合は、時価総額だけを更新する
            self.cur.execute(
                "UPDATE companies SET market_cap = %s WHERE code = %s",
                (market_cap, companies_code)
            )
            self.conn.commit()
        except Exception as e:
            print(f"市場CAP更新エラー: {e}")

    def fetch_market_cap(self, code):
        try:
            # 4桁の場合は末尾に "0" を追加
            companies_code = code + "0" if len(code) == 4 else code
            query = "SELECT market_cap FROM companies WHERE code = %s"
            self.cur.execute(query, (companies_code,))
            result = self.cur.fetchone()
            if result:
                return result[0]
            return None
        except Exception as e:
            print(f"market_cap取得エラー({code}): {e}")
            return None

    def fetch_no_entry_info(self, stock_code):
        """
        api_response テーブルから最新のエントリー不可情報のno_entry_spanを取得します。
        返り値は整数値のno_entry_spanまたはNoneです。
        """
        try:
            # 4桁の場合は末尾に "0" を追加（他のメソッドと同様の処理）
            api_code = stock_code[:-1] if stock_code.endswith("0") else stock_code
            
            query = """
                SELECT no_entry_span
                FROM api_response
                WHERE code = %s
                  AND no_entry_span IS NOT NULL
                  AND entry_score < 700  -- isEntryを entry_score < 700 に変更
                ORDER BY date DESC, update_when DESC
                LIMIT 1;
            """
            self.cur.execute(query, (api_code,))
            result = self.cur.fetchone()
            
            if result is not None:
                return result[0]  # 整数値のno_entry_spanを返す
            return None
            
        except Exception as e:
            print(f"no_entry情報取得エラー({stock_code}): {e}")
            return None

if __name__ == "__main__":
    dao = StockDAO()
    info = dao.fetch_company_info("39630")
    print("info: ", info)

    from lib.table_category import TableCategory
    name = TableCategory.get_table_prefix(info[3])
    print("name: ", name)
    print(dao.get_stock_full_data_period("3963", name))
    print(dao.fetch_no_entry_info("3978"))