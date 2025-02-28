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
        
    def calculate_latest_indicators(self, stock_data: List[Dict], code: str, industry_name: str, latest_days: int = 5) -> bool:
        """
        デイリー処理用の直近期間のインジケーター計算を行います
        
        Args:
            stock_data (List[Dict]): 株価データのリスト
            code (str): 株価コード
            industry_name (str): 業種名
            latest_days (int): 保存する最新のインジケーター日数（デフォルト: 5日）
            
        Returns:
            bool: 保存成功でTrue
        """
        try:
            if not stock_data:
                self.logger.warning(f"株価データが空のため、インジケーター計算をスキップします: code={code}")
                return False

            # インジケーター計算に必要な最小データ数をチェック
            min_required_records = 78  # 一目均衡表の先行B = 52+26日
            if len(stock_data) < min_required_records:
                self.logger.warning(f"データ不足のため、インジケーター計算をスキップします: code={code}, データ数={len(stock_data)}, 必要数={min_required_records}")
                return False

            # 日付でソート（古い順）
            stock_data = sorted(stock_data, key=lambda x: x['date'])
            self.logger.info(f"銘柄コード {code} のインジケーター計算（データ期間: {stock_data[0]['date']}～{stock_data[-1]['date']}）")

            # インジケーターを計算
            calculator = IndicatorCalculator(stock_data)
            indicators = calculator.calculate_indicators()
            
            if not indicators:
                self.logger.warning(f"インジケーター計算結果が空です: code={code}")
                return False
                
            # 直近の指定日数分のみを保存
            if len(indicators) > latest_days:
                indicators_to_save = indicators[-latest_days:]
                self.logger.info(f"銘柄コード {code} の直近 {latest_days}日分のインジケーターのみを保存します（全期間: {len(indicators)}日）")
            else:
                indicators_to_save = indicators
                self.logger.info(f"銘柄コード {code} の全インジケーターを保存します（全期間: {len(indicators)}日）")
            
            # 日付フォーマットの検証と修正
            validated_indicators = []
            for indicator in indicators_to_save:
                # 日付フォーマットチェック
                date_str = indicator.get('date')
                if not date_str:
                    self.logger.warning(f"インジケーターに日付がありません: {indicator}")
                    continue
                
                # 日付フォーマットの検証と修正
                try:
                    # 既に正しいフォーマット（YYYY-MM-DD）かチェック
                    if '-' in date_str and len(date_str.split('-')) == 3:
                        # 既に正しいフォーマット
                        pass
                    # YYYYMMDDの形式かチェック
                    elif len(date_str) == 8 and date_str.isdigit():
                        # YYYYMMDDをYYYY-MM-DDに変換
                        indicator['date'] = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                    else:
                        # その他の場合はエラーログを出力して次へ
                        self.logger.warning(f"不正な日付フォーマットです: {date_str}")
                        continue
                except Exception as e:
                    self.logger.error(f"日付フォーマット変換エラー: {str(e)}, date={date_str}")
                    continue
                
                validated_indicators.append(indicator)
            
            if not validated_indicators:
                self.logger.warning(f"検証後のインジケーターデータが空です: code={code}")
                return False
            
            self.logger.info(f"日付フォーマット検証後のデータ件数: {len(validated_indicators)}件")
            
            # 検証済みデータをDBに保存
            success = self.stock_repository.insert_indicator_data(validated_indicators, code, industry_name)
            
            if success:
                self.logger.info(f"銘柄コード {code} の直近インジケーター計算・保存が完了しました（保存件数: {len(validated_indicators)}件）")
            
            return success
            
        except Exception as e:
            self.logger.error(f"直近インジケーター計算・保存エラー: code={code}, error={str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False 