import time
import traceback
import concurrent.futures

from dao.stock_dao import StockDAO
from Gemini.api_handler import ApiHandler
from lib.parse_response import parse_response
from lib.table_category import TableCategory
from discord.discord_notifier import create_error_message

def run_ai_rule_generation(start_code=None):
    try:
        # 取得用のDAOは別途作成して銘柄コード一覧を取得
        tmp_dao = StockDAO()
        stock_codes = tmp_dao.fetch_company_code_list()
        tmp_dao.close()

        if start_code is not None and start_code in stock_codes:
            start_index = stock_codes.index(start_code)
            stock_codes = stock_codes[start_index:]
        print("対象銘柄コード:", stock_codes)

        # 各銘柄の処理を4スレッドで並列実行
        def process_stock(stock_code):
            dao = StockDAO()
            try:
                company_info = dao.fetch_company_info(stock_code)
                if not company_info:
                    print(f"企業情報取得失敗: {stock_code}")
                    return

                industry_name = TableCategory.get_table_prefix(company_info[3])
                full_data = dao.get_stock_full_data_period(stock_code, industry_name)
                if not full_data:
                    print(f"株価データ取得失敗: {stock_code}")
                    return

                # --- フィルター処理 ---
                # 最新レコードから終値を取得
                latest_record = full_data[-1]
                close_price = float(latest_record.get("close", 0))
                # フィルターはyfinanceのティッカー記法（例:"7203.T"）を想定するため補正
                ticker_symbol = stock_code if stock_code.endswith(".T") else stock_code + ".T"
                from lib.stock_filter import filter_stock
                if not filter_stock(ticker_symbol, close_price):
                    print(f"{stock_code}: フィルターによりGemini APIリクエスト対象外")
                    return

                # --- Gemini API 呼び出し ---
                handler = ApiHandler(full_data)
                response = handler.call_gemini_api()
                # Gemini API がエラー（200以外）の場合は、エラーメッセージが返る想定
                if (isinstance(response, str) and response.startswith("Gemini API call failed")) or (isinstance(response, dict) and response.get("error")):
                    print(f"{stock_code}: Gemini APIエラー発生のためスキップ")
                    return

                print("Gemini API response:", response)
                insert_data = parse_response(full_data, response)
                if not insert_data:
                    print(f"生成された挿入データが無効: {stock_code}")
                    return

                print("生成された挿入データ:", insert_data)
                dao.insert_api_response(insert_data)
            except Exception as e:
                error_msg = traceback.format_exc()
                print(f"銘柄 {stock_code} 処理中エラー: {e}")
                create_error_message(error_msg)
            finally:
                try:
                    dao.close()
                except Exception:
                    pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(process_stock, stock_codes)
    except Exception as e:
        error_msg = traceback.format_exc()
        print(f"全体処理エラー: {e}")
        create_error_message(error_msg)

if __name__ == "__main__":
    # 必要に応じて開始銘柄コードを設定します（例："27820"）
    run_ai_rule_generation(start_code="27820") 