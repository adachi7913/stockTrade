import time
import traceback

from Gemini.api_handler import ApiHandler

from dao.stock_dao import StockDAO

from discord.discord_notifier import create_error_message
from lib.parse_response import parse_response
from lib.table_category import TableCategory


if __name__ == "__main__":
    try:
        dao = StockDAO()
        stock_codes = dao.fetch_company_code_list()
        # stock_codes = stock_codes[68:] # 0-68はすでに取得済み
        # stock_codes = stock_codes[216:] # 0-216はすでに取得済み
        # stock_codes = stock_codes[297:]  # 0-292はすでに取得済み
        # stock_codes = stock_codes[297:]  # 0-490はすでに取得済み
        # print("stock_codes:", stock_codes[0])
        # print(stock_codes)
        # stock_code = stock_codes[10]
        dao.close()
        for stock_code in stock_codes:
            start_time = time.time()  # 処理開始時刻を記録
            dao = StockDAO()
            company_info = dao.fetch_company_info(stock_code)
            industry_name = TableCategory.get_table_prefix(
                company_info[3]
            )  # 企業名の取得
            full_data = dao.get_stock_full_data_period(stock_code, industry_name)
            handler = ApiHandler(full_data)
            response = handler.call_gemini_api()
            print("response:", response)

            insert_data = parse_response(full_data, response)
            if insert_data == None:
                continue
            print("insert_data:", insert_data)
            dao.insert_api_response(insert_data)

            end_time = time.time()  # 処理終了時刻を記録
            elapsed = end_time - start_time
            print(f"[ログ] 銘柄 {stock_code} の処理時間: {elapsed:.2f} 秒")
            dao.close()
    except Exception as e:
        print(f"エラー発生: {e}")
        dao.close()
        create_error_message(traceback.format_exc())