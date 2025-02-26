#!/usr/bin/env python3
from service.ai_rule_service import run_ai_rule_generation
import logging
import os
import datetime
import glob
import time
import sys
import signal
from dotenv import load_dotenv, set_key
from utils.date_util import is_holiday

# グローバル変数で停止フラグを管理
stop_processing = False

# シグナルハンドラ関数
def signal_handler(sig, frame):
    global stop_processing
    print("\nCtrl+C が押されました。処理を安全に停止します...")
    logging.info("ユーザーによる中断シグナルを受信しました。処理を停止します。")
    stop_processing = True
    # .envファイルに停止フラグを設定
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    set_key(dotenv_path, "STOP_GEMINI_FLAG", "y")
    logging.info("停止フラグを設定しました。現在の処理が完了次第、プログラムは終了します。")

if __name__ == "__main__":
    # 環境変数を確実に読み込む
    load_dotenv(override=True)
    
    # シグナルハンドラを設定
    signal.signal(signal.SIGINT, signal_handler)
    
    # 停止フラグをリセット
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    set_key(dotenv_path, "STOP_GEMINI_FLAG", "false")
    
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
    logger.info("Ctrl+C で処理を安全に停止できます")

    # 休日判定
    if is_holiday():
        logger.info("本日は休日のため、処理を終了します")
        sys.exit(0)

    try:
        # 必要に応じて開始銘柄コードを指定（例："27820"）
        # run_ai_rule_generation(start_code="99970")
        run_ai_rule_generation()
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
    finally:
        # 停止フラグをリセット
        set_key(dotenv_path, "STOP_GEMINI_FLAG", "false")
        logger.info("処理を終了します")