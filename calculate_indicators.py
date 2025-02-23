#!/usr/bin/env python3
import glob
import os
import sys
import logging
from datetime import datetime
import time
from typing import Optional
import psutil
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from itertools import islice

from repository.stock_repository import StockRepository
from service.indicator_service import IndicatorService

def setup_logging(log_type):
    today = datetime.now()
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.strftime("%d")
    log_dir = os.path.join("log", year, month)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    # ファイル名は dd_daily.log の形式
    log_file = os.path.join(log_dir, f"{day}_calculate_indicators.log")
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()
    fh = logging.FileHandler(log_file, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

def cleanup_old_logs(log_type):
    now = time.time()
    # ログファイルパターン: /log/**/ *_[daily].log
    pattern = os.path.join("log", "**", "*_calculate_indicators.log")
    for file in glob.glob(pattern, recursive=True):
        if os.path.isfile(file) and now - os.path.getmtime(file) > 7 * 24 * 3600:
            os.remove(file)

def process_stock_batch(batch_codes: list, indicator_service: IndicatorService) -> None:
    """バッチ単位で株価データを処理"""
    for code in batch_codes:
        try:
            # CPU使用率をチェック
            if psutil.cpu_percent(interval=1) > 80:  # 80%以上の場合は一時停止
                logging.warning("CPU使用率が高いため、5秒間処理を一時停止します")
                time.sleep(5)
                
            # 業種名を取得
            industry_name = indicator_service.get_industry_name(code)
            if not industry_name:
                logging.warning(f"業種名の取得に失敗しました: code={code}")
                continue
            
            # 5桁かつ末尾が0の場合、末尾の0を取り除く
            if len(code) == 5 and code.endswith('0'):
                code = code[:-1]
                
            # 株価データを取得
            stock_data = indicator_service.get_stock_price_data(code, industry_name)
            if not stock_data:
                logging.warning(f"株価データの取得に失敗しました: code={code}")
                continue
            
            # インジケーターを計算してDBに保存
            success = indicator_service.calculate_and_save_indicators(stock_data, code, industry_name)
            if success:
                logging.info(f"インジケーター計算・保存成功: code={code}")
            else:
                logging.warning(f"インジケーター計算・保存失敗: code={code}")
                
        except Exception as e:
            logging.error(f"銘柄処理中のエラー: code={code}, error={str(e)}")
            continue

def main():
    """メイン処理"""
    cleanup_old_logs("calculate_indicators")
    logger = setup_logging("calculate_indicators")
    logger.info("calculate_indicators Service Starting")
    logger = logging.getLogger(__name__)
    
    try:
        # CPU使用率の制限を設定
        cpu_count = multiprocessing.cpu_count()
        max_workers = max(1, min(cpu_count - 1, 4))  # CPU数-1か4のいずれか小さい方
        batch_size = 10  # 一度に処理する銘柄数
        
        # リポジトリとサービスのインスタンス化
        stock_repository = StockRepository()
        indicator_service = IndicatorService(stock_repository)
        stock_codes = indicator_service.get_all_stock_codes()
        start_code = sys.argv[1] if len(sys.argv) > 1 else None
        
        # 全株価コードを取得
        if start_code is None:
            start_code = "64110"
            stock_codes = stock_codes[stock_codes.index(start_code):]
        
        if not stock_codes:
            logger.error("株価コードの取得に失敗しました")
            return
            
        logger.info(f"処理対象の株価コード数: {len(stock_codes)}")
        
        # バッチ処理の実行
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for i in range(0, len(stock_codes), batch_size):
                batch = stock_codes[i:i + batch_size]
                executor.submit(process_stock_batch, batch, indicator_service)
                
                # バッチ間で一時停止を入れる
                # time.sleep(1)
                
                # CPU使用率が90%を超えた場合は長めの一時停止
                if psutil.cpu_percent(interval=1) > 90:
                    logger.warning("CPU使用率が非常に高いため、10秒間処理を一時停止します")
                    time.sleep(10)
                
    except Exception as e:
        logger.error(f"処理全体でエラーが発生しました: {str(e)}")
    finally:
        if stock_repository:
            stock_repository.close()
            
if __name__ == "__main__":
    main() 