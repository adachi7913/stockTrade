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
from utils.logging_config import setup_logging, cleanup_old_logs

# .envファイルの読み込み
load_dotenv()

# ロギング設定
logger = setup_logging("daily")

def main():
    """
    メイン関数
    """
    # 今日が休日かどうかチェック
    today = datetime.datetime.now().date()
    if is_holiday(today):
        logger.info(f"{today}は休日のため、処理をスキップします。")
        return

    # 処理開始
    logger.info("日次更新処理を開始します。")
    
    # 株価データ更新
    run_stock_service(expiry=1)  # 最新1日のデータのみ取得
    
    logger.info("日次更新処理が完了しました。")

if __name__ == "__main__":
    main() 