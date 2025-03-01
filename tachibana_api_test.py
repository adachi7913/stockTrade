import glob
import os
import sys
import time
from lib.tachibana_stock_api_base import TachibanaStockAPI
import logging
from datetime import datetime
from utils.logging_config import setup_logging, cleanup_old_logs

def main():
    # ロギング設定
    logger = setup_logging("tachibana")
    logger.info("立花証券APIテストを開始します")
    
    # tachibana_stock_api_base のロガーレベルを設定
    api_logger = logging.getLogger('lib.tachibana_stock_api_base')
    api_logger.setLevel(logging.WARNING)  # DEBUGやINFOレベルのログを抑制

    # コマンドライン引数から開始コードを取得
    start_code = sys.argv[1] if len(sys.argv) > 1 else None
    
    if start_code:
        logger.info(f"開始コード: {start_code}")
    
    try:
        # APIクライアントの初期化
        api = TachibanaStockAPI()
        
        # ログイン
        logger.info("立花証券APIにログインします")
        login_result = api.login()
        
        if login_result:
            logger.info("ログイン成功")
            
            # 銘柄情報の取得
            if start_code:
                stock_info = api.get_stock_info(start_code)
                logger.info(f"銘柄情報: {stock_info}")
            
            # ログアウト
            logger.info("ログアウトします")
            api.logout()
        else:
            logger.error("ログインに失敗しました")
    
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
    
    logger.info("立花証券APIテストを終了します")

def test_single_stock():
    """1銘柄のみを処理してインジケーター計算をテスト"""
    logger = setup_logging("tachibana")  # 既存のロギング設定を使用
    cleanup_old_logs("tachibana")
    
    try:
        api = TachibanaStockAPI(num_threads=1)
        api.execute_stock_price_retrieval(start_code="1301")  # 極洋を対象にテスト
    except Exception as e:
        logger.error(f"テスト実行中にエラーが発生しました: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
