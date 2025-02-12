import time
import traceback
import concurrent.futures
from dotenv import load_dotenv  # .env再読み込み用
import os

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

        # 各銘柄の処理を複数スレッドで並列実行
        def process_stock(stock_code):
            # .envファイルを再読み込みし、動的な値の更新を反映
            load_dotenv(override=True)
            if os.getenv("STOP_GEMINI_FLAG", "false").lower() == "y":
                # print(f"STOP_GEMINI_FLAGが設定されているため、{stock_code} の処理をスキップします。")
                return

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

                # DAOから時価総額および最新のエントリー不可情報を取得
                market_cap = dao.fetch_market_cap(stock_code)
                no_entry_info = dao.fetch_no_entry_info(stock_code)
                if no_entry_info is not None:
                    last_entry_date, no_entry_span = no_entry_info
                else:
                    last_entry_date, no_entry_span = None, None

                from lib.stock_filter import filter_stock
                if not filter_stock(stock_code, close_price, market_cap, last_entry_date, no_entry_span):
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

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            executor.map(process_stock, stock_codes)
    except Exception as e:
        error_msg = traceback.format_exc()
        print(f"全体処理エラー: {e}")
        create_error_message(error_msg)

if __name__ == "__main__":
    # 必要に応じて開始銘柄コードを設定します（例："27820"）
    run_ai_rule_generation(start_code="27820") 