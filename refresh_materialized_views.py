import os
import sys
import logging
import datetime
import glob
import time
from dotenv import load_dotenv

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from repository.materialized_view_repository import MaterializedViewRepository
from utils.date_util import is_holiday
from utils.logging_config import setup_logging, cleanup_old_logs

def main():
    # .envファイルの読み込み
    load_dotenv()
    
    # ロギング設定
    log_type = "refresh_views"
    logger = setup_logging(log_type)
    logger.info("マテリアライズドビューの更新処理を開始します")
    
    # 休日チェック
    today = datetime.datetime.now().date()
    if is_holiday(today):
        logger.info(f"{today}は休日のため、処理をスキップします")
        return
    
    try:
        # マテリアライズドビュー更新処理を実行
        repo = MaterializedViewRepository()
        start_time = time.time()
        
        # すべてのマテリアライズドビューを更新
        logger.info("すべてのマテリアライズドビューの更新を開始します")
        updated_views = repo.refresh_all_materialized_views()
        
        if updated_views:
            logger.info(f"更新されたビュー: {', '.join(updated_views)}")
        else:
            logger.warning("更新されたビューはありませんでした")
        
        # 処理時間を計算
        elapsed_time = time.time() - start_time
        logger.info(f"処理時間: {elapsed_time:.2f}秒")
        
    except Exception as e:
        logger.error(f"マテリアライズドビューの更新処理中にエラーが発生しました: {e}")
    
    logger.info("マテリアライズドビューの更新処理が完了しました")

if __name__ == "__main__":
    main()
