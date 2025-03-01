#!/usr/bin/env python3
import glob
import os
import sys
import logging
from datetime import datetime
import time
from typing import Optional, List, Dict, Tuple, Any
import psutil
import multiprocessing
import gc

from repository.stock_repository import StockRepository
from service.indicator_service import IndicatorService
from utils.memory_manager import MemoryManager
from utils.parallel_processor import ParallelProcessor
from utils.logging_config import setup_logging, cleanup_old_logs

# グローバルスコープに配置（マルチプロセッシングで共有できるようにするため）
def process_stock_batch(batch_data: Tuple[List[str], int]) -> Dict[str, Any]:
    """
    銘柄コードのバッチを処理する

    Args:
        batch_data: (銘柄コードのリスト, バッチ番号)のタプル

    Returns:
        処理結果の辞書
    """
    codes, batch_idx = batch_data
    batch_logger = logging.getLogger(__name__)
    batch_logger.info(f"バッチ {batch_idx} の処理を開始: {len(codes)} 銘柄")
    
    # 結果を格納する辞書
    results = {
        "processed": 0,
        "errors": 0,
        "batch_idx": batch_idx,
        "total_codes": len(codes),
        "memory_usage": 0
    }
    
    try:
        # 各コードに対するインジケーター計算
        stock_repo = StockRepository()
        indicator_service = IndicatorService()
        
        for i, code in enumerate(codes):
            try:
                # メモリ使用量をモニタリング
                process = psutil.Process(os.getpid())
                current_memory = process.memory_info().rss / 1024 / 1024  # MB単位
                
                # 進捗状況をログに出力
                if i > 0 and i % 5 == 0:
                    batch_logger.info(f"バッチ {batch_idx} - 進捗: {i}/{len(codes)} 銘柄処理完了 (メモリ使用量: {current_memory:.2f} MB)")
                
                # インジケーターを計算
                indicator_service.calculate_and_save_indicators(code)
                results["processed"] += 1
                
                # メモリ使用量が高い場合はGCを強制実行
                if current_memory > 500:  # 500MB以上使用している場合
                    gc.collect()
                    
            except Exception as e:
                batch_logger.error(f"コード {code} の処理中にエラーが発生: {str(e)}")
                results["errors"] += 1
                continue
        
        # 最終的なメモリ使用量
        process = psutil.Process(os.getpid())
        results["memory_usage"] = process.memory_info().rss / 1024 / 1024  # MB単位
        
    except Exception as e:
        batch_logger.error(f"バッチ {batch_idx} の処理中に予期せぬエラーが発生: {str(e)}")
        results["errors"] = len(codes) - results["processed"]
    
    batch_logger.info(f"バッチ {batch_idx} の処理が完了: {results['processed']}/{len(codes)} 銘柄を処理 (エラー: {results['errors']}件)")
    return results

def main():
    # ロギング設定
    logger = setup_logging("calculate_indicators")
    logger.info("テクニカル指標計算処理を開始します")
    
    # メモリ管理クラスのインスタンス化
    memory_manager = MemoryManager()
    
    try:
        # 株式リポジトリのインスタンス化
        stock_repo = StockRepository()
        
        # 全銘柄コードを取得
        logger.info("全銘柄コードの取得を開始")
        all_codes = stock_repo.get_all_stock_codes()
        logger.info(f"合計 {len(all_codes)} 銘柄のコードを取得")
        
        # コマンドライン引数から開始銘柄コードを取得（指定がある場合）
        start_code = None
        if len(sys.argv) > 1:
            start_code = sys.argv[1]
            logger.info(f"開始銘柄コード: {start_code}")
        
        # 開始銘柄コードが指定されている場合は、その銘柄から処理を開始
        if start_code:
            try:
                start_index = all_codes.index(start_code)
                all_codes = all_codes[start_index:]
                logger.info(f"銘柄 {start_code} から処理を開始します（残り {len(all_codes)} 銘柄）")
            except ValueError:
                logger.warning(f"指定された開始銘柄コード {start_code} が見つかりません。最初から処理を開始します。")
        
        # 並列処理の設定
        cpu_count = multiprocessing.cpu_count()
        # 利用可能CPUコアの半分を使用（ただし最低2、最大6）
        worker_count = max(2, min(cpu_count // 2, 6))
        logger.info(f"並列処理を {worker_count} ワーカーで実行")
        
        # バッチサイズの計算（大きな銘柄数を適切に分割）
        batch_size = max(10, min(100, len(all_codes) // worker_count))
        logger.info(f"バッチサイズ: {batch_size} 銘柄")
        
        # 並列処理実行クラスのインスタンス化
        processor = ParallelProcessor(
            worker_count=worker_count,
            process_func=process_stock_batch,
            logger=logger
        )
        
        # 銘柄コードをバッチに分割
        batches = []
        for i in range(0, len(all_codes), batch_size):
            batch_codes = all_codes[i:i+batch_size]
            batches.append((batch_codes, i // batch_size))
        
        logger.info(f"合計 {len(batches)} バッチに分割して処理を実行")
        
        # 並列処理の実行
        results = processor.process(batches)
        
        # 結果の集計
        total_processed = sum(r.get("processed", 0) for r in results)
        total_errors = sum(r.get("errors", 0) for r in results)
        
        logger.info(f"処理完了: 合計 {total_processed} 銘柄を処理 (エラー: {total_errors}件)")
        logger.info("テクニカル指標計算処理が終了しました")
        
    except Exception as e:
        logger.error(f"処理中に予期せぬエラーが発生: {str(e)}")
    finally:
        # メモリ使用状況のレポート
        memory_manager.log_memory_usage()

if __name__ == "__main__":
    main() 