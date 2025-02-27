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

# ロギングの設定
def setup_logging():
    today = datetime.now()
    log_dir = os.path.join("log", today.strftime("%Y"), today.strftime("%m"))
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, f"{today.strftime('%d')}_performance_test.log")
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()
    
    fh = logging.FileHandler(log_file, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    return logger

def get_memory_usage():
    """現在のメモリ使用量をMB単位で取得"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

# グローバルスコープに移動（マルチプロセッシングで共有できるようにするため）
def process_batch(batch_data):
    """バッチ処理用の関数（グローバルスコープに配置）"""
    batch, batch_id = batch_data
    try:
        # 各プロセスで独自のリポジトリとサービスを作成
        repo = StockRepository()
        service = IndicatorService(repo)
        
        # 業種名を事前にロード
        service.preload_industry_names(batch)
        
        # バッチ処理を実行
        success = service.calculate_and_save_indicators_batch(batch)
        
        return {
            "batch_id": batch_id,
            "success": success,
            "count": len(batch)
        }
    except Exception as e:
        logging.error(f"バッチ処理中にエラーが発生しました: {str(e)}")
        return {
            "batch_id": batch_id,
            "success": False,
            "count": len(batch)
        }
    finally:
        if 'repo' in locals() and repo:
            repo.close()

def get_valid_test_codes(count=3):
    """テスト用の有効な銘柄コードを取得"""
    try:
        # リポジトリの初期化
        repo = StockRepository()
        
        # 全銘柄コードを取得
        all_codes = repo.fetch_company_code_list()
        
        # 業種名が取得できる銘柄コードを選択
        valid_codes = []
        for code in all_codes:
            # 5桁コードから4桁コードに変換（末尾の0を削除）
            if len(code) == 5 and code.endswith('0'):
                code_4digit = code[:-1]
            else:
                code_4digit = code
                
            # 業種名を取得
            industry_name = repo.fetch_industry_name_prefix(code)
            if industry_name:
                valid_codes.append(code_4digit)
                if len(valid_codes) >= count:
                    break
        
        return valid_codes
    except Exception as e:
        logging.error(f"有効な銘柄コード取得エラー: {str(e)}")
        # デフォルトのコードを返す
        return ["7203", "9984", "6758"]
    finally:
        if 'repo' in locals() and repo:
            repo.close()

def test_single_stock(code: str, test_name: str):
    """単一銘柄のインジケーター計算のパフォーマンスをテスト"""
    logger = logging.getLogger(__name__)
    logger.info(f"=== {test_name} 開始: 銘柄コード {code} ===")
    
    try:
        # リポジトリとサービスの初期化
        stock_repository = StockRepository()
        indicator_service = IndicatorService(stock_repository)
        
        # 業種名の取得
        # 5桁コードに変換（末尾に0を追加）
        code_5digit = code + "0" if len(code) == 4 else code
        industry_name = stock_repository.fetch_industry_name_prefix(code_5digit)
        
        if not industry_name:
            logger.error(f"業種名の取得に失敗しました: code={code}")
            return None
        
        logger.info(f"業種名: {industry_name}")
        
        # 株価データの取得
        stock_data = stock_repository.get_stock_price_only(code, industry_name)
        if not stock_data:
            logger.error(f"株価データの取得に失敗しました: code={code}")
            return None
        
        # メモリ使用量の記録
        initial_memory = get_memory_usage()
        logger.info(f"初期メモリ使用量: {initial_memory:.2f} MB")
        
        # 処理時間の計測
        start_time = time.time()
        
        # インジケーターの計算
        from lib.indicator_calculator import IndicatorCalculator
        calculator = IndicatorCalculator(stock_data)
        indicators = calculator.calculate_indicators()
        
        # 処理時間とメモリ使用量の記録
        end_time = time.time()
        elapsed_time = end_time - start_time
        final_memory = get_memory_usage()
        memory_diff = final_memory - initial_memory
        
        logger.info(f"処理時間: {elapsed_time:.2f}秒")
        logger.info(f"最終メモリ使用量: {final_memory:.2f} MB (差分: {memory_diff:+.2f} MB)")
        logger.info(f"計算されたインジケーター数: {len(indicators)}")
        
        # 結果の返却
        result = {
            "code": code,
            "elapsed_time": elapsed_time,
            "initial_memory": initial_memory,
            "final_memory": final_memory,
            "memory_diff": memory_diff,
            "indicator_count": len(indicators)
        }
        
        # リソースの解放
        del calculator
        del indicators
        gc.collect()
        
        logger.info(f"=== {test_name} 終了: 銘柄コード {code} ===")
        return result
        
    except Exception as e:
        logger.error(f"テスト中にエラーが発生しました: {str(e)}")
        return None
    finally:
        if 'stock_repository' in locals() and stock_repository:
            stock_repository.close()

def test_batch_processing(batch_size: int, test_name: str):
    """バッチ処理のパフォーマンスをテスト"""
    logger = logging.getLogger(__name__)
    logger.info(f"=== {test_name} 開始: バッチサイズ {batch_size} ===")
    
    try:
        # メモリマネージャーの初期化
        memory_manager = MemoryManager(enable_tracemalloc=False)
        
        # リポジトリとサービスの初期化
        stock_repository = StockRepository()
        indicator_service = IndicatorService(stock_repository)
        
        # 全株価コードの取得
        stock_codes = indicator_service.get_all_stock_codes()
        if not stock_codes:
            logger.error("株価コードの取得に失敗しました")
            return None
        
        # テスト用にコード数を制限
        max_codes = min(batch_size * 3, len(stock_codes))
        test_codes = stock_codes[:max_codes]
        logger.info(f"テスト対象の銘柄数: {len(test_codes)}")
        
        # 並列プロセッサの初期化
        parallel_processor = ParallelProcessor(
            use_processes=True,
            adaptive=True,
            batch_size=batch_size
        )
        
        # 処理時間の計測
        start_time = time.time()
        
        # バッチデータの準備
        batches = []
        for i in range(0, len(test_codes), batch_size):
            batch = test_codes[i:i + batch_size]
            batches.append((batch, i // batch_size))
        
        # バッチ処理の実行
        batch_results = []
        for batch_data in batches:
            result = process_batch(batch_data)
            batch_results.append(result)
            logger.info(f"バッチ {batch_data[1]} 処理完了: 成功={result['success']}, 件数={result['count']}")
        
        # 処理時間とメモリ使用量の記録
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        # 結果の表示
        logger.info(f"処理時間: {elapsed_time:.2f}秒")
        logger.info(f"処理速度: {len(test_codes) / elapsed_time:.2f}銘柄/秒")
        
        # メモリ使用状況の表示
        memory_info = memory_manager.check_memory(force_log=True)
        
        # 結果の返却
        result = {
            "batch_size": batch_size,
            "code_count": len(test_codes),
            "elapsed_time": elapsed_time,
            "codes_per_second": len(test_codes) / elapsed_time,
            "memory_info": memory_info
        }
        
        logger.info(f"=== {test_name} 終了: バッチサイズ {batch_size} ===")
        return result
        
    except Exception as e:
        logger.error(f"テスト中にエラーが発生しました: {str(e)}")
        return None
    finally:
        if 'stock_repository' in locals() and stock_repository:
            stock_repository.close()

def main():
    """メイン処理"""
    logger = setup_logging()
    logger.info("パフォーマンステスト開始")
    
    try:
        # 有効な銘柄コードを取得
        test_codes = get_valid_test_codes(3)
        logger.info(f"テスト用銘柄コード: {test_codes}")
        
        # 単一銘柄のテスト
        single_results = []
        
        for code in test_codes:
            result = test_single_stock(code, f"単一銘柄テスト")
            if result:
                single_results.append(result)
            
            # メモリ解放のための一時停止
            gc.collect()
            time.sleep(1)
        
        # バッチ処理のテスト
        batch_sizes = [10, 20, 50]
        batch_results = []
        
        for size in batch_sizes:
            result = test_batch_processing(size, f"バッチ処理テスト")
            if result:
                batch_results.append(result)
            
            # メモリ解放のための一時停止
            gc.collect()
            time.sleep(3)
        
        # 結果のサマリー
        logger.info("=== テスト結果サマリー ===")
        
        # 単一銘柄テストのサマリー
        if single_results:
            logger.info("単一銘柄テスト結果:")
            for result in single_results:
                logger.info(f"銘柄 {result['code']}: 処理時間 {result['elapsed_time']:.2f}秒, メモリ使用 {result['memory_diff']:+.2f} MB")
        
        # バッチ処理テストのサマリー
        if batch_results:
            logger.info("バッチ処理テスト結果:")
            for result in batch_results:
                logger.info(f"バッチサイズ {result['batch_size']}: 処理時間 {result['elapsed_time']:.2f}秒, 処理速度 {result['codes_per_second']:.2f}銘柄/秒")
        
        logger.info("パフォーマンステスト終了")
        
    except Exception as e:
        logger.error(f"テスト全体でエラーが発生しました: {str(e)}")

if __name__ == "__main__":
    main() 