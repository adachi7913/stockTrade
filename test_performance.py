#!/usr/bin/env python3
import os
import sys
import time
import logging
import psutil
import pandas as pd
import numpy as np
from datetime import datetime
import gc

from repository.stock_repository import StockRepository
from service.indicator_service import IndicatorService
from utils.memory_manager import MemoryManager
from utils.parallel_processor import ParallelProcessor
from utils.logging_config import setup_logging, cleanup_old_logs

def get_memory_usage():
    """現在のメモリ使用量をMB単位で取得"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

# グローバルスコープに移動（マルチプロセッシングで共有できるようにするため）
def process_batch(batch_data):
    """バッチ処理用の関数（グローバルスコープに配置）"""
    batch, batch_id = batch_data
    try:
        logger = logging.getLogger(__name__)
        logger.info(f"バッチ {batch_id} の処理を開始: {len(batch)} 銘柄")
        
        # 結果を格納する辞書
        results = {
            "batch_id": batch_id,
            "processed": 0,
            "errors": 0,
            "memory_usage": get_memory_usage(),
            "execution_time": 0
        }
        
        start_time = time.time()
        
        # 各コードに対する処理
        for code in batch:
            try:
                # 処理ロジック（実際の処理はここに記述）
                time.sleep(0.01)  # 処理をシミュレート
                results["processed"] += 1
            except Exception as e:
                logger.error(f"コード {code} の処理中にエラー: {str(e)}")
                results["errors"] += 1
        
        # 処理時間と最終メモリ使用量を記録
        results["execution_time"] = time.time() - start_time
        results["memory_usage"] = get_memory_usage()
        
        logger.info(f"バッチ {batch_id} の処理が完了: {results['processed']}/{len(batch)} 銘柄を処理 "
                   f"(実行時間: {results['execution_time']:.2f}秒, メモリ: {results['memory_usage']:.2f}MB)")
        
        return results
    except Exception as e:
        logger.error(f"バッチ処理中に予期せぬエラー: {str(e)}")
        return {"batch_id": batch_id, "processed": 0, "errors": len(batch), "error_msg": str(e)}

def get_valid_test_codes(count=3):
    """テスト用の有効な銘柄コードを取得"""
    try:
        logger = logging.getLogger(__name__)
        logger.info(f"{count}個のテスト用銘柄コードを取得します")
        
        # StockRepositoryのインスタンス化
        repo = StockRepository()
        
        # 全銘柄コードを取得
        all_codes = repo.get_all_stock_codes()
        if not all_codes:
            logger.warning("銘柄コードの取得に失敗しました")
            return []
        
        # テスト用にランダムに選択（実際のテストでは固定コードの方が再現性があるため、固定コードを使用）
        test_codes = ["1301", "1332", "1333"]  # 固定テストコード
        
        # 指定された数のコードを返す
        return test_codes[:count]
    except Exception as e:
        logger.error(f"テストコード取得中にエラー: {str(e)}")
        return []

def test_single_stock(code: str, test_name: str):
    """単一銘柄の処理パフォーマンスをテスト"""
    logger = logging.getLogger(__name__)
    logger.info(f"テスト '{test_name}' を開始: 銘柄コード {code}")
    
    # メモリ使用量の初期値を記録
    initial_memory = get_memory_usage()
    logger.info(f"初期メモリ使用量: {initial_memory:.2f}MB")
    
    try:
        # 処理開始時間
        start_time = time.time()
        
        # StockRepositoryとIndicatorServiceのインスタンス化
        stock_repo = StockRepository()
        indicator_service = IndicatorService()
        
        # 株価データの取得
        logger.info(f"銘柄 {code} の株価データを取得中...")
        stock_data = stock_repo.get_stock_price_data(code)
        
        if stock_data is None or len(stock_data) == 0:
            logger.warning(f"銘柄 {code} の株価データが取得できませんでした")
            return False
        
        logger.info(f"取得した株価データ: {len(stock_data)}行")
        
        # インジケーターの計算
        logger.info(f"銘柄 {code} のインジケーターを計算中...")
        indicators = indicator_service.calculate_indicators(stock_data)
        
        # 処理時間とメモリ使用量を記録
        execution_time = time.time() - start_time
        current_memory = get_memory_usage()
        memory_increase = current_memory - initial_memory
        
        logger.info(f"テスト '{test_name}' の結果:")
        logger.info(f"  - 実行時間: {execution_time:.4f}秒")
        logger.info(f"  - 現在のメモリ使用量: {current_memory:.2f}MB")
        logger.info(f"  - メモリ増加量: {memory_increase:.2f}MB")
        
        # 明示的にガベージコレクションを実行
        gc.collect()
        after_gc_memory = get_memory_usage()
        logger.info(f"  - GC後のメモリ使用量: {after_gc_memory:.2f}MB")
        
        return True
    except Exception as e:
        logger.error(f"テスト '{test_name}' 実行中にエラー: {str(e)}")
        return False

def test_batch_processing(batch_size: int, test_name: str):
    """バッチ処理のパフォーマンスをテスト"""
    logger = logging.getLogger(__name__)
    logger.info(f"バッチ処理テスト '{test_name}' を開始: バッチサイズ {batch_size}")
    
    # メモリ使用量の初期値を記録
    initial_memory = get_memory_usage()
    logger.info(f"初期メモリ使用量: {initial_memory:.2f}MB")
    
    try:
        # テスト用の銘柄コードを取得
        test_codes = get_valid_test_codes(batch_size * 3)  # 3バッチ分のコードを取得
        
        if not test_codes:
            logger.error("テスト用銘柄コードの取得に失敗しました")
            return False
        
        logger.info(f"テスト用銘柄コード: {len(test_codes)}個")
        
        # バッチに分割
        batches = []
        for i in range(0, len(test_codes), batch_size):
            batch = test_codes[i:i+batch_size]
            batches.append((batch, i // batch_size))
        
        logger.info(f"バッチ数: {len(batches)}")
        
        # 処理開始時間
        start_time = time.time()
        
        # 並列処理の実行
        processor = ParallelProcessor(
            worker_count=2,  # テスト用に少ない数のワーカーを使用
            process_func=process_batch,
            logger=logger
        )
        
        results = processor.process(batches)
        
        # 処理時間とメモリ使用量を記録
        execution_time = time.time() - start_time
        current_memory = get_memory_usage()
        memory_increase = current_memory - initial_memory
        
        # 結果の集計
        total_processed = sum(r.get("processed", 0) for r in results)
        total_errors = sum(r.get("errors", 0) for r in results)
        
        logger.info(f"バッチ処理テスト '{test_name}' の結果:")
        logger.info(f"  - 合計処理数: {total_processed}/{len(test_codes)} (エラー: {total_errors})")
        logger.info(f"  - 実行時間: {execution_time:.4f}秒")
        logger.info(f"  - 現在のメモリ使用量: {current_memory:.2f}MB")
        logger.info(f"  - メモリ増加量: {memory_increase:.2f}MB")
        
        # 明示的にガベージコレクションを実行
        gc.collect()
        after_gc_memory = get_memory_usage()
        logger.info(f"  - GC後のメモリ使用量: {after_gc_memory:.2f}MB")
        
        return True
    except Exception as e:
        logger.error(f"バッチ処理テスト '{test_name}' 実行中にエラー: {str(e)}")
        return False

def main():
    """メイン関数"""
    # ロギング設定
    logger = setup_logging("performance_test")
    logger.info("パフォーマンステストを開始します")
    
    try:
        # 単一銘柄のテスト
        test_code = "1301"  # テスト用銘柄コード
        test_single_stock(test_code, "単一銘柄処理")
        
        # バッチ処理のテスト
        test_batch_processing(5, "小バッチ処理")
        test_batch_processing(20, "中バッチ処理")
        
        logger.info("すべてのテストが完了しました")
    except Exception as e:
        logger.error(f"テスト実行中に予期せぬエラー: {str(e)}")
    finally:
        # 最終的なメモリ使用量を表示
        final_memory = get_memory_usage()
        logger.info(f"最終メモリ使用量: {final_memory:.2f}MB")

if __name__ == "__main__":
    main() 