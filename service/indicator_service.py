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
        # 業種名キャッシュ
        self.industry_cache = {}

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
        # キャッシュにあればそれを返す
        if code in self.industry_cache:
            return self.industry_cache[code]
            
        try:
            industry_name = self.stock_repository.fetch_industry_name_prefix(code)
            if industry_name:
                # キャッシュに保存
                self.industry_cache[code] = industry_name
            return industry_name
        except Exception as e:
            self.logger.error(f"業種名取得エラー: {e}")
            return None

    def preload_industry_names(self, codes: List[str]) -> None:
        """
        複数の株価コードの業種名を事前にロードします
        
        Args:
            codes (List[str]): 株価コードのリスト
        """
        try:
            self.stock_repository.preload_industry_names(codes)
        except Exception as e:
            self.logger.error(f"業種名の事前ロードエラー: {e}")

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
            
    def calculate_and_save_indicators_batch(self, batch_codes: List[str]) -> bool:
        """
        複数の銘柄のインジケーターを一括で計算・保存します
        
        Args:
            batch_codes (List[str]): 株価コードのリスト
            
        Returns:
            bool: 保存成功でTrue
        """
        if not batch_codes:
            return True
            
        # 業種名を事前にロード
        self.preload_industry_names(batch_codes)
        
        # 業種ごとのバッチデータを格納する辞書
        industry_batches = {}
        
        for code in batch_codes:
            try:
                # 業種名を取得
                industry_name = self.get_industry_name(code)
                if not industry_name:
                    self.logger.warning(f"業種名の取得に失敗しました: code={code}")
                    continue
                
                # 5桁かつ末尾が0の場合、末尾の0を取り除く
                stock_code = code[:-1] if len(code) == 5 and code.endswith('0') else code
                
                # 株価データを取得
                stock_data = self.get_stock_price_data(stock_code, industry_name)
                if not stock_data:
                    self.logger.warning(f"株価データの取得に失敗しました: code={code}")
                    continue
                
                # インジケーター計算に必要な最小データ数をチェック
                min_required_records = 78
                if len(stock_data) < min_required_records:
                    self.logger.warning(f"データ不足のため、インジケーター計算をスキップします: code={code}, データ数={len(stock_data)}")
                    continue
                
                # インジケーターを計算
                calculator = IndicatorCalculator(stock_data)
                indicators = calculator.calculate_indicators()
                
                if not indicators:
                    self.logger.warning(f"インジケーター計算結果が空です: code={code}")
                    continue
                
                # 業種ごとのバッチに追加
                if industry_name not in industry_batches:
                    industry_batches[industry_name] = []
                    
                industry_batches[industry_name].append({
                    'code': stock_code,
                    'indicators': indicators
                })
                
            except Exception as e:
                self.logger.error(f"銘柄処理中のエラー: code={code}, error={str(e)}")
                continue
        
        # 業種ごとにバルクインサート
        success = True
        for industry_name, batch_data in industry_batches.items():
            try:
                if not self.stock_repository.bulk_insert_indicator_data(batch_data, industry_name):
                    self.logger.warning(f"業種 {industry_name} のバルクインサート失敗")
                    success = False
            except Exception as e:
                self.logger.error(f"バルクインサートエラー: industry={industry_name}, error={str(e)}")
                success = False
                
        return success 