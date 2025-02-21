from typing import List, Dict, Optional
import logging
from repository.stock_repository import StockRepository
from lib.indicator_calculator import IndicatorCalculator

class IndicatorService:
    def __init__(self, stock_repository: StockRepository):
        """
        株価インジケーター計算を行うサービスクラス
        
        Args:
            stock_repository (StockRepository): 株価データリポジトリ
        """
        self.stock_repository = stock_repository
        self.logger = logging.getLogger(__name__)

    def get_all_stock_codes(self) -> List[str]:
        """
        DBに格納されている全ての株価コードを取得します
        
        Returns:
            List[str]: 株価コードのリスト
        """
        try:
            return self.stock_repository.fetch_company_code_list()
        except Exception as e:
            self.logger.error(f"株価コード取得エラー: {e}")
            return []

    def get_industry_name(self, code: str) -> Optional[str]:
        """
        指定された株価コードの業種名を取得します
        
        Args:
            code (str): 株価コード
            
        Returns:
            Optional[str]: 業種名、取得失敗時はNone
        """
        try:
            return self.stock_repository.fetch_industry_name_prefix(code)
        except Exception as e:
            self.logger.error(f"業種名取得エラー: {e}")
            return None

    def get_stock_price_data(self, code: str, industry_name: str) -> List[Dict]:
        """
        指定された株価コードと業種名から株価データを取得します
        
        Args:
            code (str): 株価コード
            industry_name (str): 業種名
            
        Returns:
            List[Dict]: 株価データのリスト
        """
        try:
            return self.stock_repository.get_stock_price_only(code, industry_name)
        except Exception as e:
            self.logger.error(f"株価データ取得エラー: {e}")
            return []

    def calculate_and_save_indicators(self, stock_data: List[Dict], code: str, industry_name: str) -> bool:
        """
        株価データからインジケーターを計算し、DBに保存します
        
        Args:
            stock_data (List[Dict]): 株価データのリスト
            code (str): 株価コード
            industry_name (str): 業種名
            
        Returns:
            bool: 保存成功でTrue
        """
        try:
            if not stock_data:
                self.logger.warning(f"株価データが空のため、インジケーター計算をスキップします: code={code}")
                return False

            # インジケーター計算に必要な最小データ数をチェック
            min_required_records = 78
            if len(stock_data) < min_required_records:
                self.logger.warning(f"データ不足のため、インジケーター計算をスキップします: code={code}, データ数={len(stock_data)}")
                return False

            calculator = IndicatorCalculator(stock_data)
            indicators = calculator.calculate_indicators()
            
            if not indicators:
                self.logger.warning(f"インジケーター計算結果が空です: code={code}")
                return False

            return self.stock_repository.insert_indicator_data(indicators, code, industry_name)
            
        except Exception as e:
            self.logger.error(f"インジケーター計算・保存エラー: code={code}, error={str(e)}")
            return False 