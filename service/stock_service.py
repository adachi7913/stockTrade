import time
import concurrent.futures
import threading
from datetime import date, timedelta
from dotenv import load_dotenv
from dao.stock_dao import StockDAO
from lib.accsess_yFinance_for_stockPrice import StockPriceAPI, fetch_batch_data_yfinance
from lib.indicator_calculator import IndicatorCalculator
from lib.table_category import TableCategory
import os
import logging
import psycopg_pool
from typing import List, Dict
import math

# 終了要求用のグローバルフラグ
shutdown_event = threading.Event()

# コネクションプール
db_pool = None

def init_db_pool():
    global db_pool
    if db_pool is None:
        load_dotenv()
        conninfo = (
            f"host={os.environ.get('DB_HOST')} "
            f"dbname={os.environ.get('DB_NAME')} "
            f"user={os.environ.get('DB_USER')} "
            f"password={os.environ.get('DB_PASSWORD')}"
        )
        db_pool = psycopg_pool.ConnectionPool(
            conninfo=conninfo,
            min_size=2,
            max_size=10,
            timeout=30,  # コネクション取得のタイムアウト時間
            max_waiting=20  # 待機キューの最大サイズ
        )
    return db_pool

def get_optimal_batch_size(total_stocks: int) -> int:
    """最適なバッチサイズを計算"""
    return min(max(1, total_stocks // 200), 3)  # 最小1、最大3（さらに負荷を大幅に減らす）

def process_stock_batch(stock_codes: List[str], fetch_range: int, expected_days: int):
    """バッチ処理による株価データの取得と更新"""
    load_dotenv(override=True)
    if os.getenv("STOP_PRICING_FLAG", "false").lower() == "y":
        return

    try:
        dao = StockDAO()
        start_time = time.time()

        # 企業情報の一括取得
        company_infos = {code: dao.fetch_company_info(code) for code in stock_codes}
        valid_codes = [code for code, info in company_infos.items() if info]
        
        if not valid_codes:
            logging.error(f"企業情報取得失敗: {stock_codes}")
            return

        # 業種名のマッピングを作成
        industry_names = {code: TableCategory.get_table_prefix(company_infos[code][3]) 
                         for code in valid_codes}

        # 環境変数による処理モードの判定
        pricing_flag = os.environ.get("PRICING_PROCESS_DONE", "n").lower() == "y"
        indicator_flag = os.environ.get("INDICATOR_PROCESS_DONE", "n").lower() == "y"
        
        logging.info(f"データ取得設定: 取得日数: {fetch_range}日, 予想最大件数: {expected_days}件")

        def validate_price_data(price_data):
            """株価データがnumeric(10,2)の制約に適合するか検証"""
            try:
                # 最大値: 99999999.99（10桁、小数点以下2桁）
                MAX_VALUE = 99999999.99
                MIN_VALUE = -99999999.99

                for key in ['open', 'high', 'low', 'close']:
                    value = float(price_data.get(key, 0))
                    if not MIN_VALUE <= value <= MAX_VALUE or math.isnan(value) or math.isinf(value):
                        logging.warning(f"無効な株価データ（{key}: {value}）を0に置換します。")
                        price_data[key] = 0.0

                # volumeは整数値であることを確認
                volume = price_data.get('volume', 0)
                if not isinstance(volume, (int, float)) or math.isnan(volume) or math.isinf(volume):
                    price_data['volume'] = 0
                else:
                    price_data['volume'] = int(volume)

                return True
            except Exception as e:
                logging.error(f"データ検証エラー: {e}")
                return False

        price_data_batch = {}
        # バッチでの株価データ取得
        if pricing_flag:
            # 各銘柄を個別に処理してエラーの影響を最小限に
            for code in valid_codes:
                max_retries = 2
                base_delay = 5
                success = False
                skip_retries = False
                
                for retry in range(max_retries):
                    try:
                        # StockPriceAPIクラスを使用して1銘柄ずつ処理
                        api = StockPriceAPI(code, fetch_range)
                        single_data = api.fetch_data_yfinance()
                        
                        if single_data:
                            # 各データポイントを検証
                            validated_data = [data for data in single_data if validate_price_data(data)]
                            if validated_data:
                                price_data_batch[code] = validated_data
                                success = True
                                logging.info(f"銘柄 {code} のデータ取得成功（取得件数: {len(validated_data)}件, 予想最大件数: {expected_days}件）")
                                if len(validated_data) > expected_days:
                                    logging.warning(f"銘柄 {code} の取得データ件数が予想を超えています")
                                break
                        
                        wait_time = base_delay * (2 ** retry)
                        logging.info(f"銘柄 {code} の取得待機: {wait_time}秒")
                        time.sleep(wait_time)
                    
                    except Exception as e:
                        error_str = str(e)
                        if "404" in error_str or "Not Found" in error_str or "delisted" in error_str:
                            logging.warning(f"銘柄 {code} は404エラーまたは上場廃止のためスキップします: {e}")
                            skip_retries = True
                            break
                        
                        logging.error(f"銘柄 {code} のデータ取得エラー (試行 {retry + 1}/{max_retries}): {e}")
                        if retry < max_retries - 1 and not skip_retries:
                            wait_time = base_delay * (2 ** retry)
                            time.sleep(wait_time)
                
                if skip_retries:
                    continue
                
                if not success:
                    logging.error(f"銘柄 {code} のデータ取得を諦めます")

        # インジケーター計算用のデータ取得（pricing_flagがFalseの場合）
        if not pricing_flag and indicator_flag:
            price_data_batch = {code: dao.get_stock_full_data_period(code, industry_names[code]) 
                              for code in valid_codes}
        
        if not pricing_flag and not indicator_flag:
            logging.warning("全ての処理が行われない設定になっています。")
            return

        # 各銘柄の処理
        for code in valid_codes:
            if shutdown_event.is_set():
                logging.warning(f"{code} の処理が中断されました。")
                break

            price_data = price_data_batch.get(code)
            if not price_data:
                logging.error(f"株価データの取得に失敗しました: {code}")
                continue

            industry_name = industry_names[code]

            try:
                # インジケーター計算（pricing_flagがTrueの場合も実行）
                if indicator_flag:
                    indicator_calculator = IndicatorCalculator(price_data)
                    indicator = indicator_calculator.get_indicators()
                    dao.insert_indicator_data(indicator, code, industry_name)
                    logging.info(f"銘柄 {code} のインジケーター計算・保存完了")

                # 株価データの挿入
                if pricing_flag and price_data:
                    success_count = 0
                    for price in price_data:
                        if shutdown_event.is_set():
                            break
                        if validate_price_data(price):
                            result = dao.insert_stock_price_data(price, industry_name)
                            if result:
                                success_count += 1
                            else:
                                logging.error(f"株価データ 挿入失敗: {code}, {price}")
                    
                    logging.info(f"銘柄 {code} の株価データ {success_count}/{len(price_data)} 件を挿入完了")

            except Exception as e:
                logging.error(f"銘柄 {code} の処理中エラー: {e}")
                continue

        elapsed = time.time() - start_time
        logging.info(f"バッチ {stock_codes} の処理時間: {elapsed:.2f} 秒")

    except Exception as e:
        logging.error(f"バッチ {stock_codes} の処理中エラー: {e}")
    finally:
        try:
            dao.close()
        except Exception:
            pass

def run_stock_service(expiry=None):
    load_dotenv(override=True)
    init_db_pool()
    
    dao = StockDAO()
    stock_codes = dao.fetch_company_code_list()
    dao.close()
    
    if not stock_codes:
        logging.error("銘柄コードの取得に失敗しました。")
        return

    logging.info(f"処理対象の銘柄コード: {stock_codes}")

    # 取得期間の設定
    if expiry is None:
        # daily_update用の設定
        # 株価データは5日分だが、インジケーター計算用に追加の日数を確保
        fetch_range = 5  # 株価データ取得用
        indicator_days = 52  # インジケーター計算に必要な最小日数
        extra_days = 40  # 余裕を持たせる日数（営業日ベース）を40日に増加
        total_days = indicator_days + extra_days  # 合計92日
        
        if os.environ.get("INDICATOR_PROCESS_DONE", "n").lower() == "y":
            # インジケーター計算が必要な場合は、十分な日数のデータを取得
            fetch_range = total_days
            expected_days = total_days
            logging.info(f"日次更新モード（インジケーター計算あり）: {total_days}日分のデータを取得します")
        else:
            # 株価データのみの更新の場合
            expected_days = 5
            logging.info("日次更新モード（株価のみ）: 5日分のデータを取得します")
    else:
        # confirmOfStockPrice用の設定（FETCH_DATA_RANGE年分）
        years = int(expiry)
        business_days = years * 252
        extra_days = 90
        fetch_range = (years * 365) + extra_days
        expected_days = business_days + 52
        logging.info(f"全期間取得モード: {years}年分のデータを取得します")

    # システムリソースに基づいて最適なワーカー数とバッチサイズを決定
    cpu_count = os.cpu_count() or 4
    max_workers = min(max(2, cpu_count // 2), 4)
    batch_size = get_optimal_batch_size(len(stock_codes))
    
    # バッチに分割して処理
    batches = [stock_codes[i:i + batch_size] for i in range(0, len(stock_codes), batch_size)]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_stock_batch, batch, fetch_range, expected_days) 
                  for batch in batches]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"バッチ処理中の例外: {e}")

if __name__ == "__main__":
    run_stock_service()