#!/usr/bin/env python3
# プロジェクトルートディレクトリをPythonパスに追加
import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from service.ai_rule_service import run_ai_rule_generation
import logging
import datetime
import glob
import time
import signal
from dotenv import load_dotenv, set_key
from utils.date_util import is_holiday
from utils.logging_config import setup_logging, cleanup_old_logs

# グローバル変数で停止フラグを管理
stop_processing = False
# グローバルロガー変数
logger = None

# シグナルハンドラ関数
def signal_handler(sig, frame):
    global stop_processing, logger
    print("\nCtrl+C が押されました。処理を安全に停止します...")
    if logger:
        logger.info("ユーザーによる中断シグナルを受信しました。処理を停止します。")
    else:
        print("ユーザーによる中断シグナルを受信しました。処理を停止します。")
    
    stop_processing = True
    # .envファイルに停止フラグを設定
    dotenv_path = os.path.join(project_root, '.env')
    set_key(dotenv_path, "STOP_GEMINI_FLAG", "y")
    
    if logger:
        logger.info("停止フラグを設定しました。現在の処理が完了次第、プログラムは終了します。")
    else:
        print("停止フラグを設定しました。現在の処理が完了次第、プログラムは終了します。")

if __name__ == "__main__":
    # 環境変数を確実に読み込む
    load_dotenv(override=True)
    
    # ロギングの設定
    logger = setup_logging("entryRule")
    
    # シグナルハンドラを設定
    signal.signal(signal.SIGINT, signal_handler)
    
    # 停止フラグをリセット
    dotenv_path = os.path.join(project_root, '.env')
    set_key(dotenv_path, "STOP_GEMINI_FLAG", "false")
    
    logger.info("AIエントリールール生成処理を開始します")
    
    # 休日判定
    if is_holiday():
        logger.info("本日は休日のため、処理を終了します")
        sys.exit(0)
    
    # AIルール生成処理を実行
    run_ai_rule_generation(logger=logger)
    
    logger.info("AIエントリールール生成処理が完了しました")