import logging
import os
import glob
from datetime import datetime, timedelta

def setup_logging(log_type: str) -> logging.Logger:
    """
    ロギングの設定を行う
    
    Args:
        log_type (str): ログファイルの種類を示す文字列
        
    Returns:
        logging.Logger: 設定済みのロガーインスタンス
    """
    # 日付情報を取得
    today = datetime.now()
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.strftime("%d")
    
    # log/yyyy/mm/dd ディレクトリ構造を作成
    log_dir = os.path.join("log", year, month, day)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    current_time = datetime.now().strftime("%H%M%S")
    log_file = os.path.join(log_dir, f"{log_type}_{current_time}.log")
    
    logger = logging.getLogger(log_type)
    logger.setLevel(logging.INFO)
    
    # ハンドラーが既に存在する場合は削除
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # ファイルハンドラーの設定
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    logger.addHandler(file_handler)
    
    # コンソールハンドラーの設定
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    logger.addHandler(console_handler)
    
    # 古いログファイルのクリーンアップ
    cleanup_old_logs(log_type)
    
    return logger 

def cleanup_old_logs(log_type: str, days_to_keep: int = 7):
    """
    指定した日数よりも古いログファイルを削除する
    
    Args:
        log_type (str): ログファイルの種類を示す文字列
        days_to_keep (int): 保持する日数（デフォルト7日）
    """
    # 削除基準日
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    # 全てのログファイルを検索（yyyy/mm/dd構造対応）
    pattern = os.path.join("log", "**", f"*{log_type}*.log")
    log_files = glob.glob(pattern, recursive=True)
    
    for log_file in log_files:
        # ファイルのタイムスタンプを取得
        file_time = datetime.fromtimestamp(os.path.getmtime(log_file))
        
        # 基準日より古い場合は削除
        if file_time < cutoff_date:
            try:
                os.remove(log_file)
                print(f"古いログファイルを削除しました: {log_file}")
            except Exception as e:
                print(f"ログファイルの削除に失敗しました: {log_file} - {e}") 