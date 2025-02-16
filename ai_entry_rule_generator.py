#!/usr/bin/env python3
from service.ai_rule_service import run_ai_rule_generation
import logging
import os
import datetime
import glob
import time
import sys
from dotenv import load_dotenv
from utils.date_util import is_holiday

if __name__ == "__main__":
    # 環境変数を確実に読み込む
    load_dotenv(override=True)
    
    def setup_logging(log_type):
        today = datetime.datetime.now()
        year = today.strftime("%Y")
        month = today.strftime("%m")
        day = today.strftime("%d")
        log_dir = os.path.join("log", year, month)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        # ファイル名は dd_entryRule.log の形式
        log_file = os.path.join(log_dir, f"{day}_entryRule.log")
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
        # ログファイルパターン: /log/**/ *_[entryRule].log
        pattern = os.path.join("log", "**", "*_entryRule.log")
        for file in glob.glob(pattern, recursive=True):
            if os.path.isfile(file) and now - os.path.getmtime(file) > 7 * 24 * 3600:
                os.remove(file)

    cleanup_old_logs("entryRule")
    logger = setup_logging("entryRule")
    logger.info("Entry Rule Generation Starting")

    # 休日判定
    if is_holiday():
        logger.info("本日は休日のため、処理を終了します")
        sys.exit(0)

    # 必要に応じて開始銘柄コードを指定（例："27820"）
    # run_ai_rule_generation(start_code="99970")
    run_ai_rule_generation()