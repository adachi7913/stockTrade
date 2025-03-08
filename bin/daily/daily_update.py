#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob
import os
import sys
import time
import traceback

# プロジェクトルートディレクトリをPythonパスに追加
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lib.tachibana_stock_api_base import TachibanaStockAPI
import logging
from datetime import datetime
from utils.logging_config import setup_logging, cleanup_old_logs

# 標準出力と標準エラー出力のエンコーディングをUTF-8に設定
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

def main():
    # ロギング設定
    logger = setup_logging("daily")
    logger.info("日次株価データ更新処理を開始します")
    
    # tachibana_stock_api_base のロガーレベルを設定
    api_logger = logging.getLogger('lib.tachibana_stock_api_base')
    api_logger.setLevel(logging.INFO)  # INFOレベル以上のログを表示
    
    # コマンドライン引数から開始コードを取得
    start_code = sys.argv[1] if len(sys.argv) > 1 else None
    
    if start_code:
        logger.info(f"開始コード: {start_code}")
    
    try:
        # APIクライアントの初期化 - loggerを渡す
        api = TachibanaStockAPI(logger=logger)
        
        # ログインと株価取得を実行
        logger.info("立花証券APIにログインします")
        try:
            api.execute_stock_price_retrieval(start_code)
            logger.info("株価データ更新処理が完了しました")
        except AttributeError as ae:
            logger.error(f"メソッド呼び出しエラー: {ae}")
            logger.error(f"詳細: {traceback.format_exc()}")
        except Exception as inner_e:
            logger.error(f"API処理中のエラー: {inner_e}")
            logger.error(f"スタックトレース: {traceback.format_exc()}")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        logger.error(f"詳細なエラー情報: {traceback.format_exc()}")
    
    logger.info("日次株価データ更新処理を終了します")

def test_single_stock():
    """1銘柄のみを処理してインジケーター計算をテスト"""
    logger = setup_logging("tachibana")  # 既存のロギング設定を使用
    cleanup_old_logs("tachibana")
    
    try:
        api = TachibanaStockAPI(num_threads=1, logger=logger)  # loggerを渡す
        api.execute_stock_price_retrieval(start_code="1301")  # 極洋を対象にテスト
    except Exception as e:
        logger.error(f"テスト実行中にエラーが発生しました: {str(e)}")
        logger.error(f"詳細: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
