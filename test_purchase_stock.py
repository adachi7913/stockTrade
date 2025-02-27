import os
import logging
import argparse
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

from lib.prompt_generator import PromptGenerator
from Gemini.entry_judgment_handler import EntryJudgmentHandler
from purchase_stock import StockPurchaseManager
from repository.stock_repository import StockRepository
from repository.entry_repository import EntryRepository
from utils.logging_config import setup_logging

# 環境変数の読み込み
load_dotenv()

# ロガーのセットアップ
logger = setup_logging('test_purchase_stock')

def parse_arguments():
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(description='株式購入テスト')
    parser.add_argument('--code', type=str, help='テスト対象の銘柄コード')
    parser.add_argument('--max_ai_calls', type=int, default=5, help='最大AI判断回数')
    parser.add_argument('--min_score', type=float, default=70.0, help='最小エントリースコア')
    parser.add_argument('--delay', type=int, default=60, help='API呼び出し間の待機時間(秒)')
    parser.add_argument('--test_mode', action='store_true', help='テストモード（実際の購入は行わない）')
    return parser.parse_args()

def test_prompt_generation():
    """プロンプト生成のテスト"""
    logger.info("プロンプト生成テスト開始")

    # テストデータ
    stock_data = {
        'code': '1234',
        'company_name': 'テスト株式会社',
        'close': 1500,
    }
    
    technical_data = [
        {'date': '2023-06-01', 'close': 1450, 'rsi': 62.5, 'stoch_k': 75.2, 'adx': 28.1},
        {'date': '2023-06-02', 'close': 1480, 'rsi': 65.3, 'stoch_k': 78.1, 'adx': 29.5},
        {'date': '2023-06-03', 'close': 1490, 'rsi': 67.8, 'stoch_k': 80.3, 'adx': 30.2},
        {'date': '2023-06-04', 'close': 1510, 'rsi': 70.1, 'stoch_k': 82.5, 'adx': 31.8},
        {'date': '2023-06-05', 'close': 1500, 'rsi': 68.2, 'stoch_k': 79.7, 'adx': 30.5},
    ]
    
    backtest_results = {
        'success_rate': 78.5,
        'average_return': 3.2,
        'total_trades': 42,
        'best_strategy': 'RSI_STOCH',
    }
    
    # プロンプト生成器
    generator = PromptGenerator(verbose=True)
    
    # 詳細プロンプト
    detailed_prompt = generator.generate_entry_prompt(
        stock_data, backtest_results, technical_data, entry_score=85.5
    )
    
    # 簡易プロンプト
    simple_prompt = generator.generate_simplified_prompt(
        stock_data, entry_score=85.5
    )
    
    logger.info("詳細プロンプト:\n%s", detailed_prompt)
    logger.info("簡易プロンプト:\n%s", simple_prompt)
    
    # デバッグ用にプロンプトをファイルに保存
    with open('detailed_prompt.txt', 'w', encoding='utf-8') as f:
        f.write(detailed_prompt)
    with open('simple_prompt.txt', 'w', encoding='utf-8') as f:
        f.write(simple_prompt)
    
    logger.info("プロンプト生成テスト完了")
    return detailed_prompt, simple_prompt

def test_ai_judgment(prompt):
    """AI判断のテスト"""
    logger.info("AI判断テスト開始")
    
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEYが設定されていません")
        return None
    
    # テスト用のダミー銘柄データ
    test_stock = {
        'code': '1234',
        'company_name': 'テスト株式会社'
    }
    
    # EntryJudgmentHandlerの初期化
    handler = EntryJudgmentHandler(api_key, logger)
    
    # カスタムプロンプトでの判断
    judgment = handler.judge_entry_with_prompt(test_stock, prompt)
    
    logger.info("AI判断結果:")
    logger.info(json.dumps(judgment, indent=2, ensure_ascii=False))
    
    logger.info("AI判断テスト完了")
    return judgment

def test_stock_purchase_manager(args):
    """StockPurchaseManagerのテスト"""
    logger.info("StockPurchaseManagerテスト開始")
    
    # APIキー取得
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEYが設定されていません")
        return
    
    # リポジトリの初期化
    stock_repo = StockRepository()
    entry_repo = EntryRepository()
    
    # StockPurchaseManagerの初期化
    manager = StockPurchaseManager(
        max_ai_calls=args.max_ai_calls,
        min_entry_score=args.min_score,
        api_delay=args.delay
    )
    
    # API キー、ロガー、テストモードを設定
    manager.judgment_handler = EntryJudgmentHandler(api_key=api_key, logger=logger)
    manager.entry_repository = entry_repo
    manager.logger = logger
    
    # テストモードが有効な場合は購入処理をスキップする設定
    if args.test_mode:
        manager.test_mode = True
    
    # 特定の銘柄コードが指定されている場合
    if args.code:
        # 特定銘柄のみをフィルターするように処理をオーバーライド
        original_filter = manager._filter_candidates
        
        def filtered_candidate_override(candidates):
            logger.info(f"特定銘柄 {args.code} のみをフィルター")
            filtered = [c for c in candidates if c['code'] == args.code]
            if not filtered:
                logger.warning(f"指定された銘柄コード {args.code} が候補に見つかりませんでした")
            return filtered
        
        # メソッドをオーバーライド
        manager._filter_candidates = filtered_candidate_override
    
    # 購入処理の実行
    result = manager.execute_purchase()
    
    logger.info("購入処理結果:")
    logger.info(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    
    logger.info("StockPurchaseManagerテスト完了")
    return result

def main():
    """メイン処理"""
    args = parse_arguments()
    
    if args.test_mode:
        logger.info("テストモードで実行します（実際の購入は行いません）")
    
    # プロンプト生成テスト
    detailed_prompt, simple_prompt = test_prompt_generation()
    
    # AI判断テスト
    judgment = test_ai_judgment(detailed_prompt)
    
    # StockPurchaseManagerテスト
    result = test_stock_purchase_manager(args)
    
    logger.info("テスト完了")

if __name__ == "__main__":
    main() 