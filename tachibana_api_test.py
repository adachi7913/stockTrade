import glob
import os
import sys
import time
from lib.tachibana_stock_api_base import TachibanaStockAPI
import logging
from datetime import datetime

def setup_logging(log_type):
    today = datetime.now()
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.strftime("%d")
    log_dir = os.path.join("log", year, month)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    # ファイル名は dd_daily.log の形式
    log_file = os.path.join(log_dir, f"{day}_tachibana.log")
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
    # ログファイルパターン: /log/**/ *_[tachibana].log
    pattern = os.path.join("log", "**", "*_daily.log")
    for file in glob.glob(pattern, recursive=True):
        if os.path.isfile(file) and now - os.path.getmtime(file) > 7 * 24 * 3600:
            os.remove(file)

def main():
    logger = setup_logging("tachibana")
    cleanup_old_logs("tachibana")

    # コマンドライン引数から開始コードを取得
    start_code = sys.argv[1] if len(sys.argv) > 1 else None
    if start_code is None:
        start_code = "9880"
    try:
        api = TachibanaStockAPI()
        api.execute_stock_price_retrieval(start_code)
    except Exception as e:
        logger.error(f"株価データ取得処理でエラーが発生しました: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
