import unittest
from datetime import datetime, date
from repository.entry_repository import EntryRepository

class TestEntryRepository(unittest.TestCase):
    def setUp(self):
        """
        テストの前処理
        """
        self.repository = EntryRepository()
        # テストデータをリセット
        self.repository.reset_test_data(initial_funds=1000000.0)
        
    def tearDown(self):
        """
        テストの後処理
        """
        # テストデータをクリーンアップ
        self.repository.reset_test_data()
        self.repository.close()
        
    def test_get_available_funds(self):
        """
        get_available_fundsメソッドのテスト
        """
        # テストモードの資金を取得
        test_funds = self.repository.get_available_funds(test_mode=True)
        self.assertEqual(test_funds, 1000000.0)
        
        # 本番モードの資金を取得（データがない場合は0を返す）
        prod_funds = self.repository.get_available_funds(test_mode=False)
        self.assertEqual(prod_funds, 0.0)
        
    def test_get_test_trade_history(self):
        """
        get_test_trade_historyメソッドのテスト
        """
        # 初期状態では履歴が空
        history = self.repository.get_test_trade_history()
        self.assertEqual(len(history), 1)  # 初期資金設定のレコードのみ
        
        # テストデータを追加（実際のトレード処理を通じて）
        entry_data = {
            'code': '1301',
            'entry_date': date.today(),
            'entry_price': 1000.0,
            'stop_loss': 950.0,
            'target_price': 1100.0,
            'reason': 'テスト用エントリー',
            'holding_period': '5',
            'risk_reward': 2.0,
            'quantity': 100,
            'status': 'active',
            'is_test': True
        }
        self.repository.save_entry_info(entry_data)
        
        # 履歴を再取得
        history = self.repository.get_test_trade_history()
        self.assertGreater(len(history), 1)
        
        # 最新の取引を確認
        latest_trade = history[0]
        self.assertEqual(latest_trade['symbol_code'], '1301')
        self.assertEqual(latest_trade['trade_type'], 'buy')
        self.assertEqual(latest_trade['entry_price'], 1000.0)
        self.assertEqual(latest_trade['quantity'], 100)
        
    def test_get_test_summary(self):
        """
        get_test_summaryメソッドのテスト
        """
        # 初期状態のサマリーを取得
        summary = self.repository.get_test_summary()
        self.assertEqual(summary['initial_funds'], 1000000.0)
        self.assertEqual(summary['current_funds'], 1000000.0)
        self.assertEqual(summary['total_profit'], 0.0)
        self.assertEqual(summary['trade_count'], 0)
        self.assertEqual(summary['win_count'], 0)
        self.assertIsNotNone(summary['test_start'])
        self.assertIsNotNone(summary['test_end'])
        
        # テストデータを追加（実際のトレード処理を通じて）
        entry_data = {
            'code': '1301',
            'entry_date': date.today(),
            'entry_price': 1000.0,
            'stop_loss': 950.0,
            'target_price': 1100.0,
            'reason': 'テスト用エントリー',
            'holding_period': '5',
            'risk_reward': 2.0,
            'quantity': 100,
            'status': 'active',
            'is_test': True
        }
        self.repository.save_entry_info(entry_data)
        
        # サマリーを再取得
        summary = self.repository.get_test_summary()
        self.assertEqual(summary['trade_count'], 1)
        
    def test_reset_test_data(self):
        """
        reset_test_dataメソッドのテスト
        """
        # テストデータを追加
        entry_data = {
            'code': '1301',
            'entry_date': date.today(),
            'entry_price': 1000.0,
            'stop_loss': 950.0,
            'target_price': 1100.0,
            'reason': 'テスト用エントリー',
            'holding_period': '5',
            'risk_reward': 2.0,
            'quantity': 100,
            'status': 'active',
            'is_test': True
        }
        self.repository.save_entry_info(entry_data)
        
        # リセット前の状態を確認
        history = self.repository.get_test_trade_history()
        self.assertGreater(len(history), 1)
        
        # データをリセット
        initial_funds = 2000000.0
        success = self.repository.reset_test_data(initial_funds)
        self.assertTrue(success)
        
        # リセット後の状態を確認
        history = self.repository.get_test_trade_history()
        self.assertEqual(len(history), 1)  # 初期資金設定のレコードのみ
        
        funds = self.repository.get_available_funds(test_mode=True)
        self.assertEqual(funds, initial_funds)

if __name__ == '__main__':
    unittest.main() 