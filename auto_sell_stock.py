#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
自動売却処理スクリプト

保有中の銘柄を自動的に評価し、売却条件を満たしている場合に売却処理を行います。
"""

import os
import sys
import logging
import datetime
import argparse
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
from dotenv import load_dotenv

from repository.entry_repository import EntryRepository
from repository.stock_repository import StockRepository
from service.backtest_service import BacktestService
from Gemini.entry_judgment_handler import EntryJudgmentHandler
from utils.logging_config import setup_logging
from lib.table_category import TableCategory

# .envファイルの読み込み
load_dotenv()

# ロガーの設定
logger = setup_logging("auto_sell_stock")

class AutoSellStock:
    """
    保有銘柄の自動売却を行うクラス
    """
    def __init__(self, test_mode: bool = False):
        """
        初期化
        
        Args:
            test_mode (bool): テスト実行モードかどうか
        """
        self.entry_repository = EntryRepository()
        self.stock_repository = StockRepository()
        self.backtest_service = BacktestService()
        
        # Gemini APIキーの取得
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("環境変数 GEMINI_API_KEY が設定されていません")
            
        self.entry_judgment = EntryJudgmentHandler(api_key=api_key, logger=logger)
        self.logger = logging.getLogger(__name__)
        self.test_mode = test_mode
        self.test_results = []  # テストモード時の結果を保存するリスト
        
    def get_active_entries(self) -> List[Dict]:
        """
        アクティブな（保有中の）エントリー情報を取得
        
        Returns:
            List[Dict]: アクティブなエントリー情報のリスト
        """
        try:
            active_entries = self.entry_repository.get_active_entries()
            if not active_entries:
                self.logger.info("アクティブなエントリーが見つかりません")
                return []
                
            self.logger.info(f"アクティブなエントリー数: {len(active_entries)}")
            return active_entries
            
        except Exception as e:
            self.logger.error(f"アクティブなエントリー取得中にエラー: {e}")
            return []
            
    def validate_stock_code(self, code: str) -> str:
        """
        銘柄コードを検証し、必要に応じて変換
        
        Args:
            code (str): 検証する銘柄コード
            
        Returns:
            str: 検証済みの銘柄コード
        """
        # 5桁コードの場合、末尾の0を削除して4桁に変換
        if len(code) == 5 and code.endswith('0'):
            return code[:-1]
        return code
        
    def evaluate_entry(self, entry: Dict) -> Tuple[bool, str, float]:
        """
        エントリーを評価し、売却すべきかどうかを判断
        
        Args:
            entry (Dict): 評価するエントリー情報
            
        Returns:
            Tuple[bool, str, float]: (売却すべきか, 理由, 現在価格)
        """
        try:
            # エントリー情報の取得
            code = entry['code']
            entry_price = float(entry['entry_price'])
            entry_date = entry['entry_date']
            lot_size = int(entry['quantity'])
            
            # 業種情報の取得
            industry_name = self.stock_repository.fetch_industry_name_prefix(code)
            if not industry_name:
                return False, f"業種情報が取得できません: {code}", 0
            
            # 銘柄コードの検証
            validated_code = self.validate_stock_code(code)
            
            # 最新の株価データを取得
            latest_price_data = self.stock_repository.get_latest_price(validated_code, industry_name)
            if not latest_price_data:
                return False, "最新の株価データが取得できません", 0
                
            current_price = float(latest_price_data['close'])
            current_date = latest_price_data['date']
            
            # 保有期間の計算
            holding_days = (current_date - entry_date).days
            
            # 損益率の計算
            profit_rate = ((current_price - entry_price) / entry_price) * 100
            
            # 売却判断ロジック
            # 1. 利益確定条件: 10%以上の利益
            if profit_rate >= 10:
                return True, f"利益確定: {profit_rate:.2f}%の利益", current_price
                
            # 2. 損切り条件: 5%以上の損失
            if profit_rate <= -5:
                return True, f"損切り: {profit_rate:.2f}%の損失", current_price
                
            # 3. 長期保有条件: 60日以上保有かつ利益がない
            if holding_days >= 60 and profit_rate <= 0:
                return True, f"長期保有かつ利益なし: {holding_days}日間保有, {profit_rate:.2f}%", current_price
                
            # 4. バックテスト結果による判断
            backtest_results = self.backtest_service.run_multiple_strategy_backtest(
                code=validated_code,
                industry_name=industry_name,
                period_years=1  # 直近1年のデータでバックテスト
            )
            
            # バックテスト結果の分析
            if backtest_results:
                # 直近の戦略パフォーマンスを評価
                recent_performance = [r for r in backtest_results if r['start_date'] >= (current_date - datetime.timedelta(days=365)).strftime('%Y-%m-%d')]
                
                # すべての戦略が負のリターンを示している場合は売却
                if recent_performance and all(r['return_percentage'] < 0 for r in recent_performance):
                    return True, "全戦略が負のリターンを示しています", current_price
            
            # 5. AIによる判断
            ai_judgment = self.entry_judgment.judge_exit_timing(
                code=validated_code,
                industry_name=industry_name,
                entry_price=entry_price,
                current_price=current_price,
                holding_days=holding_days
            )
            
            if ai_judgment.get('should_exit', False):
                return True, f"AI判断: {ai_judgment.get('reason', '理由なし')}", current_price
            
            # デフォルトでは保持を継続
            return False, f"保持継続: 現在の損益率 {profit_rate:.2f}%, 保有日数 {holding_days}日", current_price
            
        except Exception as e:
            self.logger.error(f"エントリー評価中にエラー: {e}")
            return False, f"エラー: {e}", 0
            
    def execute_sell(self, entry: Dict, current_price: float, reason: str) -> bool:
        """
        売却処理を実行
        
        Args:
            entry (Dict): 売却するエントリー情報
            current_price (float): 現在の株価
            reason (str): 売却理由
            
        Returns:
            bool: 売却処理が成功したかどうか
        """
        try:
            code = entry['code']
            lot_size = int(entry['quantity'])
            entry_price = float(entry['entry_price'])
            entry_date = entry['entry_date']
            
            # 損益計算
            profit = (current_price - entry_price) * lot_size
            profit_rate = ((current_price - entry_price) / entry_price) * 100
            
            # テストモードの場合は実際の売却処理をスキップ
            if self.test_mode:
                self.logger.info(f"【テストモード】売却シミュレーション: 銘柄={code}, 価格={current_price}, 利益={profit:,.0f}円 ({profit_rate:.2f}%), 理由={reason}")
                
                # テスト結果を保存
                self.test_results.append({
                    'code': code,
                    'entry_date': entry_date,
                    'lot_size': lot_size,
                    'entry_price': entry_price,
                    'exit_price': current_price,
                    'profit': profit,
                    'profit_rate': profit_rate,
                    'reason': reason,
                    'timestamp': datetime.datetime.now()
                })
                
                return True
            
            # 実モードの場合は売却情報をデータベースに記録 (status='sold'に更新)
            result = self.entry_repository.update_exit_info(
                code=code,
                entry_date=entry_date,
                exit_price=current_price,
                exit_date=datetime.date.today(),
                profit=profit,
                profit_rate=profit_rate,
                exit_reason=reason
            )
            
            if result:
                self.logger.info(f"売却処理成功: 銘柄={code}, 価格={current_price}, 利益={profit:,.0f}円 ({profit_rate:.2f}%), 理由={reason}")
                return True
            else:
                self.logger.error(f"売却処理失敗: 銘柄={code}")
                return False
                
        except Exception as e:
            self.logger.error(f"売却処理中にエラー: {e}")
            return False
            
    def run(self):
        """
        自動売却処理のメイン実行メソッド
        """
        try:
            if self.test_mode:
                self.logger.info("【テストモード】自動売却処理を開始します（売却はシミュレーションのみ）")
            else:
                self.logger.info("自動売却処理を開始します")
            
            # アクティブなエントリーを取得
            active_entries = self.get_active_entries()
            if not active_entries:
                self.logger.info("処理対象のエントリーがありません")
                return
                
            sell_count = 0
            hold_count = 0
            
            # 各エントリーを評価
            for entry in active_entries:
                code = entry['code']
                
                # 業種情報の取得
                industry_name = self.stock_repository.fetch_industry_name_prefix(code)
                if not industry_name:
                    self.logger.warning(f"業種情報が取得できないためスキップ: {code}")
                    continue
                
                self.logger.info(f"エントリー評価: 銘柄={code}, 業種={industry_name}")
                
                # 売却判断
                should_sell, reason, current_price = self.evaluate_entry(entry)
                
                if should_sell:
                    # 売却処理
                    if self.execute_sell(entry, current_price, reason):
                        sell_count += 1
                else:
                    self.logger.info(f"保持継続: 銘柄={code}, 理由={reason}")
                    hold_count += 1
            
            if self.test_mode:
                self.logger.info(f"【テストモード】自動売却処理完了: 売却候補={sell_count}件, 保持継続={hold_count}件")
                self._print_test_report()
            else:        
                self.logger.info(f"自動売却処理完了: 売却={sell_count}件, 保持継続={hold_count}件")
            
        except Exception as e:
            self.logger.error(f"自動売却処理中にエラー: {e}")
            
    def _print_test_report(self):
        """テストモードの結果レポートを出力"""
        if not self.test_results:
            self.logger.info("【テストレポート】売却候補はありませんでした")
            return
            
        self.logger.info("\n===== テスト実行モード 売却候補レポート =====")
        self.logger.info(f"実行日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"売却候補銘柄数: {len(self.test_results)}")
        
        total_profit = sum(r['profit'] for r in self.test_results)
        self.logger.info(f"合計予想利益: {total_profit:,.0f}円")
        
        self.logger.info("\n----- 売却候補一覧 -----")
        for idx, result in enumerate(self.test_results, 1):
            self.logger.info(f"候補 {idx}:")
            self.logger.info(f"  銘柄コード: {result['code']}")
            self.logger.info(f"  数量: {result['lot_size']}株")
            self.logger.info(f"  購入価格: {result['entry_price']:,.0f}円")
            self.logger.info(f"  売却価格: {result['exit_price']:,.0f}円")
            self.logger.info(f"  利益: {result['profit']:,.0f}円 ({result['profit_rate']:.2f}%)")
            self.logger.info(f"  売却理由: {result['reason']}")
            self.logger.info("  ---")
            
        self.logger.info("===== レポート終了 =====\n")
        
    def save_test_report(self, output_file: str = None):
        """
        テストモードの結果レポートをファイルに保存
        
        Args:
            output_file (str, optional): 出力ファイルパス。指定がない場合は自動生成
        """
        if not self.test_mode or not self.test_results:
            return
            
        if not output_file:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"auto_sell_test_report_{timestamp}.txt"
            
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("===== 自動売却テストレポート =====\n")
                f.write(f"実行日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"売却候補銘柄数: {len(self.test_results)}\n")
                
                total_profit = sum(r['profit'] for r in self.test_results)
                f.write(f"合計予想利益: {total_profit:,.0f}円\n\n")
                
                f.write("----- 売却候補一覧 -----\n")
                for idx, result in enumerate(self.test_results, 1):
                    f.write(f"候補 {idx}:\n")
                    f.write(f"  銘柄コード: {result['code']}\n")
                    f.write(f"  数量: {result['lot_size']}株\n")
                    f.write(f"  購入価格: {result['entry_price']:,.0f}円\n")
                    f.write(f"  売却価格: {result['exit_price']:,.0f}円\n")
                    f.write(f"  利益: {result['profit']:,.0f}円 ({result['profit_rate']:.2f}%)\n")
                    f.write(f"  売却理由: {result['reason']}\n")
                    f.write("  ---\n")
                    
                f.write("===== レポート終了 =====\n")
                
            self.logger.info(f"テストレポートを {output_file} に保存しました")
            
        except Exception as e:
            self.logger.error(f"テストレポート保存中にエラー: {e}")
            
def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='自動売却処理')
    parser.add_argument('--debug', action='store_true', help='デバッグモードで実行')
    parser.add_argument('--test', '-t', action='store_true', help='テスト実行モード（売却処理を実行せずシミュレーションのみ）')
    parser.add_argument('--output', '-o', help='テストモード時のレポート出力ファイル')
    args = parser.parse_args()
    
    # デバッグモードの設定
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        
    try:
        # 自動売却処理の実行
        auto_sell = AutoSellStock(test_mode=args.test)
        auto_sell.run()
        
        # テストモードの場合、レポートを保存
        if args.test and args.output:
            auto_sell.save_test_report(args.output)
        elif args.test:
            auto_sell.save_test_report()
        
    except Exception as e:
        logger.error(f"実行中にエラーが発生しました: {e}")
        sys.exit(1)
        
if __name__ == "__main__":
    main() 