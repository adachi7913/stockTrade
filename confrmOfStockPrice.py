import json
import os
import re
import sys
import time
import concurrent.futures

from dao.stock_dao import StockDAO
from lib.indicator_calculator import IndicatorCalculator
from Gemini.api_handler import ApiHandler
from lib.accsess_yFinance_for_stockPrice import StockPriceAPI

from lib.table_category import TableCategory


# def analyze_stocks():
#     try:
#         # 株価コード一覧取得
#         stock_codes = StockDAO.fetch_company_code_list()

#         # 各銘柄の分析
#         for code in stock_codes:
#             try:
#                 stock_price_api = StockPriceAPI(code)
#                 # 株価データ取得
#                 price_data = stock_price_api.fetch_data_yfinance()

#                 if price_data:
#                     # インジケーター計算
#                     calculator = IndicatorCalculator(price_data)
#                     indicators = calculator.get_indicators()

#                     # Geminiによる分析
#                     prompt = f"""
#                         銘柄コード: {code}
#                         株価データ: {price_data}
#                         テクニカル指標: {indicators}
                        
#                         上記データから投資判断をお願いします。
#                         """

#                     analysis = ApiHandler.call_gemini_api(prompt)
#                     print(f"銘柄 {code} の分析結果:")
#                     print(analysis)
#                     print("-" * 50)

#             except Exception as e:
#                 print(f"銘柄 {code} の処理中にエラー: {e}")
#                 continue

#     except Exception as e:
#         print(f"実行エラー: {e}")
#         return None


if __name__ == "__main__":

    def process_stock(stock_code):
        try:
            dao = StockDAO()
            start_time = time.time()

            # FETCH_DATA_RANGEが環境変数で設定されているとして、ティッカーのデータ取得
            stock_price_api = StockPriceAPI(
                stock_code, os.environ.get("FETCH_DATA_RANGE")
            )
            price_data = stock_price_api.fetch_data_yfinance()
            if not price_data:
                print(f"株価データの取得に失敗しました: {stock_code}")
                return

            # インジケーター計算
            indi_instance = IndicatorCalculator(price_data)
            indicator = indi_instance.get_indicators()

            company_info = dao.fetch_company_info(stock_code)
            industry_name = TableCategory.get_table_prefix(company_info[3])
            dao.insert_indicator_data(indicator, stock_code, industry_name)

            for price in price_data:
                company_info = dao.fetch_company_info(stock_code)
                result = dao.insert_stock_price_data(price, industry_name)
                if result == False:
                    print(f"株価データ 挿入停止: {stock_code}")
                    break

            elapsed = time.time() - start_time
            print(f"[ログ] 銘柄 {stock_code} の処理時間: {elapsed:.2f} 秒")
        except Exception as e:
            print(f"銘柄 {stock_code} の処理中エラー: {e}")
        finally:
            try:
                dao.close()
            except Exception as e:
                pass

    try:
        # DAO を用いて銘柄コード一覧を取得
        dao = StockDAO()
        stock_codes = dao.fetch_company_code_list()
        stock_codes = stock_codes[297:]  # 例: 0-490はすでに取得済み
        dao.close()

        # 並列数（最大 worker 数）は環境や接続件数に応じて調整してください
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(process_stock, stock_codes)
    except Exception as e:
        print(f"全体処理エラー: {e}")
