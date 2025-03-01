#!/usr/bin/env python3
import argparse
import logging
import os
import datetime
from service.backtest_service import run_backtest
from utils.logging_config import setup_logging, cleanup_old_logs

def main():
    """メイン関数"""
    # ロギング設定
    logger = setup_logging("backtest")
    logger.info("バックテスト処理を開始します")
    
    # コマンドライン引数のパース
    parser = argparse.ArgumentParser(description='バックテスト実行スクリプト')
    parser.add_argument('--code', type=str, help='銘柄コード（例: 1234）')
    parser.add_argument('--days', type=int, default=90, help='バックテスト期間（日数）')
    parser.add_argument('--capital', type=float, default=1000000, help='初期資本（円）')
    args = parser.parse_args()
    
    if not args.code:
        logger.error("銘柄コードが指定されていません")
        print("銘柄コードの指定が必要です。例: python backtest.py --code 1234")
        return
    
    try:
        # バックテスト実行
        logger.info(f"銘柄コード: {args.code}, 期間: {args.days}日, 初期資本: {args.capital:,}円")
        result = run_backtest(args.code, days=args.days, initial_capital=args.capital)
        
        if result:
            logger.info(f"バックテスト結果: 最終資産 {result['final_capital']:,.0f}円 "
                       f"({result['profit_rate']:.2f}%), 取引回数: {result['trade_count']}回")
        else:
            logger.warning("バックテストの結果が得られませんでした")
    
    except Exception as e:
        logger.error(f"バックテスト処理中にエラーが発生しました: {e}")
    
    logger.info("バックテスト処理が完了しました")

if __name__ == "__main__":
    main()
