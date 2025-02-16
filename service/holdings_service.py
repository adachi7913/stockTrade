import json
import logging
from typing import Dict, List, Optional

from browser_use.browser_use import BrowserUse
from repository.stock_repository import StockRepository
from lib.table_category import TableCategory
from Gemini.api_handler import ApiHandler
from models.evaluation_result import EvaluationResult

class HoldingsService:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.browser_use = BrowserUse()
        self.stock_dao = StockRepository()

    def get_holdings(self) -> Optional[Dict[str, str]]:
        """
        証券口座から保有証券の情報を取得
        
        Returns:
            Dict[str, str]: {証券コード: 現在価格} の形式、取得失敗時はNone
        """
        self.logger.info("保有証券情報の取得を開始")
        prompt = self.browser_use._get_prompt()
        response = self.browser_use.run(prompt)
        
        if response:
            try:
                holdings = json.loads(response) if isinstance(response, str) else response
                self.logger.info(f"取得した保有証券: {holdings}")
                return holdings
            except json.JSONDecodeError as e:
                self.logger.error(f"保有証券情報のパースに失敗: {e}")
                return None
        return None

    def get_stock_data(self, code: str) -> Optional[List[dict]]:
        """
        証券コードから過去の価格とインジケーターを取得
        
        Args:
            code (str): 証券コード
            
        Returns:
            List[dict]: 株価データとインジケーターのリスト、取得失敗時はNone
        """
        try:
            # 企業情報を取得
            company_info = self.stock_dao.fetch_company_info(code + "0")
            if not company_info:
                self.logger.error(f"企業情報が見つかりません: {code}")
                return None

            # 業種名から対応するテーブル接頭辞を取得
            industry_name = TableCategory.get_table_prefix(company_info[10])
            
            # 過去の価格とインジケーターを取得
            stock_data = self.stock_dao.get_stock_full_data_period(code, industry_name)
            if not stock_data:
                self.logger.error(f"株価データが見つかりません: {code}")
                return None

            return stock_data

        except Exception as e:
            self.logger.error(f"株価データ取得中にエラーが発生: {e}")
            return None

    def evaluate_holding(self, code: str, current_price: str, historical_data: List[dict]) -> Optional[EvaluationResult]:
        """
        GeminiAPIを使用して保有株式を評価
        
        Args:
            code (str): 証券コード
            current_price (str): 現在価格
            historical_data (List[dict]): 過去の価格とインジケーターのデータ
            
        Returns:
            Optional[EvaluationResult]: 評価結果、評価失敗時はNone
        """
        try:
            # TODO: エントリー時の情報をDBから取得する処理を実装

            # Gemini APIへのプロンプトを構築
            prompt = f"""
            【前提】
            英語で思考し、**日本語のみ**で回答してください。
            あなたは優秀な個人投資家かつトレード戦略構築のエキスパートです。
            保有中の株式について、過去のデータや各種テクニカル指標をもとに、保有継続の判断を行ってください。

            【評価基準】
            1. トレンド分析（一目均衡表、MACD）
            2. モメンタム（RSI、ストキャスティクス）
            3. ボラティリティ（ボリンジャーバンド、ATR）
            4. 出来高分析
            5. 現在の株価位置

            【提供データ】
            証券コード: {code}
            現在価格: {current_price}
            過去データ: {json.dumps(historical_data, ensure_ascii=False)}

            【出力形式】（以下のJSON形式を厳守し、その他の内容は含めないでください）
            {{
                "decision": "HOLD" or "SELL",
                "confidence_score": <0〜1000の整数>,
                "reason": "判断の理由",
                "stop_loss": "ストップロス価格（金額のみ）" or "NG",
                "target_price": "目標価格（金額のみ）" or "NG"
            }}
            """

            # GeminiAPIにリクエスト送信
            api_handler = ApiHandler(historical_data)
            response = api_handler.call_gemini_api()
            
            if response:
                try:
                    evaluation_dict = json.loads(response) if isinstance(response, str) else response
                    self.logger.info(f"評価結果: {evaluation_dict}")
                    return EvaluationResult.from_dict(code, evaluation_dict)
                except json.JSONDecodeError as e:
                    self.logger.error(f"評価結果のパースに失敗: {e}")
                    return None

            return None

        except Exception as e:
            self.logger.error(f"評価処理中にエラーが発生: {e}")
            return None 