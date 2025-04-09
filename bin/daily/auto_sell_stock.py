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
        for code, holding_info in holdings.items(): # holdings now includes position
            self.logger.info(f"証券コード {code} の評価を開始")
            
            # 過去の価格とインジケーターを取得
            historical_data = self.get_stock_data(code)
            if not historical_data:
                continue
            
            # 評価を実行
            evaluation = self.evaluate_holding_with_ai(code, holding_info['current_price'], holding_info['position'], historical_data) # Pass position
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

    def get_holdings(self) -> Optional[Dict[str, Dict[str, str]]]: # Return type updated
        """
        entriesテーブルから保有証券の情報を取得 (position含む)
        
        Returns:
            Dict[str, Dict[str, str]]: {証券コード: {'current_price': 価格, 'position': ポジション}} の形式、取得失敗時はNone
        """
        self.logger.info("保有証券情報の取得を開始")
        
        # positionも取得するように修正が必要 (StockRepository側)
        holdings = self.stock_repository.get_active_holdings(is_test=self.test_mode) 
        
        if holdings is None:
            self.logger.error("保有証券情報の取得に失敗しました")
            return None
        
        if not holdings:
            self.logger.info("保有証券が見つかりません")
            return {}
        
        self.logger.info(f"取得した保有証券 (ポジション含む): {holdings}")
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

    def evaluate_holding_with_ai(self, code: str, current_price: str, position: str, historical_data: List[dict]) -> Optional[EvaluationResult]:
        """
        GeminiAPIを使用して保有株式を評価
        
        Args:
            code (str): 証券コード
            current_price (str): 現在価格
            position (str): ポジション
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
            **日本語のみ**で回答してください。
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
            ポジション: {position}
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

            # 各評価ごとに新しいAPIハンドラを作成するように修正
            self.api_handler = ApiHandler(historical_data, prompt)
            response = self.api_handler.call_gemini_api()
            self.logger.info(f"response: {response}")
            
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

    def execute_test_sell(self, code: str, evaluation: EvaluationResult) -> None:
        """
        テストモードでの売却処理を実行
        
        Args:
            code (str): 証券コード
            evaluation (EvaluationResult): 評価結果
        """
        try:
            self.logger.info(f"テストモードで {code} の売却シミュレーションを実行")
            
            # 1. entriesテーブルからエントリー情報を取得
            entry = self.stock_repository.get_entry_by_code(code, is_test=True)
            if not entry:
                self.logger.error(f"エントリー情報の取得に失敗: {code}")
                return
                
            # 2. 損益を算出
            entry_price = float(entry['entry_price'])
            current_price = float(evaluation.close)
            quantity = int(entry['quantity'])
            
            profit_loss = int((current_price - entry_price) * quantity)
            profit_rate = ((current_price / entry_price) - 1) * 100
            
            # 約定代金を計算
            transaction_amount = current_price * quantity
            
            # 手数料計算
            fee = self.calculate_fee(transaction_amount)
            
            # 3. trade_resultsテーブルに売却結果を格納
            trade_result = {
                'trade_type': 'close',
                'symbol_code': code,
                'entry_datetime': entry['entry_date'],
                'close_datetime': self.stock_repository.get_current_datetime(),
                'entry_price': entry_price,
                'close_price': current_price,
                'quantity': quantity,
                'profit_loss': profit_loss,
                'available_funds': self.calculate_available_funds(profit_loss, fee, transaction_amount),
                'fee': fee,
                'order_type': 'market',
                'position': 'long',
                'note': f"テスト売却: {evaluation.reason} (確信度: {evaluation.confidence_score})",
                'is_test': True
            }
            
            # 売却結果をデータベースに保存
            trade_id = self.stock_repository.save_trade_result(trade_result)
            
            # entriesテーブルの更新
            entry_update = {
                'code': code,
                'status': 'closed',
                'exit_date': self.stock_repository.get_current_date(),
                'exit_price': current_price,
                'profit': profit_loss,
                'profit_rate': profit_rate,
                'exit_reason': evaluation.reason,
                'is_test': True
            }
            
            # エントリー情報を更新
            self.stock_repository.update_entry(entry_update)
            
            self.logger.info(f"テスト売却完了: {code}")
            self.logger.info(f"損益: {profit_loss}円 ({profit_rate:.2f}%)")
            self.logger.info(f"売却理由: {evaluation.reason}")
            
        except Exception as e:
            self.logger.error(f"テスト売却処理中にエラーが発生: {e}")

    def calculate_available_funds(self, profit_loss: float, fee: float, transaction_amount: float) -> int:
        """
        テストモードでの利用可能資金を計算
        
        Args:
            profit_loss (float): 売却による損益
            fee (float): 取引手数料
            transaction_amount (float): 売却総額（現在価格×数量）
            
        Returns:
            int: 更新後の利用可能資金
        """
        try:
            # 最新のテスト取引から現在の利用可能資金を取得
            current_funds = self.stock_repository.get_latest_test_funds()
            
            # 利用可能資金がない場合は初期値を設定
            if current_funds is None:
                current_funds = 1000000  # 初期資金100万円（設定に応じて変更）
                self.logger.info(f"テスト用初期資金を設定: {current_funds}円")
            
            # 売却後の資金を計算（現在の資金 + 売却総額 - 手数料）
            updated_funds = int(current_funds + transaction_amount - fee)
            self.logger.info(f"テスト用資金更新: {current_funds}円 → {updated_funds}円 (売却総額: {transaction_amount}円, 手数料: {fee}円)")
            self.logger.info(f"損益情報: {profit_loss}円") # 参考情報としてログに残す
            
            return updated_funds
            
        except Exception as e:
            self.logger.error(f"テスト用資金計算中にエラーが発生: {e}")
            return 0  # エラー時は0を返す

    def calculate_fee(self, transaction_amount):
        """
        取引手数料を計算する
        
        Args:
            transaction_amount (float): 約定代金（現在価格×数量）
            
        Returns:
            int: 手数料（税込）
        """
        if transaction_amount <= 50000:  # 5万円まで
            return 55
        elif transaction_amount <= 100000:  # 10万円まで
            return 99
        elif transaction_amount <= 200000:  # 20万円まで
            return 115
        elif transaction_amount <= 500000:  # 50万円まで
            return 275
        elif transaction_amount <= 1000000:  # 100万円まで
            return 535
        elif transaction_amount <= 1500000:  # 150万円まで
            return 640
        elif transaction_amount <= 30000000:  # 3,000万円まで
            return 1013
        else:  # 3,000万円超
            return 1070

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
        
        # 保有証券情報の取得
        holdings = auto_sell.get_holdings()
        if not holdings:
            logger.error("保有証券情報の取得に失敗しました")
            return
            
        if not holdings:
            logger.info("保有証券が見つかりません")
            return
            
        logger.info(f"取得した保有証券: {holdings}")
        
        # 各銘柄ごとに処理を実行
        for code, current_price in holdings.items():
            logger.info(f"\n===== 証券コード {code} の処理を開始 =====")
            
            # 1. 過去の価格とインジケーターを取得
            historical_data = auto_sell.get_stock_data(code)
            if not historical_data:
                logger.error(f"証券コード {code} の株価データ取得に失敗しました")
                continue
                
            # 2. 評価を実行
            evaluation = auto_sell.evaluate_holding_with_ai(code, current_price, holdings[code]['position'], historical_data)
            if not evaluation:
                logger.error(f"証券コード {code} の評価に失敗しました")
                continue
                
            # 3. 評価結果をデータベースに保存
            auto_sell.stock_repository.save_holding_evaluation(evaluation, is_test=args.test)
            
            # 3.5. entriesテーブルのストップロスと目標価格も更新
            entry_update = {'code': code}
            
            # ストップロスが有効な値なら更新対象に追加
            if evaluation.stop_loss != "NG":
                entry_update['stop_loss'] = evaluation.stop_loss
            
            # 目標価格が有効な値なら更新対象に追加
            if evaluation.target_price != "NG":
                entry_update['target_price'] = evaluation.target_price
            
            # is_testパラメータは必須（WHERE句の条件に使用）
            entry_update['is_test'] = args.test
            
            # 更新すべき項目がある場合のみ更新実行
            if len(entry_update) > 2:  # codeとis_testを除く他の項目がある場合
                update_success = auto_sell.stock_repository.update_entry(entry_update)
                if update_success:
                    update_items = []
                    if 'stop_loss' in entry_update:
                        update_items.append(f"ストップロス={evaluation.stop_loss}")
                    if 'target_price' in entry_update:
                        update_items.append(f"目標価格={evaluation.target_price}")
                    
                    logger.info(f"entriesテーブルの価格情報を更新しました: {', '.join(update_items)}")
                else:
                    logger.error(f"entriesテーブルの価格情報更新に失敗しました")
            
            # 4. 評価結果のサマリーを表示
            logger.info(f"\n証券コード: {code}")
            logger.info(f"判断: {evaluation.decision}")
            logger.info(f"確信度: {evaluation.confidence_score}")
            logger.info(f"理由: {evaluation.reason}")
            logger.info(f"ストップロス: {evaluation.stop_loss}")
            logger.info(f"目標価格: {evaluation.target_price}")
            
            # 5. 売却判断
            if evaluation.decision == "SELL" and evaluation.confidence_score >= 500:
                logger.info(f"\n証券コード {code} は売却候補です")
                
                # テストモードの場合
                if args.test:
                    logger.info(f"テストモードのため、実際の売却は実行されません")
                    logger.info(f"テストモードでの売却シミュレーションを実行します")
                    auto_sell.execute_test_sell(code, evaluation)
                    continue
                
                # 強制売却モードの場合
                if args.force_sell:
                    logger.info(f"強制売却モードで {code} を売却します")
                    auto_sell.execute_sell(code, evaluation)
                    continue
                
                # 通常モードの場合は確認を求める
                if input(f"\n{code}を売却しますか？ (y/n): ").lower() == 'y':
                    auto_sell.execute_sell(code, evaluation)
            else:
                logger.info(f"証券コード {code} は保有継続と判断されました")
            
            logger.info(f"===== 証券コード {code} の処理を完了 =====\n")

    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise

if __name__ == "__main__":
    main() 