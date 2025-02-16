#!/usr/bin/env python3
import logging
import os
import datetime
import glob
import time
import sys
from dotenv import load_dotenv
from service.stock_service import run_stock_service
from utils.date_util import is_holiday
from utils.logging_config import setup_logging

def setup_logging(log_type):
    today = datetime.datetime.now()
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.strftime("%d")
    log_dir = os.path.join("log", year, month)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    # ファイル名は dd_daily.log の形式
    log_file = os.path.join(log_dir, f"{day}_daily.log")
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
    pattern = os.path.join("log", "**", "*_daily.log")
    for file in glob.glob(pattern, recursive=True):
        if os.path.isfile(file) and now - os.path.getmtime(file) > 7 * 24 * 3600:
            os.remove(file)

if __name__ == "__main__":
    # 環境変数を確実に読み込む
    load_dotenv(override=True)
    
    cleanup_old_logs("daily")
    logger = setup_logging("daily")
    logger.info("Daily Service Starting")

    # 休日判定
    if is_holiday():
        logger.info("本日は休日のため、処理を終了します")
        sys.exit(0)

    run_stock_service()  # expiry=None（デフォルト値）で5日分のデータ取得 