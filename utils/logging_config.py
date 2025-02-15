import logging
import os
from datetime import datetime

def setup_logging(log_type: str) -> logging.Logger:
    """
    ロギングの設定を行う
    
    Args:
        log_type (str): ログファイルの種類を示す文字列
        
    Returns:
        logging.Logger: 設定済みのロガーインスタンス
    """
    log_dir = "log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
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
    
    return logger 