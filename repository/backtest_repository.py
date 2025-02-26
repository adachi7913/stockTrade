import os
import psycopg
import pandas as pd
from dotenv import load_dotenv
from repository.base_repository import BaseRepository
from repository.stock_repository import StockRepository
import logging
from sqlalchemy import create_engine
import urllib.parse

load_dotenv()

class BacktestRepository(BaseRepository):
    def __init__(self):
        super().__init__()
        self.stock_repository = StockRepository()
        self.logger = logging.getLogger(__name__)
        # SQLAlchemyエンジンを初期化
        self.engine = self._create_sqlalchemy_engine()

    def _create_sqlalchemy_engine(self):
        """
        SQLAlchemyエンジンを作成します
        
        Returns:
            sqlalchemy.engine.Engine: SQLAlchemyエンジンオブジェクト
        """
        try:
            # 環境変数から接続情報を取得
            host = os.getenv("DB_HOST", "localhost")
            port = os.getenv("DB_PORT", "5432")
            database = os.getenv("DB_NAME", "stock_trade")
            user = os.getenv("DB_USER", "postgres")
            password = os.getenv("DB_PASSWORD", "postgres")
            
            # パスワードをURLエンコード
            encoded_password = urllib.parse.quote_plus(password)
            
            # PostgreSQL接続文字列を作成
            connection_string = f"postgresql://{user}:{encoded_password}@{host}:{port}/{database}"
            
            # エンジンを作成して返す
            return create_engine(connection_string)
        except Exception as e:
            self.logger.error(f"SQLAlchemyエンジン作成エラー: {e}")
            raise

    def fetch_historical_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        指定された銘柄の株価データを取得します。
        
        Args:
            symbol (str): 証券コード
            start_date (str): 開始日（YYYY-MM-DD形式）
            end_date (str): 終了日（YYYY-MM-DD形式）
            
        Returns:
            pd.DataFrame: 株価データ
        """
        try:
            # 業種名のプレフィックスを取得
            # 4桁の場合のみ末尾に0を追加
            companies_code = symbol
            if len(symbol) == 4:
                companies_code = symbol + "0"
            
            industry_name = self.stock_repository.fetch_industry_name_prefix(companies_code)
            if not industry_name:
                self.logger.error(f"業種名が取得できません: {symbol}")
                return pd.DataFrame()

            # 業種別テーブルから株価データを取得
            query = """
                SELECT date, open, high, low, close, volume 
                FROM {}_price
                WHERE code = %s AND date BETWEEN %s AND %s
                ORDER BY date ASC;
            """.format(industry_name)

            # SQLAlchemyエンジンを使用してデータを取得
            df = pd.read_sql_query(
                sql=query, 
                con=self.engine, 
                params=(symbol, start_date, end_date)
            )
            return df

        except Exception as e:
            self.logger.error(f"株価データ取得エラー: {e}")
            return pd.DataFrame()

    def close(self):
        """
        データベース接続をクローズします。
        """
        super().close()
        if hasattr(self, 'stock_repository'):
            self.stock_repository.close()
        # SQLAlchemyエンジンの接続をクローズ
        if hasattr(self, 'engine'):
            self.engine.dispose()
