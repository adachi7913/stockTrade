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

def run_ai_rule_generation(logger=None):
    if logger is None:
        # ロガーが渡されなかった場合はデフォルトロガーを使用
        from utils.logging_config import setup_logging
        logger = setup_logging("entryRule")
        
    try:
        logger.info("Entry Rule Generation Starting")
        logger.info("Ctrl+C で処理を安全に停止できます")

        # 銘柄コード一覧を取得
        tmp_repository = StockRepository()
        stock_codes = tmp_repository.fetch_company_code_list()
        tmp_repository.close()

        start_code = os.getenv("START_CODE")
        if start_code is not None and start_code in stock_codes:
            start_index = stock_codes.index(start_code)
            stock_codes = stock_codes[start_index:]
        logger.info("対象銘柄コード: %s", stock_codes)

        # 各銘柄の処理を複数スレッドで並列実行
        def process_stock(stock_code):
            # .envファイルを再読み込みし、動的な値の更新を反映
            load_dotenv(override=True)
            if os.getenv("STOP_GEMINI_FLAG", "false").lower() == "y":
                # logger.info(f"停止フラグが検出されました。銘柄 {stock_code} の処理をスキップします。")
                return

            repository = StockRepository()
            try:
                # 処理開始前に停止フラグを確認
                load_dotenv(override=True)
                if os.getenv("STOP_GEMINI_FLAG", "false").lower() == "y":
                    # logger.info(f"停止フラグが検出されました。銘柄 {stock_code} の処理をスキップします。")
                    return

                industry_name = repository.fetch_industry_name_prefix(stock_code)
                if not industry_name:
                    logger.error(f"企業情報取得失敗: {stock_code}")
                    return

                # 4桁コードに変換
                code_4digit = validate_stock_code(stock_code)
                
                # 株価情報を確認
                latest_price = repository.get_latest_price(code_4digit, industry_name)
                if not latest_price:
                    logger.warning(f"{stock_code}: 株価情報がありません")
                    return

                # フィルタリング 1: 株価が100円以上5000円以下
                close_price = float(latest_price['close'])
                if close_price < 100:
                    logger.info(f"{stock_code}: 終値 {close_price} 円 は最低価格 100 円以上の条件を満たしていません。")
                    return
                if close_price > 5000:
                    logger.info(f"{stock_code}: 終値 {close_price} 円 は 5000 円以下の条件を満たしていません。")
                    return

                # フィルタリング 2: 平均出来高代金が一定以上 (5000万円)
                avg_volume = repository.get_average_volume(code_4digit, industry_name, days=15)
                avg_trading_value = avg_volume * close_price
                if avg_trading_value < 50000000: # 5000万円未満はスキップ
                    logger.info(f"{stock_code}: 過去15日の平均出来高代金が5000万円未満（{avg_trading_value:,.0f}円）のため除外")
                    return

                # フィルタリング 3: ストップ高・ストップ安が続いていないか ← このフィルタは削除

                # すべての条件を満たした場合
                logger.info(f"{stock_code}: 全てのフィルタ条件を満たしています。")
                
                # バックテスト実行
                logger.info(f"{stock_code}: バックテスト実行開始")
                backtest_results = run_multiple_backtests(code_4digit, industry_name, logger=logger)
                
                if not backtest_results or len(backtest_results) == 0:
                    logger.warning(f"{stock_code}: バックテスト結果が取得できませんでした")
                    return
                    
                logger.info(f"{stock_code}: バックテスト実行完了 - {len(backtest_results)}件の結果を取得")
                
                # Gemini API呼び出し
                try:
                    # .envから取得期間を取得（年数指定。デフォルトは1年*230営業日）
                    fetch_range = int(os.getenv("FETCH_DATA_RANGE", "1"))*230
                    logger.info(f"{stock_code}: データ取得期間: {fetch_range}日")
                    
                    # 株価履歴とインジケータデータの取得
                    price_and_indicators = repository.get_stock_full_data_period(code_4digit, industry_name)
                    if not price_and_indicators:
                        logger.warning(f"{stock_code}: 株価履歴またはインジケータが取得できませんでした")
                        return
                        
                    # APIハンドラの初期化 - ここを修正
                    api_key = os.getenv("GEMINI_API_KEY")
                    if not api_key:
                        logger.error("GEMINI_API_KEY が設定されていません")
                        return
                    
                    # 環境変数にAPIキーを設定しておく（ApiHandler内部で使用されるため）
                    os.environ["GEMINI_API_KEY"] = api_key
                    
                    logger.info(f"Gemini APIリクエスト開始: 銘柄={stock_code}")
                    
                    # ApiHandlerはpriceデータとバックテスト結果を受け取る
                    api_handler = ApiHandler(price_and_indicators, backtest_results=backtest_results, logger=logger)
                    
                    # API呼び出し - パラメータなしでcall_gemini_apiを呼び出す
                    response = api_handler.call_gemini_api()
                    
                    # レスポンス解析
                    if response:
                        logger.info(f"銘柄コード: {stock_code}")
                        logger.info(f"Gemini API response: {response}")
                        
                        # レスポンスをDBに保存
                        parsed_result = parse_response(price_and_indicators, response, code=code_4digit, logger=logger)
                        if parsed_result:
                            repository.insert_api_response(parsed_result)
                            logger.info(f"{stock_code}: AIエントリー判断をDBに保存しました")
                        else:
                            logger.warning(f"{stock_code}: AIレスポンスの解析に失敗しました")
                    else:
                        logger.error(f"{stock_code}: Gemini APIからの応答がありません")
                
                except Exception as api_error:
                    logger.error(f"{stock_code}: API呼び出し中にエラーが発生しました: {str(api_error)}")
                    logger.error(traceback.format_exc())

            except Exception as e:
                logger.error(f"銘柄 {stock_code} の処理中にエラーが発生しました: {str(e)}")
                logger.error(traceback.format_exc())
            finally:
                repository.close()

        # スレッドプールで並列処理
        max_workers = int(os.getenv("MAX_WORKERS", "1"))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_stock, code): code for code in stock_codes}
            
            for future in concurrent.futures.as_completed(futures):
                code = futures[future]
                try:
                    future.result()  # 例外があれば再スロー
                except Exception as e:
                    logger.error(f"銘柄 {code} の処理中に例外が発生しました: {str(e)}")
                    logger.error(traceback.format_exc())
                    
                    # Discordに通知
                    error_message = create_error_message(
                        title="AIエントリールール生成エラー",
                        code=code,
                        error=str(e),
                        traceback=traceback.format_exc()
                    )
                    # ここでDiscord通知処理を呼び出す（実装は省略）

    except Exception as e:
        logger.error(f"AI Entry Rule Generation でエラーが発生しました: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Discordに通知
        error_message = create_error_message(
            title="AIエントリールール生成 - 重大なエラー",
            error=str(e),
            traceback=traceback.format_exc()
        )
        # ここでDiscord通知処理を呼び出す（実装は省略）

if __name__ == "__main__":
    # 必要に応じて開始銘柄コードを設定します（例："27820"）
    run_ai_rule_generation(start_code="99970") 