#!/usr/bin/env python3
import logging
import os
import datetime
import glob
import time
import sys
from dotenv import load_dotenv
from service.stock_service import run_stock_service
from utils.logging_config import setup_logging, cleanup_old_logs

# .envファイルの読み込み
load_dotenv()

# ログを設定
logger = setup_logging("stockPrice")

def main():
    """
    メイン関数。
    """
    logger.info("株価確認処理を開始します")
    
    # 最新の株価確認
    run_stock_service()
    
    logger.info("株価確認処理が完了しました")

if __name__ == "__main__":
    main()
