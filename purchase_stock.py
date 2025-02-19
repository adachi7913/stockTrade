import logging
from typing import Dict, List
import os
from dotenv import load_dotenv
import time

from repository.entry_repository import EntryRepository
from Gemini.entry_judgment_handler import EntryJudgmentHandler
from browser_use.entry_browser_use import EntryBrowserUse
from repository.stock_repository import StockRepository
from utils.stock_util import StockUtil
from lib.table_category import TableCategory

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
    
    def __init__(self):
        """
        初期化処理
        
        - .envファイルから環境変数を読み込み
        - 各種コンポーネントの初期化:
          - EntryRepository: エントリー情報の管理
          - EntryJudgmentHandler: Gemini APIによる判断
          - EntryBrowserUse: ブラウザ操作による購入実行
        """
        load_dotenv()
        self.entry_repository = EntryRepository()
        self.judgment_handler = EntryJudgmentHandler(
            api_key=os.getenv('GEMINI_API_KEY'),
            logger=logger
        )
        self.browser_handler = EntryBrowserUse(logger=logger)
        self.logger = logger

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

    def execute_purchase(self) -> bool:
        """
        株式購入処理を実行

        処理フロー:
        1. エントリー候補の取得
           - 複数の候補を取得し、候補が見つからない場合は処理を中断
        2. 各候補に対して過去データの取得、AIによるエントリー判断、実際の購入処理を実施
        3. 1件でも購入が成功すれば True を返し、すべて失敗の場合は False を返す

        Returns:
            bool: 購入成功で True、すべて失敗または候補がない場合は False
        """
        try:
            # エントリー候補を全件取得
            candidates = self._get_entry_candidate()
            if not candidates:
                return False

            any_success = False
            # 取得した複数の候補に対してループ処理
            for candidate in candidates:
                # 過去の価格データを取得
                historical_data = self._get_historical_data(candidate['code'])
                if not historical_data:
                    self.logger.error(f"候補 {candidate['code']} の過去データが取得できませんでした")
                    continue

                # Gemini APIでエントリー判断
                judgment = self.judgment_handler.judge_entry(candidate, historical_data)
                
                # API利用後に30秒スリープしてリクエスト制限を回避

                if not judgment['should_enter']:
                    self.logger.info(f"候補 {candidate['code']} はエントリー見送り: {judgment['reasoning']}")
                    continue

                time.sleep(30)
                # エントリーを実行
                success = self.browser_handler.execute_entry(candidate)
                if success:
                    # エントリー情報を保存
                    self.entry_repository.save_entry_info(candidate)
                    self.logger.info(f"エントリー成功: {candidate['code']}")
                    any_success = True
                else:
                    self.logger.error(f"エントリー失敗: {candidate['code']}")

            return any_success

        except Exception as e:
            self.logger.error(f"購入処理中にエラーが発生: {e}")
            return False

# 同期実行用のエントリーポイント
def main():
    manager = StockPurchaseManager()
    success = manager.execute_purchase()
    if success:
        logger.info("株式購入処理が完了しました")
    else:
        logger.info("株式購入処理は実行されませんでした")

if __name__ == "__main__":
    main() 