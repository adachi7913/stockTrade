import os
import psycopg2
from dotenv import load_dotenv
import logging
from typing import Optional

class BaseRepository:
    def __init__(self):
        """
        データベースリポジトリの基底クラス
        """
        self.logger = logging.getLogger(__name__)
        self.conn = None
        self.cur = None
        self.connect()

    def connect(self):
        """
        データベースに接続します
        """
        try:
            load_dotenv()
            self.conn = self.get_connection()
            self.cur = self.conn.cursor()
        except Exception as e:
            self.logger.error(f"データベース接続エラー: {e}")
            raise

    def get_connection(self):
        """
        データベース接続を取得します
        
        Returns:
            psycopg2.extensions.connection: データベース接続オブジェクト
        """
        try:
            return psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5432"),
                database=os.getenv("DB_NAME", "stock_trade"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "postgres")
            )
        except Exception as e:
            self.logger.error(f"データベース接続取得エラー: {e}")
            raise

    def close(self):
        """
        データベース接続を閉じます
        """
        try:
            if self.cur:
                self.cur.close()
            if self.conn and not self.conn.closed:
                self.conn.close()
        except Exception as e:
            self.logger.error(f"データベース切断エラー: {e}")

    def __del__(self):
        """
        デストラクタ：リソースの解放を確実に行います
        """
        self.close() 