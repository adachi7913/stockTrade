import time
import traceback
import concurrent.futures
from dotenv import load_dotenv  # .env再読み込み用
import os
import logging

from repository.stock_repository import StockRepository
from Gemini.api_handler import ApiHandler
from lib.parse_response import parse_response
from lib.table_category import TableCategory
from lib.code_validator import validate_stock_code
from discord.discord_notifier import create_error_message
from service.backtest_service import run_multiple_backtests

def run_ai_rule_generation(start_code=None):
    try:
        logging.info("Entry Rule Generation Starting")

        # 銘柄コード一覧を取得
        tmp_repository = StockRepository()
        stock_codes = tmp_repository.fetch_company_code_list()
        tmp_repository.close()

        if start_code is not None and start_code in stock_codes:
            start_index = stock_codes.index(start_code)
            stock_codes = stock_codes[start_index:]
        logging.info("対象銘柄コード: %s", stock_codes)

        # 各銘柄の処理を複数スレッドで並列実行
        def process_stock(stock_code):
            # .envファイルを再読み込みし、動的な値の更新を反映
            load_dotenv(override=True)
            if os.getenv("STOP_GEMINI_FLAG", "false").lower() == "y":
                logging.info(f"停止フラグが検出されました。銘柄 {stock_code} の処理をスキップします。")
                return

            repository = StockRepository()
            try:
                # 処理開始前に停止フラグを確認
                load_dotenv(override=True)
                if os.getenv("STOP_GEMINI_FLAG", "false").lower() == "y":
                    logging.info(f"停止フラグが検出されました。銘柄 {stock_code} の処理をスキップします。")
                    return

                industry_name = repository.fetch_industry_name_prefix(stock_code)
                if not industry_name:
                    logging.error(f"企業情報取得失敗: {stock_code}")
                    return

                # 銘柄コードのバリデーション
                validated_code = validate_stock_code(stock_code)
                
                full_data = repository.get_stock_full_data_period(validated_code, industry_name)
                if not full_data:
                    logging.error(f"株価データ取得失敗: {stock_code}")
                    return

                # 最新レコードから終値を取得
                latest_record = full_data[-1]
                close_price = float(latest_record.get("close", 0))

                # 時価総額および最新のエントリー不可情報を取得
                market_cap = repository.fetch_market_cap(stock_code)
                no_entry_info = repository.fetch_no_entry_info(stock_code)
                if no_entry_info is not None:
                    if isinstance(no_entry_info, tuple):
                        last_entry_date, no_entry_span = no_entry_info
                    elif isinstance(no_entry_info, int):
                        last_entry_date, no_entry_span = None, no_entry_info
                    else:
                        logging.error(f"{stock_code}: 予期しない形式の no_entry_info: {no_entry_info}")
                        last_entry_date, no_entry_span = None, None
                else:
                    last_entry_date, no_entry_span = None, None

                # バックテスト前に停止フラグを確認
                load_dotenv(override=True)
                if os.getenv("STOP_GEMINI_FLAG", "false").lower() == "y":
                    logging.info(f"停止フラグが検出されました。銘柄 {stock_code} の処理をスキップします。")
                    return

                from lib.stock_filter import filter_stock
                # full_data内の各日付の出来高を抽出（float型に変換）
                volume_data = [float(record.get("volume", 0)) for record in full_data]
                # 最新の指標データを最新レコードから取得
                atr = float(latest_record.get("atr", 0))
                rsi_val = float(latest_record.get("rsi", 0))
                stoch_k = float(latest_record.get("stoch_k", 0))
                if not filter_stock(stock_code, close_price, market_cap, last_entry_date, no_entry_span, volume_data, atr, rsi_val, stoch_k):
                    return

                # バックテスト結果を取得
                logging.info(f"{stock_code}: バックテスト実行開始")
                backtest_results = []
                try:
                    # 銘柄コードから末尾の0を除去（yFinance API用）
                    # 5桁の場合のみ末尾の0を除去し、4桁以下の場合はそのまま使用
                    yfinance_code = validated_code
                    if len(validated_code) == 5 and validated_code.endswith('0'):
                        yfinance_code = validated_code[:-1]
                    backtest_results = run_multiple_backtests(yfinance_code)
                    logging.info(f"{stock_code}: バックテスト実行完了 - {len(backtest_results)}件の結果を取得")
                except Exception as e:
                    logging.error(f"{stock_code}: バックテスト実行エラー: {e}")
                    # バックテストエラーでも処理は続行

                # API呼び出し前に停止フラグを確認
                load_dotenv(override=True)
                if os.getenv("STOP_GEMINI_FLAG", "false").lower() == "y":
                    logging.info(f"停止フラグが検出されました。銘柄 {stock_code} の処理をスキップします。")
                    return

                # Gemini API 呼び出し
                handler = ApiHandler(full_data, backtest_results)
                response = handler.call_gemini_api()
                time.sleep(5)
                # Gemini API がエラー（200以外）の場合は、エラーメッセージが返る想定
                if (isinstance(response, str) and response.startswith("Gemini API call failed")) or (isinstance(response, dict) and response.get("error")):
                    logging.warning(f"{stock_code}: Gemini APIエラー発生のためスキップ")
                    return

                logging.info("銘柄コード: %s", stock_code)
                logging.info("Gemini API response: %s", response)
                insert_data = parse_response(full_data, response)
                if not insert_data:
                    logging.error(f"生成された挿入データが無効: {stock_code}")
                    return

                repository.insert_api_response(insert_data)
            except Exception as e:
                error_msg = traceback.format_exc()
                logging.error(f"銘柄 {stock_code} の処理中エラー:\n{error_msg}")
                create_error_message(error_msg)
            finally:
                try:
                    repository.close()
                except Exception:
                    pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            futures = []
            for stock_code in stock_codes:
                # 各銘柄の処理を開始する前に停止フラグを確認
                load_dotenv(override=True)
                if os.getenv("STOP_GEMINI_FLAG", "false").lower() == "y":
                    logging.info("停止フラグが検出されました。残りの銘柄の処理をスキップします。")
                    break
                futures.append(executor.submit(process_stock, stock_code))
            
            # 実行中のタスクの完了を待機
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"タスク実行中のエラー: {e}")
                
                # 各タスク完了後に停止フラグを確認
                load_dotenv(override=True)
                if os.getenv("STOP_GEMINI_FLAG", "false").lower() == "y":
                    logging.info("停止フラグが検出されました。残りのタスクは完了次第終了します。")
    except Exception as e:
        error_msg = traceback.format_exc()
        logging.error(f"全体処理エラー: {e}")
        create_error_message(error_msg)
    finally:
        logging.info("Entry Rule Generation Completed")

if __name__ == "__main__":
    # 必要に応じて開始銘柄コードを設定します（例："27820"）
    run_ai_rule_generation(start_code="99970") 