import os
import sys

# デバッグ情報の出力
def print_debug_info():
    print("\n=== デバッグ情報 ===")
    print(f"Python バージョン: {sys.version}")
    print(f"実行ファイル: {__file__}")
    print(f"初期カレントディレクトリ: {os.getcwd()}")
    print(f"PYTHONPATH: {sys.path}")
    print(f"環境変数:")
    for key, value in os.environ.items():
        if key.startswith(('PYTHON', 'PATH', 'VIRTUAL_ENV')):
            print(f"  {key}: {value}")
    print("==================\n")

# デバッグ情報を表示
print_debug_info()

# ルートディレクトリの取得とPythonパスの設定
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 3階層上がルート
sys.path.insert(0, root_dir)  # 最優先でルートディレクトリを検索パスに追加
print(f"ルートディレクトリ: {root_dir}")
os.chdir(root_dir)  # カレントディレクトリの移動

# カレントディレクトリの変更を確認
print(f"変更後のカレントディレクトリ: {os.getcwd()}")
print(f"更新後のPYTHONPATH先頭: {sys.path[0]}")

from typing import Dict, List
from dotenv import load_dotenv
import time

# .envファイルの存在確認
env_path = os.path.join(root_dir, '.env')
print(f"\n.envファイルのパス: {env_path}")
print(f".envファイルの存在: {os.path.exists(env_path)}")

from repository.entry_repository import EntryRepository
from repository.fund_manager import FundManager
from Gemini.entry_judgment_handler import EntryJudgmentHandler
from browser_use.entry_browser_use import EntryBrowserUse
from repository.stock_repository import StockRepository
from utils.stock_util import StockUtil
from lib.table_category import TableCategory
from service.backtest_service import run_multiple_backtests
from lib.stock_filter import filter_stock, calculate_entry_score
from lib.prompt_generator import PromptGenerator
from utils.logging_config import setup_logging, cleanup_old_logs

# TODO: 全体的な機能強化
# - 複数銘柄の同時処理
# - エラーリトライの実装
# - パフォーマンス監視と最適化
# - 監査ログの実装
# - 定期実行の仕組み

