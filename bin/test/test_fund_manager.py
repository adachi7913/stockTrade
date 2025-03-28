import os
import sys
import unittest

# ルートディレクトリの取得とPythonパスの設定
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 3階層上がルート
sys.path.insert(0, root_dir)  # 最優先でルートディレクトリを検索パスに追加
print(f"ルートディレクトリ: {root_dir}")
os.chdir(root_dir)  # カレントディレクトリの移動

from repository.fund_manager import FundManager

class TestFundManager(unittest.TestCase):
    """
    FundManager（資金管理クラス）のテスト
    
    複数銘柄購入時の資金予約と管理機能をテスト
    """
    
    def setUp(self):
        """
        各テスト前の準備
        """
        # テスト用にロガーなしで初期化
        self.initial_funds = 1000000  # 初期資金 100万円
        self.fund_manager = FundManager(self.initial_funds)
        
    def test_initialization(self):
        """
        初期化時の資金設定が正しいことをテスト
        """
        self.assertEqual(self.fund_manager.get_available_funds(), self.initial_funds)
        self.assertEqual(len(self.fund_manager.get_pending_purchases()), 0)
        
    def test_can_purchase(self):
        """
        購入可否判定が正しく動作することをテスト
        """
        # 資金の範囲内なのでTrue
        self.assertTrue(self.fund_manager.can_purchase(500000))
        
        # 資金ぴったりでもTrue
        self.assertTrue(self.fund_manager.can_purchase(1000000))
        
        # 資金を超えるのでFalse
        self.assertFalse(self.fund_manager.can_purchase(1000001))
        
    def test_reserve_funds(self):
        """
        資金予約機能が正しく動作することをテスト
        """
        # 最初の予約（成功）
        self.assertTrue(self.fund_manager.reserve_funds("1234", 300000))
        self.assertEqual(self.fund_manager.get_available_funds(), 700000)
        
        # 2つ目の予約（成功）
        self.assertTrue(self.fund_manager.reserve_funds("5678", 400000))
        self.assertEqual(self.fund_manager.get_available_funds(), 300000)
        
        # 3つ目の予約（成功）
        self.assertTrue(self.fund_manager.reserve_funds("9012", 300000))
        self.assertEqual(self.fund_manager.get_available_funds(), 0)
        
        # 4つ目の予約（資金不足で失敗）
        self.assertFalse(self.fund_manager.reserve_funds("3456", 100000))
        self.assertEqual(self.fund_manager.get_available_funds(), 0)
        
        # 予約リストを確認
        pending = self.fund_manager.get_pending_purchases()
        self.assertEqual(len(pending), 3)
        self.assertEqual(pending[0]['symbol'], "1234")
        self.assertEqual(pending[0]['cost'], 300000)
        
    def test_release_reservation(self):
        """
        特定の資金予約解除機能が正しく動作することをテスト
        """
        # 複数の予約を行う
        self.fund_manager.reserve_funds("1234", 200000)
        self.fund_manager.reserve_funds("5678", 300000)
        self.fund_manager.reserve_funds("9012", 100000)
        
        # 特定の予約を解除
        released = self.fund_manager.release_reservation("5678")
        self.assertEqual(released, 300000)
        self.assertEqual(self.fund_manager.get_available_funds(), 700000)
        
        # 予約リストを確認（5678が削除されていることを確認）
        pending = self.fund_manager.get_pending_purchases()
        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0]['symbol'], "1234")
        self.assertEqual(pending[1]['symbol'], "9012")
        
        # 存在しない予約の解除（解除されず0が返る）
        released = self.fund_manager.release_reservation("XXXX")
        self.assertEqual(released, 0)
        self.assertEqual(self.fund_manager.get_available_funds(), 700000)
        
    def test_clear_pending_purchases(self):
        """
        全資金予約解除機能が正しく動作することをテスト
        """
        # 複数の予約を行う
        self.fund_manager.reserve_funds("1234", 200000)
        self.fund_manager.reserve_funds("5678", 300000)
        self.fund_manager.reserve_funds("9012", 100000)
        
        # 全予約を解除
        total_released = self.fund_manager.clear_pending_purchases()
        self.assertEqual(total_released, 600000)
        self.assertEqual(self.fund_manager.get_available_funds(), self.initial_funds)
        
        # 予約リストが空になっていることを確認
        self.assertEqual(len(self.fund_manager.get_pending_purchases()), 0)
        
    def test_multiple_purchases_scenario(self):
        """
        複数銘柄購入時のシナリオをテスト
        """
        # 1つ目の銘柄購入を試行（成功）
        stock1_cost = 400000
        if self.fund_manager.can_purchase(stock1_cost):
            self.fund_manager.reserve_funds("1234", stock1_cost)
            # 銘柄1の購入処理が成功したと仮定
        
        # 2つ目の銘柄購入を試行（成功）
        stock2_cost = 350000
        if self.fund_manager.can_purchase(stock2_cost):
            self.fund_manager.reserve_funds("5678", stock2_cost)
            # 銘柄2の購入処理が成功したと仮定
        
        # 3つ目の銘柄購入を試行（資金不足で失敗）
        stock3_cost = 300000
        if self.fund_manager.can_purchase(stock3_cost):
            self.fund_manager.reserve_funds("9012", stock3_cost)
            # 実行されない（資金不足）
        
        # 最終的な残高と購入数確認
        self.assertEqual(self.fund_manager.get_available_funds(), 250000)  # 残り25万円
        self.assertEqual(len(self.fund_manager.get_pending_purchases()), 2)  # 2銘柄購入

if __name__ == '__main__':
    unittest.main() 