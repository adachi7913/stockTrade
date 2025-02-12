import os
import sys
import time
import concurrent.futures
import cProfile
import pstats
import threading
from dotenv import load_dotenv

from dao.stock_dao import StockDAO
from lib.indicator_calculator import IndicatorCalculator
from lib.accsess_yFinance_for_stockPrice import StockPriceAPI

from lib.table_category import TableCategory

# 終了要求のためのグローバルフラグ（各タスクでチェックできるように）
shutdown_event = threading.Event()

if __name__ == "__main__":
    # プロファイラーの初期化
    profiler = cProfile.Profile()
    profiler.enable()

    def process_stock(stock_code):
        # .envファイルを再読み込みし、STOP_PRICING_FLAGにより処理停止できるようにする
        load_dotenv(override=True)
        if os.getenv("STOP_PRICING_FLAG", "false").lower() == "y":
            # print(f"STOP_PRICING_FLAGが設定されているため、{stock_code} の処理をスキップします。")
            return

        # 各タスク内で shutdown_event をチェックすることでグレースフルな中断が可能になる
        if shutdown_event.is_set():
            print(f"{stock_code} の処理は中断要求によりスキップされました。")
            return

        try:
            dao = StockDAO()
            start_time = time.time()
            company_info = dao.fetch_company_info(stock_code)
            industry_name = TableCategory.get_table_prefix(company_info[3])
            
            if os.environ.get("PRICING_PROCESS_DONE").lower() == "y":
                stock_price_api = StockPriceAPI(
                    stock_code, os.environ.get("FETCH_DATA_RANGE")
                )
                price_data = stock_price_api.fetch_data_yfinance()
                if not price_data:
                    print(f"株価データの取得に失敗しました: {stock_code}")
                    return
            elif os.environ.get("INDICATOR_PROCESS_DONE").lower() == "y":
                price_data = dao.get_stock_full_data_period(stock_code, industry_name)
                if not price_data:
                    print(f"株価データの取得に失敗しました: {stock_code}")
                    return
            else:
                print("全ての処理が行われない設定になっています。")
                return
            # インジケーター計算
            if os.environ.get("INDICATOR_PROCESS_DONE").lower() == "y":
                indi_instance = IndicatorCalculator(price_data)
                indicator = indi_instance.get_indicators()
                dao.insert_indicator_data(indicator, stock_code, industry_name)
            if os.environ.get("PRICING_PROCESS_DONE").lower == "y":
                for price in price_data:
                    # 中断要求を定期的にチェック（ループ内での中断可能性）
                    if shutdown_event.is_set():
                        print(f"{stock_code} の途中処理が中断されました。")
                        break
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
            except Exception:
                pass

    try:
        # DAO を用いて銘柄コード一覧を取得
        dao = StockDAO()
        stock_codes = dao.fetch_company_code_list()
        stock_codes = stock_codes[3305:]  # 例: 0-490はすでに取得済み
        dao.close()

        # 並列処理用スレッドプールの作成
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        futures = []
        for code in stock_codes:
            futures.append(executor.submit(process_stock, code))

        # 待ち合わせ処理
        # ※ 個々のタスク結果を取得することで、例外もここで拾えます。
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print("タスク中の例外:", e)
    except KeyboardInterrupt:
        # Ctrl+C により KeyboardInterrupt を捕捉
        print("\nCtrl+C が押されたため、処理を中断します。")
        shutdown_event.set()  # タスク内に中断要求を伝播
        executor.shutdown(wait=False)
        sys.exit(0)
    except Exception as e:
        print(f"全体処理エラー: {e}")
    finally:
        # プロファイリング終了＆結果出力
        profiler.disable()
        print("===== プロファイリング結果 =====")
        stats = pstats.Stats(profiler).sort_stats("cumtime")
        stats.print_stats()
