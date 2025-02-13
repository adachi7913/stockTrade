import time
import concurrent.futures
import threading
from datetime import date, timedelta
from dotenv import load_dotenv
from dao.stock_dao import StockDAO
from lib.accsess_yFinance_for_stockPrice import StockPriceAPI
from lib.indicator_calculator import IndicatorCalculator
from lib.table_category import TableCategory
import os

# 終了要求用のグローバルフラグ
shutdown_event = threading.Event()

def process_stock(stock_code):
    load_dotenv(override=True)
    if os.getenv("STOP_PRICING_FLAG", "false").lower() == "y":
        return
    try:
        dao = StockDAO()
        start_time = time.time()
        company_info = dao.fetch_company_info(stock_code)
        if not company_info:
            print(f"企業情報取得失敗: {stock_code}")
            return
        industry_name = TableCategory.get_table_prefix(company_info[3])

        # 環境変数による処理モードの判定
        pricing_flag = os.environ.get("PRICING_PROCESS_DONE", "n").lower() == "y"
        indicator_flag = os.environ.get("INDICATOR_PROCESS_DONE", "n").lower() == "y"
        fetch_range = os.environ.get("FETCH_DATA_RANGE", "")

        if pricing_flag:
            if fetch_range == "":
                stock_price_api = StockPriceAPI(stock_code)
            else:
                stock_price_api = StockPriceAPI(stock_code, fetch_range)
            price_data = stock_price_api.fetch_data_yfinance()
            if not price_data:
                print(f"株価データの取得に失敗しました: {stock_code}")
                return
        elif indicator_flag:
            price_data = dao.get_stock_full_data_period(stock_code, industry_name)
            if not price_data:
                print(f"株価データの取得に失敗しました: {stock_code}")
                return
        else:
            print("全ての処理が行われない設定になっています。")
            return

        # 最新データと過去データのマージ（expairyがNoneの場合のみ）
        if pricing_flag:
            if stock_price_api.expairy is None:
                historical_data = dao.get_stock_full_data_period(stock_code, industry_name)
                latest_data = price_data
                if historical_data:
                    if historical_data[-1]['date'] != latest_data[0]['date']:
                        full_data = historical_data + latest_data
                    else:
                        full_data = historical_data
                else:
                    full_data = latest_data
            else:
                full_data = dao.get_stock_full_data_period(stock_code, industry_name)
        else:
            full_data = price_data

        # モニタリング用出力
        if full_data:
            print(f"{stock_code}: マージ後データ件数 {len(full_data)}、最新日は {full_data[-1]['date']}")
        else:
            print(f"{stock_code}: full_data が取得できませんでした。")

        # インジケーター計算（必要な場合）
        if indicator_flag:
            indicator_calculator = IndicatorCalculator(price_data)
            indicator = indicator_calculator.get_indicators()
            dao.insert_indicator_data(indicator, stock_code, industry_name)

        # 株価データの挿入（必要な場合）
        if pricing_flag:
            for price in price_data:
                if shutdown_event.is_set():
                    print(f"{stock_code} の途中処理が中断されました。")
                    break
                result = dao.insert_stock_price_data(price, industry_name)
                if result is False:
                    print(f"株価データ 挿入停止: {stock_code}")
                    break

        elapsed = time.time() - start_time
        print(f"[ログ] 銘柄 {stock_code} の処理時間: {elapsed:.2f} 秒")
    except Exception as e:
        print(f"銘柄 {stock_code} の処理中エラー: {e}")
    finally:
        try:
            dao.close()
        except Exception:
            pass

def run_stock_service():
    load_dotenv(override=True)
    dao = StockDAO()
    stock_codes = dao.fetch_company_code_list()
    dao.close()
    print("stock_codes:", stock_codes)

    max_workers = 5  # 必要に応じて調整
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
         futures = [executor.submit(process_stock, code) for code in stock_codes]
         for future in concurrent.futures.as_completed(futures):
             try:
                 future.result()
             except Exception as e:
                 print("タスク中の例外:", e)

if __name__ == "__main__":
    run_stock_service() 