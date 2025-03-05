import os
import sys
import datetime
from pathlib import Path

# プロジェクトルートディレクトリをPythonパスに追加
project_root = str(Path(__file__).parent.parent.parent)
sys.path.append(project_root)

from utils.logging_config import setup_logging
from utils.date_util import is_holiday
from repository.materialized_view_repository import MaterializedViewRepository

def main():
    """
    マテリアライズドビューの更新を実行するメイン関数
    """
    log_type = "refresh_materialized_views"
    logger = setup_logging(log_type)
    logger.info("マテリアライズドビューの更新処理を開始します")
    
    # 休日チェック
    if is_holiday():
        today = datetime.datetime.now().date()
        logger.info(f"{today}は休日のため、処理をスキップします")
        return
    
    try:
        # マテリアライズドビュー更新処理を実行
        repo = MaterializedViewRepository()
        if repo.refresh_all_views():
            logger.info("マテリアライズドビューの更新が正常に完了しました")
        else:
            logger.error("マテリアライズドビューの更新に失敗しました")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"マテリアライズドビューの更新処理中にエラーが発生しました: {e}")
        sys.exit(1)
    finally:
        logger.info("マテリアライズドビューの更新処理が完了しました")

if __name__ == "__main__":
    main()
