import time
import psycopg
from dotenv import load_dotenv
from datetime import date, timedelta
import os

from lib.accsess_yFinance_for_stockPrice import StockPriceAPI
from lib.indicator_calculator import IndicatorCalculator
from lib.table_category import TableCategory


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
            query = f"""
            INSERT INTO {table_name} (
                code, date,
                ichimoku_tenkan, ichimoku_kijun, ichimoku_senkou_a, ichimoku_senkou_b,
                adx, bb_lower, bb_middle, bb_upper, stoch_k, stoch_d, atr
            ) VALUES (
                %(code)s, %(date)s,
                %(tenkan)s, %(kijun)s, %(senkou_a)s, %(senkou_b)s,
                %(adx)s, %(bb_lower)s, %(bb_middle)s, %(bb_upper)s, %(stoch_k)s, %(stoch_d)s, %(atr)s
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
                atr = EXCLUDED.atr;
            """
            
            for date_str, data in indicator_data.items():
                # date_strが整数の場合もあるので、文字列に変換する
                date_str = str(date_str)
                # "YYYYMMDD" → "YYYY-MM-DD" 形式へ変換
                formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                
                if not isinstance(data.get('ichimoku'), dict):
                    print(f"Warning: ichimokuがdictではありません: {data.get('ichimoku')}")
                if not isinstance(data.get('bb'), dict):
                    print(f"Warning: bbがdictではありません: {data.get('bb')}")
                if not isinstance(data.get('stoch'), dict):
                    print(f"Warning: stochがdictではありません: {data.get('stoch')}")

                # 値を丸める（DECIMAL(10,2)に合わせるため、小数点以下2桁）
                tenkan    = round(data['ichimoku']['tenkan'], 2)
                kijun     = round(data['ichimoku']['kijun'], 2)
                senkou_a  = round(data['ichimoku']['senkou_a'], 2)
                senkou_b  = round(data['ichimoku']['senkou_b'], 2)
                adx       = round(data['adx'], 2)
                bb_lower  = round(data['bb']['lower'], 2)
                bb_middle = round(data['bb']['middle'], 2)
                bb_upper  = round(data['bb']['upper'], 2)
                stoch_k   = round(data['stoch']['stoch_k'], 2)
                stoch_d   = round(data['stoch']['stoch_d'], 2)
                atr       = round(data['atr'], 2)

                params = {
                    "code": stock_code,
                    "date": formatted_date,
                    "tenkan": tenkan,
                    "kijun": kijun,
                    "senkou_a": senkou_a,
                    "senkou_b": senkou_b,
                    "adx": adx,
                    "bb_lower": bb_lower,
                    "bb_middle": bb_middle,
                    "bb_upper": bb_upper,
                    "stoch_k": stoch_k,
                    "stoch_d": stoch_d,
                    "atr": atr
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
            one_year_ago = today - timedelta(days=365)
                
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
                    i.atr
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
                # 15: stoch_k, 16: stoch_d, 17: atr
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
                    "atr": row[17]
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
          - isEntry: エントリー可否 (例: "可能" または "不可")
          - reason: エントリー判断の理由 (例: "株価がボリンジャーバンド下限に接近しているため")
          - rule_entry_price: エントリー価格帯 (例: "1360-1370")
          - rule_stop_limit: SL価格 (例: "1330")
          - rule_top_price: 利確目標 (例: "1390-1395")
          - rule_period: 推奨保有期間 (例: "数日～1週間")
          - riskReward: リスクリワード (例: "2.0" または "NG")
          - score: スコア (例: 75)
          - no_entry_span: 再評価までの期間（日数、例: 7）
        """
        query = """
        INSERT INTO api_response (
            date, code, close, isEntry, reason, 
            rule_entry_price, rule_stop_limit, rule_top_price, rule_period, risk_reward, score, no_entry_span
        ) VALUES (
            %(date)s, %(code)s, %(close)s, %(isEntry)s, %(reason)s, 
            %(rule_entry_price)s, %(rule_stop_limit)s, %(rule_top_price)s, %(rule_period)s, %(riskReward)s, %(score)s, %(no_entry_span)s
        )
        ON CONFLICT (code) DO UPDATE SET
            date = EXCLUDED.date,
            close = EXCLUDED.close,
            isEntry = EXCLUDED.isEntry,
            reason = EXCLUDED.reason,
            rule_entry_price = EXCLUDED.rule_entry_price,
            rule_stop_limit = EXCLUDED.rule_stop_limit,
            rule_top_price = EXCLUDED.rule_top_price,
            rule_period = EXCLUDED.rule_period,
            risk_reward = EXCLUDED.risk_reward,
            score = EXCLUDED.score,
            no_entry_span = EXCLUDED.no_entry_span;
        """
        
        try:
            self.cur.execute(query, response_data)
            self.conn.commit()
        except Exception as e:
            print("APIレスポンスのデータ挿入エラー:", e)
    
    def fetch_ok_api_responses(self):
        """
        api_response テーブルから isEntry が "OK" のレコードのみを取得するメソッド
        戻り値は取得したレコードのリスト（タプルのリスト）です。
        """
        query = """
        SELECT *
        FROM api_response
        WHERE isEntry = 'OK';
        """
        try:
            self.cur.execute(query)
            records = self.cur.fetchall()
            return records
        except Exception as e:
            print("api_responseテーブルからOKのレコード取得エラー:", e)
            return []
        
    def update_market_cap(self, code, market_cap):
        try:
            # market_capカラムが存在するか確認。存在しなければ追加する
            self.cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'companies' AND column_name = 'market_cap'
            """)
            if self.cur.fetchone() is None:
                self.cur.execute("ALTER TABLE companies ADD COLUMN market_cap NUMERIC;")
                self.conn.commit()

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
