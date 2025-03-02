#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
自動売却処理スクリプト

保有中の銘柄を自動的に評価し、売却条件を満たしている場合に売却処理を行います。

実行モード:
- 通常モード: 売却条件を満たした銘柄に対して実際に売却処理を実行します
- テストモード: 売却判断は行いますが、実際の売却処理は行いません（シミュレーションのみ）
- 強制売却テストモード: 売却判断をスキップして強制的に売却操作をテストします

実行方法:
python auto_sell_stock.py [オプション]

オプション:
--test, -t        : テストモードで実行（売却処理を実行せずシミュレーションのみ）
--force-sell, -f  : 売却判断をスキップして強制的に売却処理のみをテストするモード
--output, -o FILE : テストモード時のレポート出力ファイル
--debug           : デバッグモードで実行（詳細なログを出力）
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
import traceback

from repository.entry_repository import EntryRepository
from repository.stock_repository import StockRepository
from service.backtest_service import BacktestService
from Gemini.entry_judgment_handler import EntryJudgmentHandler
from browser_use.sell_browser_use import SellBrowserUse
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
    def __init__(self, test_mode: bool = False, force_sell_test: bool = False, logger=None):
        """
        初期化
        
        Args:
            test_mode (bool): テスト実行モードかどうか
            force_sell_test (bool): 売却判断をスキップして強制的に売却処理のみをテストするモード
            logger (logging.Logger, optional): 使用するロガー。指定がなければ新しいロガーを設定
        """
        self.entry_repository = EntryRepository()
        self.stock_repository = StockRepository()
        self.backtest_service = BacktestService()
        
        # ロガーの設定
        self.logger = logger if logger else setup_logging("auto_sell_stock")
        
        # Gemini APIキーの取得
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("環境変数 GEMINI_API_KEY が設定されていません")
            
        self.entry_judgment = EntryJudgmentHandler(api_key=api_key, logger=self.logger)
        self.test_mode = test_mode
        self.force_sell_test = force_sell_test
        self.test_results = []  # テストモード時の結果を保存するリスト
        
        # テストモードでは実際のブラウザ操作をスキップ
        if self.test_mode:
            self.logger.info("テストモードが有効です。実際の売却処理はブラウザ操作を行いません。")
            self.browser_handler = None
        else:
            # 通常モードの場合はブラウザ操作クラスを初期化
            self.logger.info("ブラウザ操作による売却処理を有効化します。")
            self.browser_handler = SellBrowserUse(logger=self.logger)
        
    def get_active_entries(self) -> List[Dict]:
        """
        アクティブな（保有中の）エントリー情報を取得
        
        Returns:
            List[Dict]: アクティブなエントリー情報のリスト
        """
        try:
            self.logger.info("アクティブなエントリー情報の取得を開始します")
            active_entries = self.entry_repository.get_active_entries()
            if not active_entries:
                self.logger.info("アクティブなエントリーが見つかりません")
                return []
                
            self.logger.info(f"アクティブなエントリー数: {len(active_entries)}")
            # エントリー情報のサマリーをログ出力
            for idx, entry in enumerate(active_entries, 1):
                self.logger.info(f"エントリー {idx}: 銘柄={entry['code']}, 購入日={entry['entry_date']}, 購入価格={entry['entry_price']}")
            return active_entries
            
        except Exception as e:
            self.logger.error(f"アクティブなエントリー取得中にエラー: {e}", exc_info=True)
            return []
    
    def convert_to_companies_code(self, code: str) -> str:
        """
        companiesテーブル用に銘柄コードを5桁に変換
        
        Args:
            code (str): 元の銘柄コード
            
        Returns:
            str: companiesテーブル用の5桁コード
        """
        # 4桁コードの場合、末尾に"0"を追加して5桁にする
        if len(code) == 4:
            return code + "0"
        return code
            
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
            
            self.logger.info(f"銘柄 {code} の売却判断を開始します")
            
            # 業種情報の取得（5桁コードに変換してアクセス）
            # fetch_industry_name_prefix は既にテーブル接頭辞を返すため、そのまま使用
            companies_code = self.convert_to_companies_code(code)
            self.logger.debug(f"companies用コードに変換: {code} -> {companies_code}")
            
            table_prefix = self.stock_repository.fetch_industry_name_prefix(companies_code)
            if not table_prefix:
                self.logger.error(f"業種情報が取得できません: {code} (companies用コード: {companies_code})")
                return False, f"業種情報が取得できません: {code} (companies用コード: {companies_code})", 0
            
            self.logger.info(f"業種情報取得成功: 銘柄={code}, 業種={table_prefix}")
            
            # 銘柄コードの検証（株価データ取得用に4桁に変換）
            validated_code = self.validate_stock_code(code)
            self.logger.debug(f"株価データ取得用コードに変換: {code} -> {validated_code}")
            
            # 最新の株価データを取得（table_prefixは既に英語のテーブル接頭辞）
            self.logger.info(f"最新株価データ取得開始: 銘柄={validated_code}, 業種={table_prefix}")
            latest_price_data = self.stock_repository.get_latest_price(validated_code, table_prefix)
            if not latest_price_data:
                self.logger.error(f"最新の株価データが取得できません: {validated_code}")
                return False, "最新の株価データが取得できません", 0
                
            current_price = float(latest_price_data['close'])
            current_date = latest_price_data['date']
            self.logger.info(f"最新株価: {current_price}円 (日付: {current_date})")
            
            # 保有期間の計算
            holding_days = (current_date - entry_date).days
            
            # 損益率の計算
            profit_rate = ((current_price - entry_price) / entry_price) * 100
            self.logger.info(f"現在の状況: 保有期間={holding_days}日, 購入価格={entry_price}円, 現在価格={current_price}円, 損益率={profit_rate:.2f}%")
            
            # 売却判断ロジック
            # 1. 利益確定条件: 10%以上の利益
            if profit_rate >= 10:
                self.logger.info(f"売却判断: 利益確定条件に合致 ({profit_rate:.2f}% >= 10%)")
                return True, f"利益確定: {profit_rate:.2f}%の利益", current_price
                
            # 2. 損切り条件: 5%以上の損失
            if profit_rate <= -5:
                self.logger.info(f"売却判断: 損切り条件に合致 ({profit_rate:.2f}% <= -5%)")
                return True, f"損切り: {profit_rate:.2f}%の損失", current_price
                
            # 3. 長期保有条件: 60日以上保有かつ利益がない
            if holding_days >= 60 and profit_rate <= 0:
                self.logger.info(f"売却判断: 長期保有条件に合致 (保有日数={holding_days}日 >= 60日, 損益率={profit_rate:.2f}% <= 0%)")
                return True, f"長期保有かつ利益なし: {holding_days}日間保有, {profit_rate:.2f}%", current_price
                
            # 4. バックテスト結果による判断
            self.logger.info(f"バックテスト分析開始: 銘柄={validated_code}")
            backtest_results = self.backtest_service.run_multiple_strategy_backtest(
                code=validated_code,
                industry_name=table_prefix,  # 英語のテーブル接頭辞を使用
                period_years=1  # 直近1年のデータでバックテスト
            )
            
            # バックテスト結果の分析
            if backtest_results:
                self.logger.info(f"バックテスト結果取得成功: 結果数={len(backtest_results)}")
                # 直近の戦略パフォーマンスを評価
                recent_performance = [r for r in backtest_results if r['start_date'] >= (current_date - datetime.timedelta(days=365)).strftime('%Y-%m-%d')]
                
                self.logger.info(f"直近の戦略パフォーマンス評価: 評価対象数={len(recent_performance)}")
                
                # すべての戦略が負のリターンを示している場合は売却
                if recent_performance and all(r['return_percentage'] < 0 for r in recent_performance):
                    self.logger.info("売却判断: すべての戦略が負のリターンを示しています")
                    return True, "全戦略が負のリターンを示しています", current_price
            else:
                self.logger.warning("バックテスト結果が取得できませんでした")
            
            # 5. AIによる判断
            self.logger.info(f"AI判断開始: 銘柄={validated_code}")
            try:
                self.logger.debug(f"AI判断直前のプロセス状態: industry_name={table_prefix}, entry_price={entry_price}, current_price={current_price}, holding_days={holding_days}")
                
                ai_judgment = self.entry_judgment.judge_exit_timing(
                    code=validated_code,
                    industry_name=table_prefix,  # 英語のテーブル接頭辞を使用
                    entry_price=entry_price,
                    current_price=current_price,
                    holding_days=holding_days
                )
                
                self.logger.debug(f"AI判断結果: {ai_judgment}")
                
                if ai_judgment.get('should_exit', False):
                    self.logger.info(f"売却判断: AI判断により売却推奨 (理由: {ai_judgment.get('reason', '理由なし')})")
                    # AI判断後の処理状態チェック
                    self.logger.debug(f"AI判断後の処理状態: should_exit=True, テストモード={self.test_mode}, 現在のテスト結果数={len(self.test_results)}")
                    return True, f"AI判断: {ai_judgment.get('reason', '理由なし')}", current_price
                else:
                    self.logger.info("AI判断: 保持継続を推奨")
                    self.logger.debug(f"AI判断後の処理状態: should_exit=False, テストモード={self.test_mode}")
            except Exception as e:
                self.logger.error(f"銘柄 {validated_code} のAI判断中にエラーが発生しました: {e}", exc_info=True)
            
            # デフォルトでは保持を継続
            self.logger.info(f"最終判断: 保持継続 (損益率={profit_rate:.2f}%, 保有日数={holding_days}日)")
            return False, f"保持継続: 現在の損益率 {profit_rate:.2f}%, 保有日数 {holding_days}日", current_price
            
        except Exception as e:
            self.logger.error(f"銘柄 {entry.get('code', 'unknown')} の売却判断中にエラーが発生しました: {e}", exc_info=True)
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
            
            self.logger.info(f"銘柄 {code} の売却処理を開始します")
            self.logger.info(f"売却詳細: 数量={lot_size}株, 購入価格={entry_price}円, 売却価格={current_price}円")
            
            # 損益計算
            profit = (current_price - entry_price) * lot_size
            profit_rate = ((current_price - entry_price) / entry_price) * 100
            self.logger.info(f"損益計算: 損益額={profit:,.0f}円, 損益率={profit_rate:.2f}%")
            
            # 売却用のデータを作成
            sell_data = {
                'code': code,                 # 銘柄コード
                'quantity': lot_size,         # 株数
                'exit_price': current_price,  # 売却価格
                'entry_price': entry_price,   # 購入価格
                'reason': reason,             # 売却理由
                # 追加情報（必要に応じて）
                'profit': profit,             # 損益金額
                'profit_rate': profit_rate,   # 損益率 
                'entry_date': entry_date      # 購入日
            }
            
            self.logger.debug(f"売却データ準備完了: {sell_data}")
            
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
                
                # ログ出力を追加
                self.logger.debug(f"テスト結果を追加: 銘柄={code}, 現在のテスト結果数={len(self.test_results)}")
                self.logger.info(f"テスト結果を保存しました: 銘柄={code}")
                result = True
            else:
                # 実際に売却処理を行う場合
                self.logger.info(f"売却データ: {sell_data}")
                
                # ブラウザ操作クラスが初期化されていない場合はエラーを出力
                if self.browser_handler is None:
                    self.logger.error("ブラウザ操作クラスが初期化されていません。売却処理をスキップします。")
                    return False
                    
                # ブラウザを使用して売却処理を実行
                browser_result = self.browser_handler.execute_sell(sell_data)
                if browser_result:
                    self.logger.info(f"ブラウザ操作による売却成功: 銘柄={code}")
                else:
                    self.logger.error(f"ブラウザ操作による売却失敗: 銘柄={code}")
                    return False
                
                # データベースに売却情報を記録
                self.logger.info(f"データベースに売却情報を記録します: 銘柄={code}")
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
                self.logger.error(f"売却処理失敗: 銘柄={code} - データベース更新エラー")
                return False
                
        except Exception as e:
            self.logger.error(f"売却処理中にエラー: {e}", exc_info=True)
            return False
            
    def run(self):
        """
        自動売却処理のメイン実行メソッド
        """
        try:
            start_time = datetime.datetime.now()
            if self.test_mode and self.force_sell_test:
                self.logger.info("==========================================")
                self.logger.info("【強制売却テストモード】自動売却処理を開始します（売却判断をスキップして強制的に売却操作をテスト）")
                self.logger.info(f"開始時刻: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                self.logger.info("==========================================")
                # テスト結果の初期化を確認
                self.logger.debug(f"テスト結果初期化: test_results={self.test_results}")
            elif self.test_mode:
                self.logger.info("==========================================")
                self.logger.info("【テストモード】自動売却処理を開始します（売却はシミュレーションのみ）")
                self.logger.info(f"開始時刻: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                self.logger.info("==========================================")
                # テスト結果の初期化を確認
                self.logger.debug(f"テスト結果初期化: test_results={self.test_results}")
            else:
                self.logger.info("==========================================")
                self.logger.info("自動売却処理を開始します")
                self.logger.info(f"開始時刻: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                self.logger.info("==========================================")
            
            # アクティブなエントリーを取得
            self.logger.info("ステップ1: アクティブなエントリーの取得")
            active_entries = self.get_active_entries()
            if not active_entries:
                self.logger.info("処理対象のエントリーがありません")
                
                # テストモード時のみ、デバッグ用に強制的にダミーデータを作成する
                if self.test_mode:
                    self.logger.debug("テストモード: ダミーのテスト売却データを作成します")
                    self.test_results.append({
                        'code': 'TEST01',
                        'entry_date': datetime.date.today() - datetime.timedelta(days=5),
                        'lot_size': 100,
                        'entry_price': 1000.0,
                        'exit_price': 1050.0,
                        'profit': 5000.0,
                        'profit_rate': 5.0,
                        'reason': 'テスト用ダミーデータ（デバッグ用）',
                        'timestamp': datetime.datetime.now()
                    })
                    self.logger.debug(f"ダミーデータ作成後のテスト結果: {len(self.test_results)}件")
                
                return False
                
            sell_count = 0
            hold_count = 0
            error_count = 0
            
            # 各エントリーを評価
            self.logger.info("ステップ2: 各エントリーの評価と売却判断")
            for idx, entry in enumerate(active_entries, 1):
                code = entry['code']
                self.logger.info(f"処理中 ({idx}/{len(active_entries)}): 銘柄={code}")
                
                try:
                    # 業種情報の取得（5桁コードに変換してアクセス）
                    companies_code = self.convert_to_companies_code(code)
                    table_prefix = self.stock_repository.fetch_industry_name_prefix(companies_code)
                    if not table_prefix:
                        self.logger.warning(f"業種情報が取得できないためスキップ: {code} (companies用コード: {companies_code})")
                        error_count += 1
                        continue
                    
                    self.logger.info(f"エントリー評価: 銘柄={code}, 業種={table_prefix}")
                    
                    # 売却判断
                    should_sell, reason, current_price = self.evaluate_entry(entry)
                    
                    # 強制売却テストモードの場合は、売却判断をスキップして強制的に売却
                    if self.force_sell_test and self.test_mode:
                        self.logger.info(f"【強制売却テストモード】銘柄 {code} を強制的に売却します")
                        forced_reason = f"強制売却テスト（本来の判断: {'売却' if should_sell else '保持'}, 理由: {reason}）"
                        if self.execute_sell(entry, current_price, forced_reason):
                            sell_count += 1
                        else:
                            error_count += 1
                    # 通常の売却判断
                    elif should_sell:
                        self.logger.info(f"銘柄 {code} は売却条件を満たしています: {reason}")
                        # 売却処理
                        if self.execute_sell(entry, current_price, reason):
                            sell_count += 1
                        else:
                            error_count += 1
                    else:
                        self.logger.info(f"保持継続: 銘柄={code}, 理由={reason}")
                        hold_count += 1
                        
                        # テストモード時のみ、判断に関わらず最初のエントリーを売却候補として追加（デバッグ用）
                        if self.test_mode and not self.force_sell_test and idx == 1 and len(self.test_results) == 0:
                            self.logger.debug(f"テストモード: 銘柄 {code} を強制的に売却候補としてマーク（デバッグ用）")
                            self.execute_sell(entry, current_price, f"テスト強制売却（デバッグ用）: {reason}")
                except Exception as e:
                    self.logger.error(f"銘柄 {code} の処理中にエラー: {e}", exc_info=True)
                    error_count += 1
            
            end_time = datetime.datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            if self.test_mode:
                self.logger.info("==========================================")
                self.logger.info(f"【テストモード】自動売却処理完了: 売却候補={sell_count}件, 保持継続={hold_count}件, エラー={error_count}件")
                self.logger.info(f"処理時間: {processing_time:.2f}秒")
                self.logger.info("==========================================")
                # テスト結果の内容を確認
                self.logger.debug(f"処理完了時のテスト結果: {len(self.test_results)}件")
                if len(self.test_results) > 0:
                    for i, result in enumerate(self.test_results):
                        self.logger.debug(f"  結果{i+1}: 銘柄={result['code']}, 利益={result['profit']:,.0f}円")
                else:
                    self.logger.warning("テスト結果が0件です - レポート生成できません")
                
                # テスト結果が0件の場合、ダミーデータを追加（最終手段）
                if len(self.test_results) == 0:
                    self.logger.debug("テスト結果がないため、ダミーデータを追加します（最終手段）")
                    self.test_results.append({
                        'code': 'DUMMY',
                        'entry_date': datetime.date.today() - datetime.timedelta(days=10),
                        'lot_size': 100,
                        'entry_price': 2000.0,
                        'exit_price': 2100.0,
                        'profit': 10000.0,
                        'profit_rate': 5.0,
                        'reason': '最終手段のダミーデータ',
                        'timestamp': datetime.datetime.now()
                    })
                    self.logger.debug(f"最終ダミーデータ追加後のテスト結果: {len(self.test_results)}件")
                
                self._print_test_report()
                
                # _print_test_reportの後にも再確認
                self.logger.debug(f"レポート出力後のテスト結果: {len(self.test_results)}件")
                
                # 最終手段: テスト結果があることを再確認してから強制的にレポート保存
                # gRPCのタイムアウトが発生する前に確実に保存するため
                if len(self.test_results) > 0:
                    self.logger.info("テスト結果を強制的にレポートに保存します")
                    try:
                        report_dir = "report"
                        if not os.path.exists(report_dir):
                            os.makedirs(report_dir)
                        
                        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                        mode_prefix = "force_sell_test" if self.force_sell_test else "sell_test"
                        output_file = f"{mode_prefix}_report_{timestamp}.csv"
                        
                        with open(output_file, 'w', encoding='utf-8') as f:
                            self.logger.debug(f"ファイル {output_file} を書き込みモードでオープン")
                            if self.force_sell_test:
                                f.write("===== 強制売却テストレポート =====\n")
                            else:
                                f.write("===== 自動売却テストレポート =====\n")
                            f.write(f"実行日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                            f.write(f"売却候補数: {len(self.test_results)}\n\n")
                            
                            # CSVヘッダー
                            f.write("銘柄コード,数量,購入価格,売却価格,利益,利益率,売却理由\n")
                            
                            # 各売却候補の詳細
                            for result in self.test_results:
                                code = result['code']
                                lot_size = result['lot_size']
                                entry_price = result['entry_price']
                                exit_price = result['exit_price']
                                profit = result['profit']
                                profit_rate = result['profit_rate']
                                reason = result['reason'].replace(',', '；')  # CSVのカンマと混同しないように置換
                                
                                f.write(f"{code},{lot_size},{entry_price:.1f},{exit_price:.1f},{profit:.1f},{profit_rate:.2f},{reason}\n")
                            
                        self.logger.info(f"テストレポートを {output_file} に強制保存しました")
                    except Exception as e:
                        self.logger.error(f"強制的なレポート保存中にエラー: {e}", exc_info=True)
            else:        
                self.logger.info("==========================================")
                self.logger.info(f"自動売却処理完了: 売却={sell_count}件, 保持継続={hold_count}件, エラー={error_count}件")
                self.logger.info(f"処理時間: {processing_time:.2f}秒")
                self.logger.info("==========================================")
            
        except Exception as e:
            self.logger.error(f"自動売却処理中にエラー: {e}", exc_info=True)
            return False
            
        return True
            
    def _print_test_report(self):
        """テストモードの結果レポートを出力"""
        if not self.test_results:
            self.logger.info("【テストレポート】売却候補はありませんでした")
            return
            
        if self.force_sell_test:
            self.logger.info("\n===== 強制売却テストモード 売却レポート =====")
        else:
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
        # ロギングを追加: メソッド呼び出し時の情報
        self.logger.debug(f"save_test_report メソッド呼び出し: test_mode={self.test_mode}, test_results件数={len(self.test_results) if self.test_results else 0}, output_file={output_file}")
        
        if not self.test_mode or not self.test_results:
            self.logger.warning("テストモードでないか、テスト結果がないためレポートは保存しません")
            return
            
        try:
            # 出力ファイル名の生成
            if not output_file:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                mode_prefix = "force_sell_test" if self.force_sell_test else "sell_test"
                output_file = f"{mode_prefix}_report_{timestamp}.csv"
                self.logger.debug(f"出力ファイル名を自動生成: {output_file}")
            
            # レポート保存ディレクトリの設定とチェック
            report_dir = "report"
            if not os.path.exists(report_dir):
                self.logger.info(f"レポートディレクトリ '{report_dir}' が存在しないため作成します")
                os.makedirs(report_dir)
            
            if not os.path.isabs(output_file):
                output_file = os.path.join(report_dir, output_file)
                self.logger.debug(f"相対パスを絶対パスに変換: {output_file}")
            
            # ファイル保存前のテスト結果サマリーをログ出力
            self.logger.debug(f"保存テスト結果: {len(self.test_results)}件, 最初の銘柄={self.test_results[0]['code'] if self.test_results else 'なし'}")
            
            with open(output_file, 'w', encoding='utf-8') as f:
                self.logger.debug(f"ファイル {output_file} を書き込みモードでオープン")
                if self.force_sell_test:
                    f.write("===== 強制売却テストレポート =====\n")
                else:
                    f.write("===== 自動売却テストレポート =====\n")
                f.write(f"実行日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"売却候補数: {len(self.test_results)}\n\n")
                
                # CSVヘッダー
                f.write("銘柄コード,数量,購入価格,売却価格,利益,利益率,売却理由\n")
                
                # 各売却候補の詳細
                for result in self.test_results:
                    code = result['code']
                    lot_size = result['lot_size']
                    entry_price = result['entry_price']
                    exit_price = result['exit_price']
                    profit = result['profit']
                    profit_rate = result['profit_rate']
                    reason = result['reason'].replace(',', '；')  # CSVのカンマと混同しないように置換
                    
                    f.write(f"{code},{lot_size},{entry_price:.1f},{exit_price:.1f},{profit:.1f},{profit_rate:.2f},{reason}\n")
                
            self.logger.info(f"テストレポートを {output_file} に保存しました")
            # ファイルが実際に存在するか確認
            if os.path.exists(output_file):
                self.logger.debug(f"ファイル {output_file} の存在を確認: サイズ={os.path.getsize(output_file)}バイト")
            else:
                self.logger.error(f"エラー: ファイル {output_file} が存在しません")
            
        except Exception as e:
            self.logger.error(f"テストレポート保存中にエラー: {e}", exc_info=True)
            
def main():
    # ロギング設定
    logger = setup_logging("auto_sell_stock")
    logger.info("自動売却処理を開始します")
    
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='自動売却処理')
    parser.add_argument('--debug', action='store_true', help='デバッグモードで実行')
    parser.add_argument('--test', '-t', action='store_true', help='テスト実行モード（売却処理を実行せずシミュレーションのみ）')
    parser.add_argument('--force-sell', '-f', action='store_true', help='売却判断をスキップして強制的に売却処理のみをテストするモード')
    parser.add_argument('--output', '-o', help='テストモード時のレポート出力ファイル')
    args = parser.parse_args()
    
    # ロギングを追加: 受け取った引数情報
    logger.debug(f"コマンドライン引数: debug={args.debug}, test={args.test}, force_sell={args.force_sell}, output={args.output}")
    
    # 実行モードの表示
    if args.test and args.force_sell:
        logger.info("実行モード: 強制売却テストモード（売却判断をスキップして強制的に売却操作をテスト）")
    elif args.test:
        logger.info("実行モード: テストモード（売却はシミュレーションのみ）")
    else:
        logger.info("実行モード: 通常モード（条件を満たした銘柄を実際に売却）")
    
    # デバッグモードの設定
    if args.debug:
        # ルートロガーのレベルを変更するのではなく、個別のロガーのレベルを変更
        logger.setLevel(logging.DEBUG)
        # 関連するモジュールのロガーも設定
        logging.getLogger('repository').setLevel(logging.DEBUG)
        logging.getLogger('service').setLevel(logging.DEBUG)
        logging.getLogger('lib').setLevel(logging.DEBUG)
        logger.debug("デバッグモードが有効化されました")
        
    try:
        # 自動売却処理の実行
        auto_sell = AutoSellStock(test_mode=args.test, force_sell_test=args.force_sell, logger=logger)
        logger.debug(f"AutoSellStockインスタンス生成: test_mode={args.test}, force_sell_test={args.force_sell}")
        
        run_result = auto_sell.run()
        logger.debug(f"run()メソッド実行完了: 結果={run_result}")
        
        # テストモードでレポート出力オプションがある場合
        if args.test and args.output:
            auto_sell.save_test_report(args.output)
            logger.info(f"テストレポートを保存しました: {args.output}")
            
    except Exception as e:
        logger.error(f"処理中にエラーが発生しました: {e}")
        logger.error(traceback.format_exc())
        return 1
        
    logger.info("自動売却処理を終了します")
    return 0
        
if __name__ == "__main__":
    main() 