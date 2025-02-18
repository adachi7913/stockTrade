import json
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from browser_use.browser_use import BrowserUse
from repository.stock_repository import StockRepository
from lib.table_category import TableCategory
from lib.code_validator import validate_stock_code
from Gemini.api_handler import ApiHandler
from typing import Dict, Optional

from models.evaluation_result import EvaluationResult
from service.holdings_service import HoldingsService
from utils.logging_config import setup_logging

# .envファイルをロード
load_dotenv()

# ロギングの設定
def setup_logging():
    log_dir = "log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"holdings_evaluation_{current_time}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

class HoldingsEvaluator:
    def __init__(self):
        self.logger = setup_logging()
        self.browser_test = BrowserUse()
        self.stock_repository = StockRepository()

    def get_holdings(self):
        """
        証券口座から保有証券の情報を取得
        """
        self.logger.info("保有証券情報の取得を開始")
        prompt = self.browser_test._get_prompt()
        response = self.browser_test.run(prompt)
        
        if response:
            try:
                holdings = json.loads(response) if isinstance(response, str) else response
                self.logger.info(f"取得した保有証券: {holdings}")
                return holdings
            except json.JSONDecodeError as e:
                self.logger.error(f"保有証券情報のパースに失敗: {e}")
                return None
        return None

    def get_stock_data(self, code):
        """
        証券コードから過去の価格とインジケーターを取得
        """
        try:
            # 企業情報を取得
            industry_name = self.stock_repository.fetch_industry_name_prefix(code + "0")
            if not industry_name:
                self.logger.error(f"企業情報が見つかりません: {code}")
                return None
            
            # 銘柄コードのバリデーション
            validated_code = validate_stock_code(code)
            
            # 過去の価格とインジケーターを取得
            stock_data = self.stock_repository.get_stock_full_data_period(validated_code, industry_name)
            if not stock_data:
                self.logger.error(f"株価データが見つかりません: {code}")
                return None

            return stock_data

        except Exception as e:
            self.logger.error(f"株価データ取得中にエラーが発生: {e}")
            return None

    def evaluate_holding(self, code, current_price, historical_data):
        """
        GeminiAPIを使用して保有株式を評価
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
                    evaluation = json.loads(response) if isinstance(response, str) else response
                    self.logger.info(f"評価結果: {evaluation}")
                    return evaluation
                except json.JSONDecodeError as e:
                    self.logger.error(f"評価結果のパースに失敗: {e}")
                    return None

            return None

        except Exception as e:
            self.logger.error(f"評価処理中にエラーが発生: {e}")
            return None

    def run_evaluation(self):
        """
        保有証券の評価を実行
        """
        self.logger.info("保有証券の評価を開始")
        
        # 1. 保有証券情報の取得
        holdings = self.get_holdings()
        if not holdings:
            self.logger.error("保有証券情報の取得に失敗しました")
            return
        
        evaluation_results = {}
        
        # 2-4. 各保有証券について評価を実行
        for code, current_price in holdings.items():
            self.logger.info(f"証券コード {code} の評価を開始")
            
            # 過去の価格とインジケーターを取得
            historical_data = self.get_stock_data(code)
            if not historical_data:
                continue
            
            # 評価を実行
            evaluation = self.evaluate_holding(code, current_price, historical_data)
            if evaluation:
                evaluation_results[code] = evaluation
        
        return evaluation_results

def print_evaluation_summary(results: Dict[str, EvaluationResult]) -> None:
    """評価結果のサマリーを表示"""
    print("\n評価結果サマリー:")
    for code, evaluation in results.items():
        print(f"\n証券コード: {code}")
        print(f"判断: {evaluation.decision}")
        print(f"確信度: {evaluation.confidence_score}")
        print(f"理由: {evaluation.reason}")
        print(f"ストップロス: {evaluation.stop_loss}")
        print(f"目標価格: {evaluation.target_price}")

def run_evaluation() -> Optional[Dict[str, EvaluationResult]]:
    """
    保有証券の評価を実行
    
    Returns:
        Optional[Dict[str, EvaluationResult]]: 評価結果の辞書、失敗時はNone
    """
    logger = setup_logging("holdings_evaluation")
    holdings_service = HoldingsService(logger)
    
    # 1. 保有証券情報の取得
    holdings = holdings_service.get_holdings()
    if not holdings:
        logger.error("保有証券情報の取得に失敗しました")
        return None
    
    evaluation_results = {}
    
    # 2-4. 各保有証券について評価を実行
    for code, current_price in holdings.items():
        logger.info(f"証券コード {code} の評価を開始")
        
        # 過去の価格とインジケーターを取得
        historical_data = holdings_service.get_stock_data(code)
        if not historical_data:
            continue
        
        # 評価を実行
        evaluation = holdings_service.evaluate_holding(code, current_price, historical_data)
        if evaluation:
            evaluation_results[code] = evaluation
    
    return evaluation_results

if __name__ == "__main__":
    results = run_evaluation()
    
    if results:
        print_evaluation_summary(results)
    else:
        print("評価結果の取得に失敗しました。ログを確認してください。") 