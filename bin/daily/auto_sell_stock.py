import os
import sys
from pathlib import Path
from datetime import datetime, date, timedelta

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
from utils.date_util import is_holiday
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

    def calculate_elapsed_business_days(self, entry_date_obj: date, today_obj: date) -> int:
        """
        指定されたエントリー日から今日までの経過営業日数（土日・祝日を除く）を計算する。
        utils.date_util.is_holiday を使用。
        エントリー日当日は0日目としてカウント開始。
        """
        if not isinstance(entry_date_obj, date) or not isinstance(today_obj, date):
            self.logger.error("日付オブジェクトが無効です。")
            return -1 # エラーを示す

        if entry_date_obj >= today_obj:
            return 0

        business_days = 0
        current_date_iter = entry_date_obj
        while current_date_iter < today_obj:
            # is_holiday は土日・祝日なら True を返す
            # is_holiday_checkの引数はdatetime.date型である必要がある
            if not is_holiday(current_date_iter): # is_holiday_check を is_holiday に変更
                business_days += 1
            current_date_iter += timedelta(days=1)
        return business_days

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

    def execute_test_sell(self, code: str, evaluation: EvaluationResult, position: str, entry_info: Dict) -> None:
        """
        テストモードでの売却・買い戻しシミュレーションを実行
        Args:
            code (str): 証券コード
            evaluation (EvaluationResult): AIによる評価結果
            position (str): ポジション ('long' or 'short')
            entry_info (Dict): entriesテーブルから取得した保有情報 {'current_price': 価格, 'position': ポジション}
        """
        log_action = '売却' if position == 'long' else '買い戻し' # 先に定義
        self.logger.info(f"テストモードで {code} の{log_action}シミュレーションを実行")
        try:
            # entriesテーブルから取得したエントリー情報を利用
            # entry_info の 'current_price' は get_holdings 時点の entry_price なので注意
            entry_price = float(entry_info['current_price']) # get_holdings で取得した価格を使う

            # 数量を取得するために、改めてエントリー情報をDBから取得する
            full_entry_info = self.stock_repository.get_entry_by_code(code, is_test=self.test_mode)
            if not full_entry_info:
                self.logger.error(f"エントリー情報が見つかりません: {code}")
                return
            quantity = int(full_entry_info['quantity']) # quantity を取得

            # 現在価格を取得 (AI評価時の最新価格を使う)
            # evaluation.close は main 関数で設定されている想定
            if not hasattr(evaluation, 'close') or evaluation.close is None:
                 self.logger.error(f"評価結果に最新価格が含まれていません: {code}")
                 # フォールバックとして entry_price を使うか、エラーにする
                 current_price = entry_price # フォールバック
                 self.logger.warning(f"最新価格がないため、エントリー価格 {entry_price} を使用します")
            else:
                 current_price = float(evaluation.close)


            # 取引額計算
            transaction_amount = current_price * quantity

            # 手数料計算
            fee = self.calculate_fee(transaction_amount)

            # 損益計算
            if position == 'long':
                profit_loss = (current_price - entry_price) * quantity - fee
                profit_rate = ((current_price - entry_price) / entry_price) * 100 if entry_price != 0 else 0
                trade_type = 'close_long' # trade_results テーブル用にタイプを設定
            elif position == 'short':
                profit_loss = (entry_price - current_price) * quantity - fee
                profit_rate = ((entry_price - current_price) / entry_price) * 100 if entry_price != 0 else 0
                trade_type = 'close_short' # trade_results テーブル用にタイプを設定
            else:
                self.logger.error(f"不明なポジションタイプです: {position}")
                return

            # 利用可能資金の更新
            # current_funds = self.stock_repository.get_latest_test_funds() # calculate_available_funds 内で取得するので不要
            new_available_funds = self.calculate_available_funds(profit_loss, fee, transaction_amount, position) # position 渡す

            # 更新前の資金をログ用にしゅとくしておく
            current_funds = self.stock_repository.get_latest_test_funds() or 0

            self.logger.info(f"テスト用資金更新: {current_funds}円 → {new_available_funds}円 ({log_action}総額: {transaction_amount:.2f}円, 手数料: {fee:.2f}円)")


            # --- trade_results テーブルへの保存処理 ---
            trade_result_data = {
                'trade_type': trade_type,
                'symbol_code': code,
                'entry_datetime': full_entry_info['entry_date'], # エントリー日時
                'close_datetime': self.stock_repository.get_current_datetime(), # 現在日時
                'entry_price': entry_price, # get_holdings 時点の価格
                'close_price': current_price,
                'quantity': quantity,
                'profit_loss': profit_loss,
                'available_funds': new_available_funds,
                'fee': fee,
                'order_type': 'market', # 仮置き
                'position': position,
                'strategy_id': None, # 必要なら設定
                'note': evaluation.reason, # AIの理由をメモとして保存
                'is_test': True
            }
            trade_id = self.stock_repository.save_trade_result(trade_result_data)
            if trade_id:
                self.logger.info(f"テスト{log_action}結果を保存しました (trade_id: {trade_id})")
            else:
                 self.logger.error(f"テスト{log_action}結果の保存に失敗しました", exc_info=True)

            # --- entries テーブルの更新処理 ---
            entry_update_data = {
                'code': code,
                'status': 'closed',
                'exit_date': self.stock_repository.get_current_date(),
                'exit_price': current_price,
                'profit': profit_loss,
                'profit_rate': profit_rate,
                'exit_reason': evaluation.reason,
                'is_test': True
            }
            if self.stock_repository.update_entry(entry_update_data):
                self.logger.info(f"テスト{log_action}完了 ({log_action}済み): {code}")
            else:
                 self.logger.error(f"エントリー情報の更新に失敗しました: {code}")

            self.logger.info(f"損益: {profit_loss:.2f}円 ({profit_rate:.2f}%)")
            self.logger.info(f"{log_action}理由: {evaluation.reason}")

        except Exception as e:
            # log_action が定義されていることを保証
            log_action_in_except = '売却/買い戻し'
            if 'position' in locals():
                log_action_in_except = '売却' if position == 'long' else '買い戻し'
            self.logger.error(f"テスト{log_action_in_except}処理中にエラーが発生: {e}", exc_info=True) # トレースバックも出力

    def calculate_available_funds(self, profit_loss: float, fee: float, transaction_amount: float, position: str) -> int:
        """
        テスト取引後の利用可能資金を計算します
        Args:
            profit_loss (float): 損益額
            fee (float): 手数料
            transaction_amount (float): 取引総額（売却額または買い戻し額）
            position (str): ポジション ('long' or 'short')

        Returns:
            int: 更新後の利用可能資金
        """
        try:
            current_funds = self.stock_repository.get_latest_test_funds()
            if current_funds is None:
                self.logger.warning("最新のテスト用資金を取得できませんでした。初期資金を0として計算します。")
                current_funds = 0

            if position == 'long':
                # ロング売却の場合：現在資金 + 売却額 - 手数料
                new_funds = current_funds + transaction_amount - fee
            elif position == 'short':
                # ショート買い戻しの場合：現在資金 + (エントリー時受取額 - 買い戻し額) - 手数料
                # エントリー時の受取額 = entry_price * quantity
                # (エントリー時受取額 - 買い戻し額) = (entry_price - current_price) * quantity
                # profit_loss = (entry_price - current_price) * quantity - fee なので、
                # profit_loss + fee = (entry_price - current_price) * quantity となる
                # よって、 new_funds = current_funds + profit_loss
                # ただし、これは手数料を二重に引かないための計算。資金の増減としては損益を加算するのが直感的。
                new_funds = current_funds + profit_loss # 損益をそのまま加算する
                self.logger.debug(f"ショート買い戻し資金計算: current={current_funds}, profit_loss={profit_loss}, new={new_funds}")
                # TODO: ショートエントリー時の証拠金などを考慮した、より正確な計算が必要な場合がある
            else:
                 self.logger.error(f"不明なポジションタイプです: {position}")
                 return current_funds # エラー時は現在の資金を返す

            return int(new_funds)
        except Exception as e:
            self.logger.error(f"利用可能資金の計算エラー: {e}")
            return current_funds # エラー時は現在の資金を返す

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
    logger = setup_logging("auto_sell_stock")

    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='保有株式の自動売却処理')
    parser.add_argument('--test', action='store_true', help='テストモードで実行（実際の売買は行わない）')
    parser.add_argument('--force-sell', action='store_true', help='強制売却モードで実行')
    parser.add_argument('--debug', action='store_true', help='デバッグモードで実行')
    args = parser.parse_args()

    # --- 評価対象日（昨日）が非稼働日かどうかのチェック ---
    today_date = date.today()
    yesterday_date = today_date - timedelta(days=1)
    if is_holiday(yesterday_date): # 昨日が休日か判定
        logger.info(f"評価対象日 ({yesterday_date}) は非稼働日（土日祝）のため、本日の主要な売買判断処理をスキップします。")
        return # 処理を終了
    # --- ここまで変更 ---

    try:
        auto_sell = AutoSellStock(logger, test_mode=args.test)
        holdings = auto_sell.get_holdings()
        if holdings is None: # Noneチェックも行う
            logger.error("保有証券情報の取得に失敗しました")
            return

        if not holdings:
            logger.info("保有証券が見つかりません")
            return

        logger.info(f"取得した保有証券: {holdings}")

        # 各銘柄ごとに処理を実行
        for code, holding_info in holdings.items(): # holding_info を使うように変更
            logger.info(f"\n===== 証券コード {code} ({holding_info['position']}) の処理を開始 =====")

            should_evaluate_with_ai = True # AI評価を実行するかどうかのフラグ
            sell_reason = None # 売却理由（損切り/利確）
            evaluation = None # evaluation を初期化
            historical_data = None # historical_data を初期化

            # --- ここから追加 ---
            try:
                # 1. 最新の株価データを取得 (現在価格の取得のため)
                historical_data = auto_sell.get_stock_data(code)
                if not historical_data:
                    logger.error(f"証券コード {code} の株価データ取得に失敗しました。AI評価に進みます。")
                    # データ取得失敗時はAI評価に任せる（あるいは処理中断）
                    continue # 次の銘柄へ

                current_close_price = float(historical_data[-1]['close']) # 最新の終値を取得

                # 2. entries テーブルからエントリー情報を取得 (stop_loss, target_price のため)
                entry_details = auto_sell.stock_repository.get_entry_by_code(code, is_test=args.test)
                if not entry_details:
                    logger.warning(f"証券コード {code} のエントリー詳細が見つかりません。AI評価に進みます。")
                else:
                    # 3. ストップロス価格と比較
                    stop_loss_str = entry_details.get('stop_loss')
                    if stop_loss_str and stop_loss_str != 'NG':
                        try:
                            stop_loss_price = float(stop_loss_str)
                            # ★★★ ショートポジションの損切り条件を追加 ★★★
                            if holding_info['position'] == 'long':
                                is_stop_loss = current_close_price <= stop_loss_price
                                comparison_symbol = '<='
                            elif holding_info['position'] == 'short':
                                is_stop_loss = current_close_price >= stop_loss_price
                                comparison_symbol = '>='
                            else: # ポジションが不明な場合はスキップ
                                is_stop_loss = False
                                comparison_symbol = '??'
                                logger.warning(f"ポジションタイプが不明なため、ストップロス比較をスキップ: {holding_info['position']}")

                            if is_stop_loss:
                                logger.info(f"ストップロス条件に抵触: 現在価格({current_close_price}) {comparison_symbol} ストップロス({stop_loss_price})")
                                should_evaluate_with_ai = False
                                sell_reason = f"Stop loss triggered (Current: {current_close_price} {comparison_symbol} Stop: {stop_loss_price})"
                                # 簡易的なEvaluationResultを作成して売却処理へ
                                evaluation = EvaluationResult(
                                    code=code,
                                    decision="SELL",
                                    confidence_score=1000, # 最高確信度
                                    reason=sell_reason,
                                    stop_loss=str(current_close_price), # 売却価格を記録
                                    target_price="NG"
                                )
                                evaluation.close = current_close_price # 最新価格を設定
                        except ValueError:
                            logger.warning(f"ストップロス価格が無効な値です: {stop_loss_str}")

                    # 4. 目標価格と比較 (ストップロスに抵触していない場合のみ)
                    if should_evaluate_with_ai: # まだ売却が決まっていない場合
                        target_price_str = entry_details.get('target_price')
                        if target_price_str and target_price_str != 'NG':
                            try:
                                target_price = float(target_price_str)
                                # ★★★ ショートポジションの利確条件を追加 ★★★
                                if holding_info['position'] == 'long':
                                    is_target_reached = current_close_price >= target_price
                                    comparison_symbol = '>='
                                elif holding_info['position'] == 'short':
                                    is_target_reached = current_close_price <= target_price
                                    comparison_symbol = '<='
                                else: # ポジションが不明な場合はスキップ
                                    is_target_reached = False
                                    comparison_symbol = '??'
                                    logger.warning(f"ポジションタイプが不明なため、目標価格比較をスキップ: {holding_info['position']}")

                                if is_target_reached:
                                    logger.info(f"目標価格に到達: 現在価格({current_close_price}) {comparison_symbol} 目標価格({target_price})")
                                    should_evaluate_with_ai = False
                                    sell_reason = f"Target price reached (Current: {current_close_price} {comparison_symbol} Target: {target_price})"
                                    # 簡易的なEvaluationResultを作成して売却処理へ
                                    evaluation = EvaluationResult(
                                        code=code,
                                        decision="SELL",
                                        confidence_score=1000, # 最高確信度
                                        reason=sell_reason,
                                        stop_loss="NG",
                                        target_price=str(current_close_price) # 売却価格を記録
                                    )
                                    evaluation.close = current_close_price # 最新価格を設定
                            except ValueError:
                                logger.warning(f"目標価格が無効な値です: {target_price_str}")

                    # --- ここから最低保有期間チェックを追加 ---
                    if should_evaluate_with_ai: # まだ売却が決まっていない場合のみ期間チェック
                        MIN_HOLDING_BUSINESS_DAYS = 2 # 最低保有営業日数
                        entry_date_value = entry_details.get('entry_date') # 変数名を value に変更

                        if entry_date_value is not None: # Noneでないことを確認
                            try:
                                parsed_date_obj = None
                                if isinstance(entry_date_value, str): # 文字列の場合
                                    # self.logger.debug(f"エントリー日は文字列として取得: {entry_date_value}") # ログレベルは適宜調整
                                    if ' ' in entry_date_value: # 'YYYY-MM-DD HH:MM:SS' の形式の場合
                                        parsed_date_obj = datetime.strptime(entry_date_value.split(' ')[0], '%Y-%m-%d').date()
                                    else: # 'YYYY-MM-DD' の形式を期待
                                        parsed_date_obj = datetime.strptime(entry_date_value, '%Y-%m-%d').date()
                                elif isinstance(entry_date_value, date): # 既に datetime.date オブジェクトの場合
                                    # self.logger.debug(f"エントリー日はdateオブジェクトとして取得: {entry_date_value}") # ログレベルは適宜調整
                                    parsed_date_obj = entry_date_value
                                else:
                                    logger.error(f"エントリー日の型が予期せぬ型です ({type(entry_date_value)})。保有期間チェックをスキップします。")
                                    # parsed_date_obj は None のまま

                                if parsed_date_obj: # parsed_date_obj が正常に設定された場合のみ計算
                                    today_obj = date.today()
                                    elapsed_business_days = auto_sell.calculate_elapsed_business_days(parsed_date_obj, today_obj)

                                    if elapsed_business_days == -1: # 計算エラーの場合
                                        logger.error(f"証券コード {code}: 経過営業日数の計算に失敗しました。保有期間チェックをスキップします。")
                                    else:
                                        logger.info(f"証券コード {code}: エントリー日 {parsed_date_obj}, 経過営業日数 {elapsed_business_days}日")
                                        if elapsed_business_days < MIN_HOLDING_BUSINESS_DAYS:
                                            logger.info(f"最低保有期間 ({MIN_HOLDING_BUSINESS_DAYS}営業日) に未達のため、AI評価・売却処理をスキップします。")
                                            should_evaluate_with_ai = False
                                else:
                                    # parsed_date_obj が None (型が不正だったなど) の場合
                                    logger.warning(f"証券コード {code}: エントリー日のパースに失敗したため、保有期間チェックをスキップします。")

                            except ValueError as ve: # strptime でのエラー
                                logger.error(f"エントリー日の文字列形式が正しくありません: '{entry_date_value}' - {ve}。保有期間チェックをスキップします。")
                            except Exception as e:
                                logger.error(f"保有期間計算中に予期せぬエラーが発生: {e}。保有期間チェックをスキップします。", exc_info=True)
                        else:
                            logger.warning(f"証券コード {code}: エントリー日 (entry_date) がNoneです。保有期間チェックをスキップします。")
                    # --- ここまで最低保有期間チェック ---
            except Exception as e:
                logger.error(f"価格比較または保有期間チェック処理中に予期せぬエラー: {e}", exc_info=True)
                should_evaluate_with_ai = True # エラー時はAI評価にフォールバック（あるいは中断）


            # 5. AIによる評価 (損切り/利確条件に該当せず、かつ保有期間も満たした場合)
            if should_evaluate_with_ai:
                # historical_data が None の場合 (価格比較処理でエラーが発生した場合など) は再取得
                if historical_data is None:
                    historical_data = auto_sell.get_stock_data(code)
                    if not historical_data:
                         logger.error(f"証券コード {code} の株価データ再取得にも失敗しました")
                         continue

                # AI評価を実行
                evaluation = auto_sell.evaluate_holding_with_ai(code, holding_info['current_price'], holding_info['position'], historical_data)
                if not evaluation:
                    logger.error(f"証券コード {code} のAI評価に失敗しました")
                    continue
                # AI評価の場合、最新価格を evaluation に設定しておく（テスト売却で使うため）
                evaluation.close = float(historical_data[-1]['close'])

                # 6. 評価結果をデータベースに保存 (AI評価した場合のみ)
                auto_sell.stock_repository.save_holding_evaluation(evaluation, is_test=args.test)

                # 7. entriesテーブルのストップロスと目標価格も更新 (AI評価した場合のみ)
                entry_update = {'code': code}
                if evaluation.stop_loss != "NG":
                    entry_update['stop_loss'] = evaluation.stop_loss
                if evaluation.target_price != "NG":
                    entry_update['target_price'] = evaluation.target_price
                entry_update['is_test'] = args.test
                if len(entry_update) > 2:
                    update_success = auto_sell.stock_repository.update_entry(entry_update)
                    if update_success:
                        update_items = []
                        if 'stop_loss' in entry_update: update_items.append(f"ストップロス={evaluation.stop_loss}")
                        if 'target_price' in entry_update: update_items.append(f"目標価格={evaluation.target_price}")
                        logger.info(f"entriesテーブルのAI推奨価格情報を更新しました: {', '.join(update_items)}")
                    else:
                        logger.error(f"entriesテーブルのAI推奨価格情報更新に失敗しました")

                # 8. AI評価結果のサマリーを表示
                logger.info(f"\nAI評価結果 - 証券コード: {code}")
                logger.info(f"判断: {evaluation.decision}")
                logger.info(f"確信度: {evaluation.confidence_score}")
                logger.info(f"理由: {evaluation.reason}")
                logger.info(f"推奨ストップロス: {evaluation.stop_loss}")
                logger.info(f"推奨目標価格: {evaluation.target_price}")

            # 9. 売却判断 (損切り/利確か、AI判断か)
            # evaluation が存在し (損切り/利確 or AI評価成功)、かつ売却条件を満たす場合
            if evaluation and (sell_reason or (evaluation.decision == "SELL" and evaluation.confidence_score >= 500)):
                # 損切り/利確の場合とAI判断の場合でログメッセージを分ける
                if sell_reason:
                    log_reason_type = '損切り' if 'Stop loss' in sell_reason else '利益確定'
                    logger.info(f"\n証券コード {code} ({holding_info['position']}) はルールベース ({log_reason_type}) により売却候補です")
                else:
                     logger.info(f"\n証券コード {code} ({holding_info['position']}) はAI判断により売却候補です (確信度: {evaluation.confidence_score})")

                # テストモードの場合
                if args.test:
                    # evaluation オブジェクトは上で作成または取得されているはず
                    logger.info(f"テストモードのため、実際の売却は実行されません")
                    log_sim_type = '損切り' if sell_reason and 'Stop loss' in sell_reason else ('利益確定' if sell_reason else '売却')
                    logger.info(f"テストモードでの {log_sim_type} シミュレーションを実行します")
                     # execute_test_sell に evaluation を渡す（損切り/利確時は上で簡易作成したものを利用）
                    auto_sell.execute_test_sell(code, evaluation, holding_info['position'], holding_info)
                    continue

                # 強制売却モードの場合
                if args.force_sell:
                    log_force_type = '損切り' if sell_reason and 'Stop loss' in sell_reason else ('利益確定' if sell_reason else '売却')
                    logger.info(f"強制売却モードで {code} を {log_force_type} します")
                    # execute_sell を呼び出す (要実装 or 改修)
                    # auto_sell.execute_sell(code, evaluation) # execute_sell が未実装の場合はコメントアウト
                    logger.warning("execute_sell 関数が未実装またはコメントアウトされています。")
                    continue

                # 通常モードの場合は確認を求める
                log_confirm_type = '損切り' if sell_reason and 'Stop loss' in sell_reason else ('利益確定' if sell_reason else '売却')
                if input(f"\n{code}を {log_confirm_type} しますか？ (y/n): ").lower() == 'y':
                    # execute_sell を呼び出す (要実装 or 改修)
                    # auto_sell.execute_sell(code, evaluation) # execute_sell が未実装の場合はコメントアウト
                    logger.warning("execute_sell 関数が未実装またはコメントアウトされています。")
            # 保有継続の場合 (evaluationが存在しない、または売却条件を満たさない)
            elif evaluation is None and not sell_reason: # AI評価もスキップされ、損切り/利確もなく、保有期間未達でもない場合 (基本的には保有期間未達でshould_evaluate_with_ai=Falseになる)
                # 上記の保有期間チェックで should_evaluate_with_ai = False になっているので、
                # このelifは、例えばエントリー日がない、日付パースエラーなどで保有期間チェック自体がスキップされ、
                # かつAI評価にも進まなかったレアケース用。
                # 実際には保有期間未達のログが出力されていれば、ここは通らないか、保有継続のログが出るはず。
                logger.info(f"証券コード {code} ({holding_info['position']}) は、評価情報不足または保有期間未達のため保有継続します。")
            else: # AI評価がHOLDだった場合、または保有期間未達でAI評価がスキップされた場合
                 logger.info(f"証券コード {code} ({holding_info['position']}) は保有継続と判断されました")

            logger.info(f"===== 証券コード {code} の処理を完了 =====\n")

    except Exception as e:
        logger.error(f"メイン処理でエラーが発生しました: {e}", exc_info=True) # トレースバックも出力
        # raise # 必要に応じて再raiseする

if __name__ == "__main__":
    main() 