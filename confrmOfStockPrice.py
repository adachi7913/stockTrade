import json
import os
import re
import sys
import time

from dao.stock_dao import StockDAO
from lib.indicator_calculator import IndicatorCalculator
from Gemini.api_handler import ApiHandler
from lib.accsess_yFinance_for_stockPrice import StockPriceAPI
from lib.parse_response import perse_response
from lib.table_category import TableCategory


def analyze_stocks():
    try:
        # 株価コード一覧取得
        stock_codes = StockDAO.fetch_company_code_list()

        # 各銘柄の分析
        for code in stock_codes:
            try:
                stock_price_api = StockPriceAPI(code)
                # 株価データ取得
                price_data = stock_price_api.fetch_data_yfinance()

                if price_data:
                    # インジケーター計算
                    calculator = IndicatorCalculator(price_data)
                    indicators = calculator.get_indicators()

                    # Geminiによる分析
                    prompt = f"""
                        銘柄コード: {code}
                        株価データ: {price_data}
                        テクニカル指標: {indicators}
                        
                        上記データから投資判断をお願いします。
                        """

                    analysis = ApiHandler.call_gemini_api(prompt)
                    print(f"銘柄 {code} の分析結果:")
                    print(analysis)
                    print("-" * 50)

            except Exception as e:
                print(f"銘柄 {code} の処理中にエラー: {e}")
                continue

    except Exception as e:
        print(f"実行エラー: {e}")
        return None


if __name__ == "__main__":
    try:
        dao = StockDAO()
        stock_codes = dao.fetch_company_code_list()
        # stock_codes = stock_codes[68:] # 0-68はすでに取得済み
        # stock_codes = stock_codes[216:] # 0-216はすでに取得済み
        # stock_codes = stock_codes[297:]  # 0-292はすでに取得済み
        stock_codes = stock_codes[297:]  # 0-490はすでに取得済み
        # print("stock_codes:", stock_codes[0])
        # print(stock_codes)
        # stock_code = stock_codes[10]
        dao.close()

        for stock_code in stock_codes:
            # break
            dao = StockDAO()
            # if stock_code == "27540":
            #     continue
            start_time = time.time()  # 処理開始時刻を記録

            # if stock_code != "27530":
            #     continue
            stock_price_api = StockPriceAPI(
                stock_code, os.environ.get("FETCH_DATA_RANGE")
            )
            price_data = stock_price_api.fetch_data_yfinance()
            if not price_data:
                print(f"株価データの取得に失敗しました: {stock_code}")
                continue
            indi_instance = IndicatorCalculator(price_data)
            indicator = indi_instance.get_indicators()

            company_info = dao.fetch_company_info(stock_code)
            industry_name = TableCategory.get_table_prefix(
                company_info[3]
            )  # 企業名の取得
            dao.insert_indicator_data(indicator, stock_code, industry_name)

            for price in price_data:
                company_info = dao.fetch_company_info(stock_code)
                result = dao.insert_stock_price_data(price, industry_name)
                if result == False:
                    print("result:", result)
                    break

            # full_data = dao.get_stock_full_data_period(stock_code, industry_name)
            # handler = ApiHandler(full_data)
            # response = handler.call_gemini_api()
            # print("response:", response)

            # insert_data = perse_response(full_data, response)
            # if insert_data == None:
            #     continue
            # print("insert_data:", insert_data)
            # dao.insert_api_response(insert_data)

            end_time = time.time()  # 処理終了時刻を記録
            elapsed = end_time - start_time
            print(f"[ログ] 銘柄 {stock_code} の処理時間: {elapsed:.2f} 秒")
            dao.close()

    except Exception as e:
        print(f"エラー発生: {e}")
