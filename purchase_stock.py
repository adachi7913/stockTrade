import logging
from typing import Dict, List
import os
from dotenv import load_dotenv
import time
import datetime
import heapq

from repository.entry_repository import EntryRepository
from Gemini.entry_judgment_handler import EntryJudgmentHandler
from browser_use.entry_browser_use import EntryBrowserUse
from repository.stock_repository import StockRepository
from utils.stock_util import StockUtil
from lib.table_category import TableCategory
from service.backtest_service import run_multiple_backtests
from lib.stock_filter import filter_stock, calculate_entry_score
from lib.prompt_generator import PromptGenerator

# TODO: 全体的な機能強化
# - 複数銘柄の同時処理
# - エラーリトライの実装
# - パフォーマンス監視と最適化
# - 監査ログの実装
# - 定期実行の仕組み

# ロギングの設定
# フォーマット: 日時 - モジュール名 - ログレベル - メッセージ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class StockPurchaseManager:
    """
    株式購入を管理するクラス
    
    主な責務:
    1. エントリー候補の取得と評価
    2. 過去の価格データの取得
    3. AIによるエントリー判断
    4. 実際の購入処理の実行
    5. エントリー情報の保存
    
    このクラスは同期処理を使用して、データ取得と処理を実現します。
    """
    
    def __init__(self, max_ai_calls=5, min_entry_score=70.0, api_delay=60):
        """
        初期化処理
        
        - .envファイルから環境変数を読み込み
        - 各種コンポーネントの初期化:
          - EntryRepository: エントリー情報の管理
          - EntryJudgmentHandler: Gemini APIによる判断
          - EntryBrowserUse: ブラウザ操作による購入実行
          
        Args:
            max_ai_calls (int): 一回の処理で最大何件のAI判断を行うか
            min_entry_score (float): エントリースコアの最低値（これ以下の候補はAI判断を行わない）
            api_delay (int): AI API呼び出し間の待機時間（秒）
        """
        load_dotenv()
        self.entry_repository = EntryRepository()
        self.judgment_handler = EntryJudgmentHandler(
            api_key=os.getenv('GEMINI_API_KEY'),
            logger=logger
        )
        self.browser_handler = EntryBrowserUse(logger=logger)
        self.logger = logger
        
        # 新しい設定パラメータ
        self.max_ai_calls = max_ai_calls
        self.min_entry_score = min_entry_score
        self.api_delay = api_delay
        
        # テストモード（実際の購入処理をスキップ）
        self.test_mode = False
        
        # プロンプト生成器を初期化
        self.prompt_generator = PromptGenerator()

    def _get_entry_candidate(self) -> List[Dict]:
        """
        エントリー候補を取得
        
        処理内容:
        1. EntryRepository を使用して最適なエントリー候補を取得
        2. 候補が存在しない場合は空リストを返す
        
        Returns:
            List[Dict]: エントリー候補情報のリスト
                - code: 証券コード
                - entry_price: エントリー価格
                - stop_loss: 損切り価格
                - target_price: 目標価格
                など
        """
        candidates = self.entry_repository.fetch_best_entry_candidates()
        if not candidates:
            self.logger.info("エントリー候補が見つかりませんでした")
            return []
        return candidates

    def _get_historical_data(self, stock_code: int) -> List[Dict]:
        """
        過去の価格データを取得
        
        処理内容:
        1. StockUtilを使用して企業情報を取得（5桁の証券コードに変換）
        2. 企業の業種名を特定し、英語名に変換
        3. StockRepositoryを使用して過去の価格データとインジケーターを取得
        
        エラーハンドリング:
        - 企業情報が見つからない場合は空リストを返す
        - 業種名の変換に失敗した場合は空リストを返す
        - 過去データが取得できない場合は空リストを返す
        - その他の例外発生時は空リストを返す
        
        Args:
            stock_code (int): 銘柄コード（4桁）
            
        Returns:
            List[Dict]: 過去の価格データとインジケーターのリスト
        """
        try:
            # 企業情報を取得（5桁の証券コードに変換）
            stock_util = StockUtil()
            five_digit_code = f"{stock_code}0"  # 末尾に0を追加
            company_info = stock_util.get_company_info(five_digit_code)
            if not company_info:
                self.logger.error(f"企業情報が見つかりません: {stock_code} (5桁コード: {five_digit_code})")
                return []

            # 業種名を取得（company_infoの5番目の要素が業種名）
            japanese_industry_name = company_info[5]
            
            try:
                # 日本語の業種名を英語に変換
                industry_name = TableCategory.get_table_prefix(japanese_industry_name)
            except ValueError as e:
                self.logger.error(f"業種名の変換に失敗: {japanese_industry_name}, エラー: {e}")
                return []
            
            # StockRepositoryを使用して過去データを取得（4桁の証券コードを使用）
            repository = StockRepository()
            try:
                historical_data = repository.get_stock_full_data_period(str(stock_code), industry_name)
                if not historical_data:
                    self.logger.error(f"過去の価格データが見つかりません: {stock_code}")
                    return []
                    
                return historical_data
            finally:
                repository.close()  # 必ずDBコネクションを閉じる

        except Exception as e:
            self.logger.error(f"過去データ取得中にエラーが発生: {e}")
            return []

    def _get_backtest_results(self, stock_code: int) -> Dict:
        """
        バックテスト結果を取得
        
        過去の複数の期間と戦略について、バックテスト結果を取得します。
        
        Args:
            stock_code (int): 銘柄コード（4桁）
            
        Returns:
            Dict: バックテスト結果のデータ
                - strategy_summary: 戦略別のパフォーマンスサマリー
                - best_strategy: 最も成績の良かった戦略
                - worst_strategy: 最も成績の悪かった戦略
                - success_rate: 成功率（勝率）
                - average_return: 平均リターン
                など
        """
        try:
            self.logger.info(f"{stock_code}: バックテスト実行開始")
            
            # バックテスト実行
            backtest_results = run_multiple_backtests(str(stock_code))
            
            if not backtest_results:
                self.logger.warning(f"{stock_code}: バックテスト結果が取得できませんでした")
                return {}
                
            # 結果を集計して返す
            # 各戦略のパフォーマンスを集計
            strategy_summary = {}
            total_trades = 0
            total_wins = 0
            total_profit = 0
            
            for result in backtest_results:
                strategy = result.get("strategy", "unknown")
                trades = result.get("trades", [])
                
                # その戦略のサマリーを初期化
                if strategy not in strategy_summary:
                    strategy_summary[strategy] = {
                        "win_count": 0,
                        "loss_count": 0,
                        "total_profit": 0,
                        "avg_profit": 0,
                        "trade_count": 0
                    }
                
                # 取引情報を集計
                win_count = sum(1 for trade in trades if trade["profit"] > 0)
                loss_count = sum(1 for trade in trades if trade["profit"] <= 0)
                total_strategy_profit = sum(trade["profit"] for trade in trades)
                trade_count = len(trades)
                
                # 戦略サマリーを更新
                strategy_summary[strategy]["win_count"] += win_count
                strategy_summary[strategy]["loss_count"] += loss_count
                strategy_summary[strategy]["total_profit"] += total_strategy_profit
                strategy_summary[strategy]["trade_count"] += trade_count
                if trade_count > 0:
                    strategy_summary[strategy]["avg_profit"] = total_strategy_profit / trade_count
                
                # 全体の統計も更新
                total_trades += trade_count
                total_wins += win_count
                total_profit += total_strategy_profit
            
            # 最良/最悪の戦略を特定
            best_strategy = max(strategy_summary.items(), key=lambda x: x[1]["total_profit"], default=("none", {}))
            worst_strategy = min(strategy_summary.items(), key=lambda x: x[1]["total_profit"], default=("none", {}))
            
            # 全体の成功率を計算
            success_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
            average_return = (total_profit / total_trades) if total_trades > 0 else 0
            
            # 結果の要約を返す
            summary = {
                "strategy_summary": strategy_summary,
                "best_strategy": best_strategy[0],
                "worst_strategy": worst_strategy[0],
                "success_rate": success_rate,
                "average_return": average_return,
                "total_trades": total_trades,
                "total_profit": total_profit
            }
            
            self.logger.info(f"{stock_code}: バックテスト完了 - 成功率: {success_rate:.2f}%, 平均リターン: {average_return:.2f}")
            return summary
            
        except Exception as e:
            self.logger.error(f"{stock_code}: バックテスト実行中にエラーが発生: {e}")
            return {}

    def _filter_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """
        エントリー候補をフィルタリングする
        
        基本的なフィルター条件に基づいて候補をフィルタリングします。
        
        Args:
            candidates (List[Dict]): エントリー候補のリスト
            
        Returns:
            List[Dict]: フィルタリング後の候補リスト
        """
        filtered_candidates = []
        
        for candidate in candidates:
            stock_code = candidate.get('code')
            close_price = candidate.get('close', 0)
            
            # 必要な技術指標を取得
            rsi = candidate.get('rsi')
            stoch_k = candidate.get('stoch_k')
            atr = candidate.get('atr')
            
            # 市場情報を取得
            market_cap = candidate.get('market_cap')
            volume_data = candidate.get('volume_data', [])
            
            # エントリー制限情報
            last_no_entry_date = candidate.get('last_no_entry_date')
            no_entry_span = candidate.get('no_entry_span')
            
            # フィルタリング
            if filter_stock(
                stock_code=stock_code,
                close=close_price,
                market_cap=market_cap,
                last_no_entry_date=last_no_entry_date,
                no_entry_span=no_entry_span,
                volume_data=volume_data,
                atr=atr,
                rsi=rsi,
                stoch_k=stoch_k
            ):
                filtered_candidates.append(candidate)
        
        self.logger.info(f"フィルタリング結果: {len(candidates)}件中 {len(filtered_candidates)}件が条件を満たしています")
        return filtered_candidates

    def _score_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """
        エントリー候補にスコアを付ける
        
        テクニカル指標とバックテスト結果に基づいてスコアを計算し、
        候補リストに追加します。
        
        Args:
            candidates (List[Dict]): エントリー候補のリスト
            
        Returns:
            List[Dict]: スコア付きの候補リスト
        """
        scored_candidates = []
        
        for candidate in candidates:
            stock_code = candidate.get('code')
            
            # 過去データの取得
            historical_data = self._get_historical_data(stock_code)
            if not historical_data:
                self.logger.warning(f"{stock_code}: 過去データが取得できないためスキップ")
                continue
                
            # 最新の技術指標を取得
            latest_data = historical_data[-1] if historical_data else {}
            
            # バックテスト結果の取得
            backtest_results = self._get_backtest_results(stock_code)
            if not backtest_results:
                self.logger.warning(f"{stock_code}: バックテスト結果が取得できないためスコアを下げます")
            
            # スコアを計算
            entry_score = calculate_entry_score(
                stock_data=candidate,
                backtest_results=backtest_results,
                technical_indicators=latest_data
            )
            
            # 結果を候補に追加
            candidate['entry_score'] = entry_score
            candidate['historical_data'] = historical_data
            candidate['backtest_results'] = backtest_results
            
            scored_candidates.append(candidate)
            
            self.logger.info(f"{stock_code}: エントリースコア {entry_score:.2f}/100")
        
        # スコアでソート（降順）
        scored_candidates.sort(key=lambda x: x.get('entry_score', 0), reverse=True)
        
        return scored_candidates

    def _select_top_candidates(self, candidates: List[Dict], limit: int) -> List[Dict]:
        """
        上位候補を選択する
        
        スコアに基づいて上位の候補を選択します。
        
        Args:
            candidates (List[Dict]): スコア付きの候補リスト
            limit (int): 選択する候補の最大数
            
        Returns:
            List[Dict]: 選択された上位候補のリスト
        """
        # エントリースコアの最低値でフィルター
        qualified_candidates = [c for c in candidates if c.get('entry_score', 0) >= self.min_entry_score]
        
        # 上位N件を取得
        top_candidates = qualified_candidates[:limit]
        
        skipped_count = len(candidates) - len(top_candidates)
        if skipped_count > 0:
            self.logger.info(f"スコア不足または上限超過により {skipped_count}件がスキップされました")
            
        return top_candidates

    def execute_purchase(self) -> bool:
        """
        株式購入処理を実行

        処理フロー:
        1. エントリー候補の取得
           - 複数の候補を取得し、候補が見つからない場合は処理を中断
        2. 基本フィルタリングで候補を絞り込み
        3. 残った候補にスコアを付け、上位候補を選択
        4. 選択された候補に対してAIによるエントリー判断を実施
        5. 推奨された候補について実際の購入処理を実行
        6. 1件でも購入が成功すれば True を返し、すべて失敗の場合は False を返す

        Returns:
            bool: 購入成功で True、すべて失敗または候補がない場合は False
        """
        try:
            # 1. エントリー候補を全件取得
            self.logger.info("エントリー候補の取得を開始")
            candidates = self._get_entry_candidate()
            if not candidates:
                self.logger.info("エントリー候補が見つかりませんでした")
                return False
            self.logger.info(f"取得完了: {len(candidates)}件のエントリー候補")
            
            # 2. 基本フィルタリング
            self.logger.info("基本フィルタリングを実行")
            filtered_candidates = self._filter_candidates(candidates)
            if not filtered_candidates:
                self.logger.info("フィルタリング後の候補がありません")
                return False
            
            # 3. 候補にスコアを付け、上位候補を選択
            self.logger.info("候補のスコアリングを実行")
            scored_candidates = self._score_candidates(filtered_candidates)
            
            self.logger.info("上位候補の選択")
            top_candidates = self._select_top_candidates(
                scored_candidates, 
                self.max_ai_calls
            )
            
            if not top_candidates:
                self.logger.info("選択後の候補がありません")
                return False
            
            self.logger.info(f"選択完了: {len(top_candidates)}件の上位候補")

            any_success = False
            # 4. 各上位候補に対してループ処理
            for idx, candidate in enumerate(top_candidates):
                stock_code = candidate.get('code')
                entry_score = candidate.get('entry_score', 0)
                historical_data = candidate.get('historical_data', [])
                backtest_results = candidate.get('backtest_results', {})
                
                self.logger.info(f"候補 {idx+1}/{len(top_candidates)}: {stock_code} (スコア: {entry_score:.2f})")
                
                # モデルグレードに応じてプロンプトを最適化
                if os.getenv('USE_SIMPLIFIED_PROMPT', 'false').lower() == 'true':
                    # 簡略化されたプロンプト（低スペックモデル用）
                    prompt = self.prompt_generator.generate_simplified_prompt(
                        stock_data=candidate,
                        entry_score=entry_score
                    )
                else:
                    # 標準プロンプト
                    prompt = self.prompt_generator.generate_entry_prompt(
                        stock_data=candidate,
                        backtest_results=backtest_results,
                        technical_data=historical_data[-10:] if len(historical_data) >= 10 else historical_data,
                        entry_score=entry_score
                    )
                
                # API呼び出し間隔を調整
                if idx > 0:
                    self.logger.info(f"APIレートリミット対策: {self.api_delay}秒間待機")
                    time.sleep(self.api_delay)
                
                # 処理時間の計測開始
                start_time = time.time()
                
                # Gemini APIでエントリー判断
                judgment = self.judgment_handler.judge_entry_with_prompt(
                    candidate=candidate,
                    custom_prompt=prompt
                )
                
                # 処理時間の計測終了
                end_time = time.time()
                processing_time = end_time - start_time
                
                # 処理情報を取得
                processing_info = {
                    'prompting_tokens': judgment.get('prompting_tokens', 0),
                    'completion_tokens': judgment.get('completion_tokens', 0),
                    'total_tokens': judgment.get('total_tokens', 0),
                    'processing_time': processing_time,
                    'model_version': os.getenv('GEMINI_PRO_MODEL', 'unknown')
                }
                
                # スコアと判断結果をログに出力
                self.logger.info(f"候補 {stock_code}: エントリースコア {entry_score:.2f}/100, AI判断 should_enter={judgment.get('should_enter', False)}, confidence={judgment.get('confidence', 0)}")
                
                # AI判断結果とバックテスト結果をDBに保存
                self.entry_repository.save_full_judgment_data(
                    judgment_data=judgment,
                    stock_data=candidate,
                    backtest_data=backtest_results,
                    processing_info=processing_info
                )
                
                if not judgment.get('should_enter', False):
                    self.logger.info(f"候補 {stock_code} はエントリー見送り: {judgment.get('reasoning', 'No reasoning provided')}")
                    continue

                # 5. 推奨された候補についてエントリーを実行
                if self.test_mode:
                    self.logger.info(f"テストモード: 候補 {stock_code} の実際の購入処理をスキップします")
                    # テストモードでもエントリー成功とみなす
                    any_success = True
                else:
                    success = self.browser_handler.execute_entry(candidate)
                    if success:
                        # エントリー情報を保存
                        self.entry_repository.save_entry_info(candidate)
                        self.logger.info(f"エントリー成功: {stock_code}")
                        any_success = True
                    else:
                        self.logger.error(f"エントリー失敗: {stock_code}")

            return any_success

        except Exception as e:
            self.logger.error(f"購入処理中にエラーが発生: {e}", exc_info=True)
            return False


# 同期実行用のエントリーポイント
def main():
    # コマンドラインオプションの解析
    import argparse
    parser = argparse.ArgumentParser(description='株式購入処理を実行')
    parser.add_argument('--max-calls', type=int, default=5, help='一回の処理で最大何件のAI判断を行うか（デフォルト: 5）')
    parser.add_argument('--min-score', type=float, default=70.0, help='エントリースコアの最低値（デフォルト: 70.0）')
    parser.add_argument('--api-delay', type=int, default=60, help='AI API呼び出し間の待機時間（秒、デフォルト: 60）')
    args = parser.parse_args()

    manager = StockPurchaseManager(
        max_ai_calls=args.max_calls,
        min_entry_score=args.min_score,
        api_delay=args.api_delay
    )
    
    success = manager.execute_purchase()
    if success:
        logger.info("株式購入処理が完了しました")
    else:
        logger.info("株式購入処理は実行されませんでした")

if __name__ == "__main__":
    main() 