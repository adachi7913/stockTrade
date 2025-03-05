#!/usr/bin/env python3
import sys
import traceback
from lib.tachibana_stock_api_base import TachibanaStockAPI
from utils.logging_config import setup_logging, cleanup_old_logs

def test_single_stock():
    """1銘柄のみを処理してインジケーター計算をテスト"""
    logger = setup_logging("tachibana_test")
    cleanup_old_logs("tachibana_test")
    
    try:
        api = TachibanaStockAPI(num_threads=1, logger=logger)
        api.execute_stock_price_retrieval(start_code="1301")  # 極洋を対象にテスト
    except Exception as e:
        logger.error(f"テスト実行中にエラーが発生しました: {str(e)}")
        logger.error(f"詳細: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    test_single_stock() 