import os
import sys
from pathlib import Path

# プロジェクトルートディレクトリをPythonパスに追加
project_root = str(Path(__file__).parent.parent.parent)
sys.path.append(project_root)

import logging
from browser_use.browser_use import BrowserUse
from repository.stock_repository import StockRepository
from lib.table_category import TableCategory
from Gemini.api_handler import ApiHandler
from models.evaluation_result import EvaluationResult
from lib.code_validator import validate_stock_code
from utils.logging_config import setup_logging
import json
from typing import Optional, Dict, List
import argparse
from lib.json_encoder import dumps as json_dumps

class AutoSellStock:
    def __init__(self, logger: logging.Logger, test_mode: bool = False):
        self.logger = logger
        self.test_mode = test_mode
        # テストモードの場合はブラウザ操作が不要なのでBrowserUseを初期化しない
        self.browser_use = None if test_mode else BrowserUse()
        self.stock_repository = StockRepository()
        self.api_handler = None

    def print_evaluation_summary(self, results: Dict[str, EvaluationResult]) -> None:
        """評価結果のサマリーを表示"""
        self.logger.info("\n評価結果サマリー:")
        for code, evaluation in results.items():
            self.logger.info(f"\n証券コード: {code}")
            self.logger.info(f"判断: {evaluation.decision}")
            self.logger.info(f"確信度: {evaluation.confidence_score}")
            self.logger.info(f"理由: {evaluation.reason}")
            self.logger.info(f"ストップロス: {evaluation.stop_loss}")
            self.logger.info(f"目標価格: {evaluation.target_price}")

    def run_evaluation(self) -> Optional[Dict[str, EvaluationResult]]:
        """
        保有証券の評価を実行
        
        Returns:
            Optional[Dict[str, EvaluationResult]]: 評価結果の辞書、失敗時はNone
        """
        self.logger.info("保有証券の評価を開始")
        
        # 1. 保有証券情報の取得
        holdings = self.get_holdings()
        if not holdings:
            self.logger.error("保有証券情報の取得に失敗しました")
            return None
        
        evaluation_results = {}
        
        # 2-4. 各保有証券について評価を実行
        for code, current_price in holdings.items():
            self.logger.info(f"証券コード {code} の評価を開始")
            
            # 過去の価格とインジケーターを取得
            historical_data = self.get_stock_data(code)
            if not historical_data:
                continue
            
            # 評価を実行
            evaluation = self.evaluate_holding_with_ai(code, current_price, historical_data)
            if evaluation:
                evaluation_results[code] = evaluation
                
                # 評価結果をデータベースに保存
                self.stock_repository.save_holding_evaluation(evaluation, is_test=self.test_mode)
        
        return evaluation_results

    def evaluate_entry(self, entry: Dict) -> EvaluationResult:
        """エントリー情報を評価し、売却判断を行う"""
        try:
            # 株価データの取得
            stock_data = self.stock_repository.get_stock_full_data_period(
                entry['code'],
                self.stock_repository.fetch_industry_name_prefix(entry['code'] + "0")
            )
            if not stock_data:
                self.logger.error(f"株価データの取得に失敗: {entry['code']}")
                return EvaluationResult(
                    code=entry['code'],
                    decision="HOLD",
                    confidence_score=0,
                    reason="株価データの取得に失敗",
                    stop_loss="NG",
                    target_price="NG"
                )

            # 現在価格の取得
            current_price = stock_data[-1]['close']
            entry_price = float(entry['entry_price'])
            profit_rate = ((current_price - entry_price) / entry_price) * 100

            # 損益率による判断
            if profit_rate <= -5.0:  # 5%以上の損失
                return EvaluationResult(
                    code=entry['code'],
                    decision="SELL",
                    confidence_score=800,
                    reason=f"損益率が-5%を下回りました（{profit_rate:.2f}%）",
                    stop_loss=str(current_price),
                    target_price="NG"
                )
            elif profit_rate >= 10.0:  # 10%以上の利益
                return EvaluationResult(
                    code=entry['code'],
                    decision="SELL",
                    confidence_score=700,
                    reason=f"利益率が10%を上回りました（{profit_rate:.2f}%）",
                    stop_loss=str(current_price),
                    target_price="NG"
                )

            # テクニカル指標による判断
            rsi = stock_data[-1]['rsi']
            macd = stock_data[-1]['macd']
            macd_signal = stock_data[-1]['macd_signal']

            if rsi > 70:  # 過買い
                return EvaluationResult(
                    code=entry['code'],
                    decision="SELL",
                    confidence_score=600,
                    reason=f"RSIが70を上回りました（{rsi:.2f}）",
                    stop_loss=str(current_price),
                    target_price="NG"
                )
            elif rsi < 30:  # 過売り
                return EvaluationResult(
                    code=entry['code'],
                    decision="HOLD",
                    confidence_score=500,
                    reason=f"RSIが30を下回りました（{rsi:.2f}）",
                    stop_loss="NG",
                    target_price="NG"
                )

            if macd < macd_signal:  # デッドクロス
                return EvaluationResult(
                    code=entry['code'],
                    decision="SELL",
                    confidence_score=500,
                    reason="MACDがシグナル線を下回りました",
                    stop_loss=str(current_price),
                    target_price="NG"
                )

            # デフォルトは保有継続
            return EvaluationResult(
                code=entry['code'],
                decision="HOLD",
                confidence_score=300,
                reason="売却条件を満たしていません",
                stop_loss="NG",
                target_price="NG"
            )

        except Exception as e:
            self.logger.error(f"評価中にエラーが発生: {e}")
            return EvaluationResult(
                code=entry['code'],
                decision="HOLD",
                confidence_score=0,
                reason=f"エラーが発生: {str(e)}",
                stop_loss="NG",
                target_price="NG"
            )

    def get_holdings(self) -> Optional[Dict[str, str]]:
        """
        entriesテーブルから保有証券の情報を取得
        
        Returns:
            Dict[str, str]: {証券コード: 現在価格} の形式、取得失敗時はNone
        """
        self.logger.info("保有証券情報の取得を開始")
        
        holdings = self.stock_repository.get_active_holdings(is_test=self.test_mode)
        
        if holdings is None:
            self.logger.error("保有証券情報の取得に失敗しました")
            return None
        
        if not holdings:
            self.logger.info("保有証券が見つかりません")
            return {}
        
        self.logger.info(f"取得した保有証券: {holdings}")
        return holdings

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

    def compare_and_update_evaluation(self, current: EvaluationResult, previous: Optional[Dict]) -> EvaluationResult:
        """
        現在の評価と前回の評価を比較し、必要に応じて更新
        
        Args:
            current (EvaluationResult): 現在の評価結果
            previous (Optional[Dict]): 前回の評価結果
            
        Returns:
            EvaluationResult: 更新された評価結果
        """
        if not previous:
            return current
            
        try:
            # ストップロス更新ロジック
            if current.stop_loss != "NG" and previous["stop_loss"] != "NG":
                current_stop_loss = float(current.stop_loss)
                previous_stop_loss = float(previous["stop_loss"])
                
                # 現在のストップロスが前回より高い場合（利益確保のため引き上げ）
                if current_stop_loss > previous_stop_loss:
                    current.stop_loss_update_reason = f"前回のストップロス({previous_stop_loss})から引き上げました"
                    self.logger.info(f"ストップロスを更新: {previous_stop_loss} -> {current_stop_loss}")
                # 現在のストップロスが前回より低い場合（損失拡大の可能性）
                elif current_stop_loss < previous_stop_loss:
                    # 前回のストップロスを維持するか判断
                    if current.decision == "HOLD" and current.confidence_score < 700:
                        current.stop_loss = previous["stop_loss"]
                        current.stop_loss_update_reason = "前回のストップロスを維持します"
                        self.logger.info(f"ストップロスを維持: {previous_stop_loss}")
            
            # 目標価格更新ロジック
            if current.target_price != "NG" and previous["target_price"] != "NG":
                current_target = float(current.target_price)
                previous_target = float(previous["target_price"])
                
                # 現在の目標価格が前回より高い場合（上昇トレンド強化）
                if current_target > previous_target:
                    current.target_update_reason = f"前回の目標価格({previous_target})から引き上げました"
                    self.logger.info(f"目標価格を更新: {previous_target} -> {current_target}")
                # 現在の目標価格が前回より低い場合（上昇トレンド弱化）
                elif current_target < previous_target:
                    # 前回の目標価格を維持するか判断
                    if current.decision == "HOLD" and current.confidence_score < 700:
                        current.target_price = previous["target_price"]
                        current.target_update_reason = "前回の目標価格を維持します"
                        self.logger.info(f"目標価格を維持: {previous_target}")
            
            return current
            
        except Exception as e:
            self.logger.error(f"評価結果の比較・更新中にエラーが発生: {e}")
            return current

    def evaluate_holding_with_ai(self, code: str, current_price: str, historical_data: List[dict]) -> Optional[EvaluationResult]:
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
            # 前回の評価結果を取得
            previous_evaluation = self.stock_repository.get_previous_evaluation(code)
            previous_evaluation_json = json_dumps(previous_evaluation, ensure_ascii=False) if previous_evaluation else "なし"
            
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
            6. 前回評価時からの変化点分析

            【提供データ】
            証券コード: {code}
            現在価格: {current_price}
            過去データ: {json_dumps(historical_data, ensure_ascii=False)}
            前回の評価結果: {previous_evaluation_json}

            【出力形式】（以下のJSON形式を厳守し、その他の内容は含めないでください）
            {{
                "decision": "HOLD" or "SELL",
                "confidence_score": <0〜1000の整数>,
                "reason": "判断の理由",
                "stop_loss": "ストップロス価格（金額のみ）" or "NG",
                "target_price": "目標価格（金額のみ）" or "NG",
                "stop_loss_update_reason": "ストップロス更新の理由" or null,
                "target_update_reason": "目標価格更新の理由" or null
            }}
            """

            # GeminiAPIにリクエスト送信
            if not self.api_handler:
                self.api_handler = ApiHandler(historical_data, prompt)
            response = self.api_handler.call_gemini_api()
            
            if response:
                try:
                    evaluation_dict = json.loads(response) if isinstance(response, str) else response
                    self.logger.info(f"評価結果: {evaluation_dict}")
                    # current_priceを評価結果に追加
                    evaluation_dict['close'] = current_price
                    evaluation_result = EvaluationResult.from_dict(code, evaluation_dict)
                    
                    # 前回の評価と比較・更新
                    updated_evaluation = self.compare_and_update_evaluation(evaluation_result, previous_evaluation)
                    return updated_evaluation
                    
                except json.JSONDecodeError as e:
                    self.logger.error(f"評価結果のパースに失敗: {e}")
                    return None

            return None

        except Exception as e:
            self.logger.error(f"評価処理中にエラーが発生: {e}")
            return None

def main():
    """メイン処理"""
    # ロガーの設定
    logger = setup_logging("auto_sell_stock")
    
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='自動売却スクリプト')
    parser.add_argument('--test', action='store_true', help='テストモードで実行')
    parser.add_argument('--force-sell', action='store_true', help='強制売却モードで実行')
    parser.add_argument('--debug', action='store_true', help='デバッグモードで実行')
    args = parser.parse_args()

    try:
        # AutoSellStockインスタンスの作成
        auto_sell = AutoSellStock(logger, test_mode=args.test)
        
        # 保有証券の評価を実行
        evaluation_results = auto_sell.run_evaluation()
        if not evaluation_results:
            logger.error("評価結果の取得に失敗しました")
            return

        # 評価結果のサマリーを表示
        auto_sell.print_evaluation_summary(evaluation_results)

        # 売却判断の実行
        sell_candidates = []
        for code, evaluation in evaluation_results.items():
            if evaluation.decision == "SELL" and evaluation.confidence_score >= 500:
                sell_candidates.append((code, evaluation))

        if not sell_candidates:
            logger.info("売却候補はありません")
            return

        # 売却候補の表示
        logger.info("\n売却候補:")
        for code, evaluation in sell_candidates:
            logger.info(f"証券コード: {code}")
            logger.info(f"確信度: {evaluation.confidence_score}")
            logger.info(f"理由: {evaluation.reason}")
            logger.info(f"ストップロス: {evaluation.stop_loss}")
            logger.info(f"目標価格: {evaluation.target_price}")

        # テストモードの場合は売却を実行しない
        if args.test:
            logger.info("テストモードのため、売却は実行されません")
            return

        # 強制売却モードの場合は確認なしで売却を実行
        if args.force_sell:
            logger.info("強制売却モードで実行します")
            for code, evaluation in sell_candidates:
                auto_sell.execute_sell(code, evaluation)
            return

        # 売却の確認
        for code, evaluation in sell_candidates:
            if input(f"\n{code}を売却しますか？ (y/n): ").lower() == 'y':
                auto_sell.execute_sell(code, evaluation)

    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise

if __name__ == "__main__":
    main() 