# ロギングの設定
logger = setup_logging("stock_purchase")

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
    
    def __init__(self, max_ai_calls=40, min_entry_score=70.0, api_delay=30, test_mode=False, allow_position_increase=False):
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
            test_mode (bool): テストモードを有効にするかどうか
            allow_position_increase (bool): 保有銘柄の買い増しを許可するかどうか
        """
        load_dotenv()
        self.entry_repository = EntryRepository()
        # テストモード（実際の購入処理をスキップ）
        # 引数とコマンドライン引数と環境変数から設定を読み込む
        self.test_mode = test_mode or os.getenv('STOCK_TEST_MODE', 'false').lower() == 'true'
        self.judgment_handler = EntryJudgmentHandler(
            api_key=os.getenv('GEMINI_API_KEY'),
            logger=logger,
            test_mode=self.test_mode
        )
        self.logger = logger
        
        # 新しい設定パラメータ
        self.max_ai_calls = max_ai_calls
        self.min_entry_score = min_entry_score
        self.api_delay = api_delay
        # 買い増し設定
        self.allow_position_increase = allow_position_increase or os.getenv('ALLOW_POSITION_INCREASE', 'false').lower() == 'true'
        if self.allow_position_increase:
            self.logger.info("買い増しモードが有効です。保有中の銘柄も候補に含めます。")
        
        if self.test_mode:
            self.logger.info("テストモードが有効です。実際の購入処理はスキップされます。")
            # テストモードの場合はブラウザ操作クラスの初期化をスキップ
            self.browser_handler = None
        else:
            # 通常モードの場合はブラウザ操作クラスを初期化
            self.browser_handler = EntryBrowserUse(logger=logger)
        
        # プロンプト生成器を初期化
        self.prompt_generator = PromptGenerator()
        
        # 資金管理クラスの初期化（利用時に実際の値で初期化）
        self.fund_manager = None

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
        # 環境変数を再読み込み
        load_dotenv(override=True)
        
        # 買い増し許可モードかどうかで異なるSQLクエリを実行
        if self.allow_position_increase:
            candidates = self.entry_repository.fetch_entry_candidates_with_holdings()
            self.logger.info("買い増しモード有効: 保有中の銘柄も候補に含めます")
        else:
            candidates = self.entry_repository.fetch_best_entry_candidates()
            self.logger.info("買い増しモード無効: 保有中の銘柄は候補から除外します")
            
        if not candidates:
            self.logger.info("エントリー候補が見つかりませんでした")
            return []
            
        # 環境変数の値をログ出力
        env_limit = os.getenv("ENTRY_CANDIDATE_LIMIT")
        self.logger.info(f"現在のENTRY_CANDIDATE_LIMIT: {env_limit}")
        
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
            
            # 企業情報を取得して業種名を特定
            stock_util = StockUtil()
            five_digit_code = f"{stock_code}0"  # 末尾に0を追加
            company_info = stock_util.get_company_info(five_digit_code)
            if not company_info:
                self.logger.error(f"企業情報が見つかりません: {stock_code} (5桁コード: {five_digit_code})")
                return {}

            # 業種名を取得（company_infoの5番目の要素が業種名）
            japanese_industry_name = company_info[5]
            
            try:
                # 日本語の業種名を英語に変換
                industry_name = TableCategory.get_table_prefix(japanese_industry_name)
            except ValueError as e:
                self.logger.error(f"業種名の変換に失敗: {japanese_industry_name}, エラー: {e}")
                return {}
            
            # バックテスト実行
            backtest_results = run_multiple_backtests(str(stock_code), industry_name)
            
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
                
                # トレード情報に profit キーが存在しない場合は計算して追加
                for trade in trades:
                    try:
                        if "profit" not in trade:
                            if "entry_price" in trade and "exit_price" in trade and "lot" in trade:
                                entry_price = float(trade["entry_price"])
                                exit_price = float(trade["exit_price"])
                                lot = float(trade["lot"])
                                trade["profit"] = (exit_price - entry_price) * lot
                                self.logger.debug(f"profitキーを計算して追加: entry={entry_price}, exit={exit_price}, lot={lot}, profit={trade['profit']}")
                            else:
                                # entry_priceかexit_priceが欠けている場合はprofitを0に設定
                                missing_keys = []
                                if "entry_price" not in trade:
                                    missing_keys.append("entry_price")
                                if "exit_price" not in trade:
                                    missing_keys.append("exit_price")
                                if "lot" not in trade:
                                    missing_keys.append("lot")
                                self.logger.warning(f"トレード情報に必要なキーが欠けているため、profitを0に設定します: {', '.join(missing_keys)}")
                                trade["profit"] = 0
                    except Exception as e:
                        self.logger.error(f"profitの計算中にエラーが発生: {e}")
                        trade["profit"] = 0
                
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
                win_count = sum(1 for trade in trades if "profit" in trade and trade["profit"] > 0)
                loss_count = sum(1 for trade in trades if "profit" in trade and trade["profit"] <= 0)
                total_strategy_profit = sum(trade.get("profit", 0) for trade in trades)
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
            
            # 文字列型のデータを数値型に変換
            try:
                # closeが文字列の場合は数値に変換
                if 'close' in candidate and isinstance(candidate['close'], str):
                    candidate['close'] = float(candidate['close'])
            except (ValueError, TypeError) as e:
                self.logger.error(f"{stock_code}: 数値変換エラー: {e}")
                continue
            
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
            
            # プロンプト生成前の最新技術指標データを確認
            self.logger.debug(f"AI判断前の最新技術指標データ: {latest_data}")
            self.logger.debug(f"ADX値: {latest_data.get('adx', 'データなし')}")
            
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
        1. 買付余力の確認
        2. エントリー候補の取得
        3. 基本フィルタリングで候補を絞り込み
        4. 残った候補にスコアを付け、上位候補を選択
        5. 選択された候補に対してAIによるエントリー判断を実施
        6. 推奨された候補について実際の購入処理を実行
        7. 1件でも購入が成功すれば True を返し、すべて失敗の場合は False を返す

        Returns:
            bool: 購入成功で True、すべて失敗または候補がない場合は False
        """
        try:
            # 1. 買付余力を取得し、資金管理クラスを初期化
            self.logger.info("買付余力の確認")
            available_funds = self.entry_repository.get_available_funds(test_mode=self.test_mode)
            self.fund_manager = FundManager(available_funds, logger=self.logger)
            
            if available_funds <= 0:
                self.logger.warning("買付余力がありません")
                return False
            
            self.logger.info(f"買付余力: {available_funds:,}円")

            # 2. エントリー候補を全件取得
            self.logger.info("エントリー候補の取得を開始")
            candidates = self._get_entry_candidate()
            if not candidates:
                self.logger.info("エントリー候補が見つかりませんでした")
                return False
            self.logger.info(f"取得完了: {len(candidates)}件のエントリー候補")

            # 3. 候補にスコアを付け、上位候補を選択
            self.logger.info("候補のスコアリングを実行")
            scored_candidates = self._score_candidates(candidates)
            
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
                        technical_data=historical_data,
                        entry_score=entry_score,
                        available_funds=self.fund_manager.get_available_funds(),  # 最新の利用可能資金を使用
                        api_response_data=candidate
                    )
                
                # プロンプト生成前の最新技術指標データを確認
                latest_data = historical_data[-1] if historical_data else {}
                self.logger.debug(f"AI判断前の最新技術指標データ: {latest_data}")
                self.logger.debug(f"ADX値: {latest_data.get('adx', 'データなし')}")
                
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

                # エントリー情報の共通設定
                from datetime import datetime
                candidate['entry_date'] = datetime.now().strftime('%Y-%m-%d')
                candidate['status'] = 'active'  # 新規エントリーは'active'ステータス
                candidate['reason'] = judgment.get('reasoning', '理由なし')  # AIの判断理由を設定
                candidate['position'] = judgment.get('position', 'hold') # ★ AIの判断結果からpositionを取得し、candidateに追加 (デフォルトは hold)
                
                # AIの判断結果から保有期間を設定
                rule = judgment.get('rule', {})
                holding_period = rule.get('period')
                if holding_period and holding_period != 'NG':
                    try:
                        candidate['holding_period'] = int(holding_period)
                    except (ValueError, TypeError):
                        candidate['holding_period'] = 5  # 変換エラー時はデフォルト値
                else:
                    candidate['holding_period'] = 5  # AIが判断できない場合のデフォルト値
                
                self.logger.info(f"保有期間を設定: {candidate['holding_period']}日")

                # AIの判断結果から価格情報を設定
                entry_price = rule.get('entryPrice')
                stop_loss = rule.get('stop_loss')
                target_price = rule.get('target_price')
                risk_reward = rule.get('risk_reward')

                # 価格情報の検証と設定
                if entry_price and entry_price != 'NG':
                    try:
                        candidate['entry_price'] = float(entry_price)
                    except (ValueError, TypeError):
                        self.logger.error(f"エントリー価格の変換に失敗: {entry_price}")
                        continue
                else:
                    self.logger.error("エントリー価格が指定されていません")
                    continue

                if stop_loss and stop_loss != 'NG':
                    try:
                        candidate['stop_loss'] = float(stop_loss)
                    except (ValueError, TypeError):
                        self.logger.error(f"損切り価格の変換に失敗: {stop_loss}")
                        continue
                else:
                    self.logger.error("損切り価格が指定されていません")
                    continue

                if target_price and target_price != 'NG':
                    try:
                        candidate['target_price'] = float(target_price)
                    except (ValueError, TypeError):
                        self.logger.error(f"目標価格の変換に失敗: {target_price}")
                        continue
                else:
                    self.logger.error("目標価格が指定されていません")
                    continue

                if risk_reward and risk_reward != 'NG':
                    try:
                        candidate['risk_reward'] = float(risk_reward)
                    except (ValueError, TypeError):
                        self.logger.error(f"リスクリワード比の変換に失敗: {risk_reward}")
                        continue
                else:
                    self.logger.error("リスクリワード比が指定されていません")
                    continue

                # AIの判断結果から購入株数を設定
                quantity = rule.get('quantity')
                if quantity and quantity != 'NG':
                    try:
                        candidate['quantity'] = int(quantity)
                    except (ValueError, TypeError):
                        self.logger.error(f"購入株数の変換に失敗: {quantity}")
                        continue
                else:
                    self.logger.error("購入株数が指定されていません")
                    continue

                # 購入金額の計算と資金チェック
                purchase_cost = candidate['entry_price'] * candidate['quantity']
                if not self.fund_manager.can_purchase(purchase_cost):
                    self.logger.warning(f"候補 {stock_code}: 利用可能資金不足のためスキップ（必要額: {purchase_cost:,.0f}円、残額: {self.fund_manager.get_available_funds():,.0f}円）")
                    continue

                # 資金の予約
                if not self.fund_manager.reserve_funds(stock_code, purchase_cost):
                    self.logger.error(f"候補 {stock_code}: 資金予約に失敗")
                    continue

                # 5. 推奨された候補についてエントリーを実行
                if self.test_mode:
                    self.logger.info(f"テストモード: 候補 {stock_code} の実際の購入処理をスキップします")
                    candidate['is_test'] = True
                    if self.entry_repository.save_entry_info(candidate):
                        any_success = True
                    else:
                        # エントリー保存失敗の場合は資金予約を解除
                        self.fund_manager.release_reservation(stock_code)
                else:
                    # ブラウザ操作クラスが初期化されていない場合はエラーを出力
                    if self.browser_handler is None:
                        self.logger.error(f"ブラウザ操作クラスが初期化されていません。候補 {stock_code} のエントリーをスキップします。")
                        self.fund_manager.release_reservation(stock_code)
                        continue
                        
                    success = self.browser_handler.execute_entry(candidate)
                    if success:
                        if self.entry_repository.save_entry_info(candidate):
                            self.logger.info(f"エントリー成功: {stock_code}")
                            any_success = True
                        else:
                            # エントリー保存失敗の場合は資金予約を解除
                            self.fund_manager.release_reservation(stock_code)
                            self.logger.error(f"エントリー保存失敗: {stock_code}")
                    else:
                        # 購入失敗の場合は資金予約を解除
                        self.fund_manager.release_reservation(stock_code)
                        self.logger.error(f"エントリー失敗: {stock_code}")

            return any_success

        except Exception as e:
            self.logger.error(f"購入処理中にエラーが発生: {e}", exc_info=True)
            # 例外発生時は念のためすべての資金予約を解除
            if self.fund_manager:
                self.fund_manager.clear_pending_purchases()
            return False


