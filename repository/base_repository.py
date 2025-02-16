import os
import psycopg
from dotenv import load_dotenv
import logging
from typing import Optional

class BaseRepository:
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        load_dotenv()
        
        try:
            self.conn = psycopg.connect(
                host=os.environ.get("DB_HOST"),
                dbname=os.environ.get("DB_NAME"),
                user=os.environ.get("DB_USER"),
                password=os.environ.get("DB_PASSWORD")
            )
            self.cur = self.conn.cursor()
        except Exception as e:
            self.logger.error(f"データベース接続エラー: {e}")
            raise

    def close(self):
        """データベース接続のクローズ"""
        try:
            if hasattr(self, 'cur') and not self.cur.closed:
                self.cur.close()
            if hasattr(self, 'conn') and not self.conn.closed:
                self.conn.close()
        except Exception as e:
            self.logger.error(f"DB接続クローズエラー: {e}") 