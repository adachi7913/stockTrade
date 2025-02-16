#!/usr/bin/env python3
import logging
import os
import datetime
import glob
import time
import sys
from dotenv import load_dotenv
from service.stock_service import run_stock_service

def setup_logging(log_type):
    today = datetime.datetime.now()
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.strftime("%d")
    log_dir = os.path.join("log", year, month)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    # ファイル名は dd_stockPrice.log の形式
    log_file = os.path.join(log_dir, f"{day}_stockPrice.log")
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
    # ログファイルパターン: /log/**/ *_[stockPrice].log
    pattern = os.path.join("log", "**", "*_stockPrice.log")
    for file in glob.glob(pattern, recursive=True):
        if os.path.isfile(file) and now - os.path.getmtime(file) > 7 * 24 * 3600:
            os.remove(file)

if __name__ == "__main__":
    # 環境変数を確実に読み込む
    load_dotenv(override=True)
    
    cleanup_old_logs("stockPrice")
    logger = setup_logging("stockPrice")
    logger.info("Stock Service Starting")
    
    # FETCH_DATA_RANGEを整数として取得
    fetch_range = os.environ.get("FETCH_DATA_RANGE")
    if fetch_range:
        try:
            fetch_range = int(fetch_range)
            logger.info(f"取得期間: {fetch_range}年")
        except ValueError:
            logger.error(f"FETCH_DATA_RANGEの値が不正です: {fetch_range}")
            sys.exit(1)
    else:
        logger.error("FETCH_DATA_RANGEが設定されていません")
        sys.exit(1)
    
    # コマンドライン引数から開始銘柄コードを取得
    start_code = None
    if len(sys.argv) > 1:
        start_code = sys.argv[1]
        logger.info(f"開始銘柄コード: {start_code}")
    
    run_stock_service(expiry=fetch_range, start_code=start_code)  # 整数に変換した値を渡す 