# 同期実行用のエントリーポイント
def main():
    """
    メイン処理
    
    コマンドライン引数:
        --test: テストモードを有効にする
        --show-history: テストモードの取引履歴を表示
        --show-summary: テストモードのサマリーを表示
        --reset-test: テストデータをリセット
        --initial-funds: テストデータリセット時の初期資金（デフォルト: 1,000,000円）
        --max-calls: AI判断の最大件数（デフォルト: 50件）
        --min-score: エントリースコアの最低値（デフォルト: 70.0）
        --api-delay: API呼び出し間の待機時間（デフォルト: 30秒）
        --allow-position-increase: 保有銘柄の買い増しを許可する
        --debug: デバッグモードを有効にする
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='株式購入処理を実行します')
    parser.add_argument('--test', action='store_true', help='テストモードを有効にする')
    parser.add_argument('--show-history', action='store_true', help='テストモードの取引履歴を表示')
    parser.add_argument('--show-summary', action='store_true', help='テストモードのサマリーを表示')
    parser.add_argument('--reset-test', action='store_true', help='テストデータをリセット')
    parser.add_argument('--initial-funds', type=float, default=1000000.0, help='テストデータリセット時の初期資金')
    parser.add_argument('--max-calls', type=int, default=50, help='AI判断の最大件数')
    parser.add_argument('--min-score', type=float, default=70.0, help='エントリースコアの最低値')
    parser.add_argument('--api-delay', type=int, default=30, help='API呼び出し間の待機時間（秒）')
    parser.add_argument('--allow-position-increase', action='store_true', help='保有銘柄の買い増しを許可する')
    parser.add_argument('--debug', action='store_true', help='デバッグモードを有効にする')
    
    args = parser.parse_args()
    
    # デバッグモードが有効な場合は追加の情報を表示
    if args.debug:
        print("\n=== 実行時デバッグ情報 ===")
        print(f"コマンドライン引数: {sys.argv}")
        print(f"解析された引数: {args}")
        print(f"実行時のPYTHONPATH: {sys.path}")
        print(f"実行時のカレントディレクトリ: {os.getcwd()}")
        try:
            import dotenv
            print(f"python-dotenv バージョン: {dotenv.__version__}")
            print(f"dotenv の場所: {dotenv.__file__}")
        except ImportError as e:
            print(f"python-dotenv インポートエラー: {e}")
        print("=====================\n")
    
    # EntryRepositoryのインスタンス化
    entry_repository = EntryRepository()
    
    # テスト関連の機能を実行
    if args.show_history:
        history = entry_repository.get_test_trade_history()
        if history:
            print("\n=== テストモード取引履歴 ===")
            for trade in history:
                print(f"取引ID: {trade['trade_id']}")
                print(f"日時: {trade['created_at']}")
                print(f"種別: {trade['trade_type']}")
                print(f"銘柄: {trade['symbol_code']}")
                print(f"価格: {trade['entry_price']:,.0f}円")
                print(f"数量: {trade['quantity']}株")
                if trade['trade_type'] == 'sell':
                    print(f"損益: {trade['profit_loss']:,.0f}円")
                print(f"残高: {trade['available_funds']:,.0f}円")
                print("---")
        else:
            print("テストモードの取引履歴がありません")
        return
        
    if args.show_summary:
        summary = entry_repository.get_test_summary()
        if summary['test_start']:
            print("\n=== テストモードサマリー ===")
            print(f"テスト期間: {summary['test_start']} ～ {summary['test_end']}")
            print(f"初期資金: {summary['initial_funds']:,.0f}円")
            print(f"現在資金: {summary['current_funds']:,.0f}円")
            print(f"総損益: {summary['total_profit']:,.0f}円")
            print(f"取引回数: {summary['trade_count']}回")
            print(f"勝ち取引: {summary['win_count']}回")
            if summary['trade_count'] > 0:
                win_rate = (summary['win_count'] / summary['trade_count']) * 100
                print(f"勝率: {win_rate:.1f}%")
        else:
            print("テストモードのサマリー情報がありません")
        return
        
    if args.reset_test:
        if entry_repository.reset_test_data(args.initial_funds):
            print(f"テストデータをリセットしました。初期資金: {args.initial_funds:,.0f}円")
        else:
            print("テストデータのリセットに失敗しました")
        return
    
    # 通常の購入処理を実行
    manager = StockPurchaseManager(
        test_mode=args.test,
        max_ai_calls=args.max_calls,
        min_entry_score=args.min_score,
        api_delay=args.api_delay,
        allow_position_increase=args.allow_position_increase
    )
    success = manager.execute_purchase()
    
    if success:
        print("購入処理が完了しました")
    else:
        print("購入処理が失敗しました")
        sys.exit(1)

if __name__ == "__main__":
    main() 