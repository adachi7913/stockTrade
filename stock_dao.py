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
            self.conn.commit()
        except Exception as e:
            print(f"エラー発生: {e}")

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
            stock_price_dataは以下のキーを含む辞書である必要があります:
            - code: 株式コード
            - date: 日付 (YYYY-MM-DD 形式またはDATE型にキャスト可能な文字列)
            - open: 始値
            - high: 高値
            - low: 安値
            - close: 終値
            - volume: 出来高
            """
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
        except Exception as e:
            print(f"エラー発生: {e}")

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


if __name__ == "__main__":
    dao = StockDAO()
    company_info = dao.fetch_company_info("7203")
    print("company_info:", company_info)
    print("indutrty_name:", company_info[3])
