#!/usr/bin/env python3
import argparse
import logging
import os
import datetime
from service.backtest_service import run_backtest

def setup_logging():
    """ログの設定を行います"""
    today = datetime.datetime.now()
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.strftime("%d")
    log_dir = os.path.join("log", year, month)
    
    # ログディレクトリが存在しない場合は作成
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # ファイル名は dd_backtest.log の形式
    log_file = os.path.join(log_dir, f"{day}_backtest.log")
    
    # ロガーの設定
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 既存のハンドラをクリア
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # ファイルハンドラの設定
    fh = logging.FileHandler(log_file, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    # コンソールハンドラの設定
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    return logger

def main():
    # ログの設定
    logger = setup_logging()
    logger.info("バックテスト処理を開始します")

    parser = argparse.ArgumentParser(description="バックテスト実行用スクリプトです。")
    parser.add_argument("symbol", type=str, help="銘柄シンボルを指定してください（例: 1301）")
    parser.add_argument("start_date", type=str, help="開始日（YYYY-MM-DD形式）")
    parser.add_argument("end_date", type=str, help="終了日（YYYY-MM-DD形式）")
    parser.add_argument("strategy", type=str, choices=["tr", "re", "bo"],
                        help="戦略タイプを指定してください: tr=trend, re=reverse, bo=breakout")
    parser.add_argument("lot_size", type=int, nargs='?', default=100,
                        help="1回の取引での発注数量（単位：株）（デフォルト: 100株）")
    args = parser.parse_args()

    run_backtest(args.symbol, args.start_date, args.end_date, args.strategy, args.lot_size)
    logger.info("バックテスト処理が完了しました")

if __name__ == "__main__":
    main()
    # python backtest.py 1301 2021-02-01 2025-02-18 tr 200
