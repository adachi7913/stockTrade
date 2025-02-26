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

def setup_logging(log_type):
    today = datetime.datetime.now()
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.strftime("%d")
    log_dir = os.path.join("log", year, month)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    # ファイル名は dd_refresh_views.log の形式
    log_file = os.path.join(log_dir, f"{day}_{log_type}.log")
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
    # ログファイルパターン: /log/**/ *_[refresh_views].log
    pattern = os.path.join("log", "**", f"*_{log_type}.log")
    for file in glob.glob(pattern, recursive=True):
        if os.path.isfile(file) and now - os.path.getmtime(file) > 7 * 24 * 3600:
            os.remove(file)

def main():
    """マテリアライズドビューを更新する主処理"""
    # 環境変数を確実に読み込む
    load_dotenv(override=True)
    
    log_type = "refresh_views"
    cleanup_old_logs(log_type)
    logger = setup_logging(log_type)
    logger.info("マテリアライズドビュー更新処理を開始します")
    
    # 休日判定
    if is_holiday():
        logger.info("本日は休日のため、処理を終了します")
        sys.exit(0)
    
    try:
        # リポジトリのインスタンス化
        repo = MaterializedViewRepository()
        
        # 更新前のマテリアライズドビュー一覧を取得
        views = repo.get_all_materialized_views()
        logger.info(f"更新対象のマテリアライズドビュー: {[view['matviewname'] for view in views]}")
        
        # すべてのマテリアライズドビューを更新
        success = repo.refresh_all_views()
        
        if success:
            logger.info("すべてのマテリアライズドビューの更新が完了しました")
            
            # 更新後の各ビューの状態を確認
            for view in views:
                view_name = view['matviewname']
                last_refresh = repo.get_view_last_refresh_time(view_name)
                logger.info(f"ビュー {view_name} の最終更新時間: {last_refresh}")
        else:
            logger.error("マテリアライズドビューの更新に失敗しました")
        
    except Exception as e:
        logger.error(f"予期しないエラーが発生しました: {e}", exc_info=True)
    finally:
        # リソースの解放
        if 'repo' in locals():
            repo.close()
        
    logger.info("マテリアライズドビュー更新処理を終了します")

if __name__ == "__main__":
    main()
