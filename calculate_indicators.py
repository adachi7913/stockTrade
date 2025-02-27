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

def setup_logging(log_type):
    today = datetime.now()
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.strftime("%d")
    log_dir = os.path.join("log", year, month)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    # ファイル名は dd_daily.log の形式
    log_file = os.path.join(log_dir, f"{day}_calculate_indicators.log")
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

def cleanup_old_logs(log_type):
    now = time.time()
    # ログファイルパターン: /log/**/ *_[daily].log
    pattern = os.path.join("log", "**", "*_calculate_indicators.log")
    for file in glob.glob(pattern, recursive=True):
        if os.path.isfile(file) and now - os.path.getmtime(file) > 7 * 24 * 3600:
            os.remove(file)

# グローバルスコープに配置（マルチプロセッシングで共有できるようにするため）
def process_stock_batch(batch_data: Tuple[List[str], int]) -> Dict[str, Any]:
    """
    バッチ単位で株価データを処理
    
    Args:
        batch_data (Tuple): (バッチコードリスト, バッチID)
        
    Returns:
        Dict[str, Any]: 処理結果の統計情報
    """
    batch_codes, batch_id = batch_data
    
    # 処理結果の統計情報
    stats = {
        'batch_id': batch_id,
        'total': len(batch_codes),
        'success': 0,
        'failed': 0,
        'skipped': 0
    }
    
    try:
        # メモリマネージャーを初期化
        memory_manager = MemoryManager(log_interval=5)
        
        # 各プロセスで独自のリポジトリとサービスを作成
        stock_repository = StockRepository()
        indicator_service = IndicatorService(stock_repository)
        
        # 業種名を事前にロード
        indicator_service.preload_industry_names(batch_codes)
        
        # バッチ処理を実行
        if indicator_service.calculate_and_save_indicators_batch(batch_codes):
            stats['success'] = len(batch_codes)
            logging.info(f"バッチ {batch_id} の一括処理が成功しました（{len(batch_codes)}銘柄）")
        else:
            # 個別に処理を試みる
            logging.warning(f"バッチ {batch_id} の一括処理が失敗したため、個別処理を実行します")
            for code in batch_codes:
                try:
                    # メモリ使用状況をチェック
                    memory_manager.check_memory()
                    
                    # CPU使用率をチェック
                    if psutil.cpu_percent(interval=0.1) > 80:  # 80%以上の場合は一時停止
                        logging.warning("CPU使用率が高いため、3秒間処理を一時停止します")
                        time.sleep(3)
                        
                    # 業種名を取得
                    industry_name = indicator_service.get_industry_name(code)
                    if not industry_name:
                        logging.warning(f"業種名の取得に失敗しました: code={code}")
                        stats['failed'] += 1
                        continue
                    
                    # 5桁かつ末尾が0の場合、末尾の0を取り除く
                    if len(code) == 5 and code.endswith('0'):
                        code = code[:-1]
                        
                    # 株価データを取得
                    stock_data = indicator_service.get_stock_price_data(code, industry_name)
                    if not stock_data:
                        logging.warning(f"株価データの取得に失敗しました: code={code}")
                        stats['failed'] += 1
                        continue
                    
                    # インジケーターを計算してDBに保存
                    success = indicator_service.calculate_and_save_indicators(stock_data, code, industry_name)
                    if success:
                        logging.info(f"インジケーター計算・保存成功: code={code}")
                        stats['success'] += 1
                    else:
                        logging.warning(f"インジケーター計算・保存失敗: code={code}")
                        stats['failed'] += 1
                        
                except Exception as e:
                    logging.error(f"銘柄処理中のエラー: code={code}, error={str(e)}")
                    stats['failed'] += 1
                    continue
    except Exception as e:
        logging.error(f"バッチ処理中のエラー: batch_id={batch_id}, error={str(e)}")
    finally:
        # リソースの解放
        if 'stock_repository' in locals() and stock_repository:
            stock_repository.close()
        
        # メモリマネージャーの統計情報を記録
        if 'memory_manager' in locals():
            memory_info = memory_manager.check_memory(force_log=True)
            stats['memory_usage'] = memory_info
        
        # 明示的にガベージコレクションを実行
        gc.collect()
        
    return stats

def main():
    """メイン処理"""
    cleanup_old_logs("calculate_indicators")
    logger = setup_logging("calculate_indicators")
    logger.info("calculate_indicators Service Starting")
    logger = logging.getLogger(__name__)
    
    try:
        # メモリマネージャーを初期化
        memory_manager = MemoryManager(enable_tracemalloc=False)
        
        # 並列プロセッサを初期化
        parallel_processor = ParallelProcessor(
            use_processes=True,  # プロセスを使用
            adaptive=True,       # 動的にワーカー数を調整
            batch_size=20        # バッチサイズ
        )
        
        # リポジトリとサービスのインスタンス化
        stock_repository = StockRepository()
        indicator_service = IndicatorService(stock_repository)
        
        # 全株価コードを取得
        stock_codes = indicator_service.get_all_stock_codes()
        start_code = sys.argv[1] if len(sys.argv) > 1 else None
        
        if start_code:
            try:
                start_index = stock_codes.index(start_code)
                stock_codes = stock_codes[start_index:]
                logger.info(f"指定された開始コード {start_code} から処理を開始します")
            except ValueError:
                logger.warning(f"指定された開始コード {start_code} が見つかりません。全コードを処理します")
        
        if not stock_codes:
            logger.error("株価コードの取得に失敗しました")
            return
            
        logger.info(f"処理対象の株価コード数: {len(stock_codes)}")
        
        # 最適なバッチサイズを計算
        batch_size = ParallelProcessor.get_optimal_batch_size(len(stock_codes), target_batches=20)
        logger.info(f"最適なバッチサイズ: {batch_size}")
        
        # バッチ処理の準備
        batches = []
        for i in range(0, len(stock_codes), batch_size):
            batch = stock_codes[i:i + batch_size]
            batches.append((batch, i // batch_size))
            
        # 最適なワーカー数を計算
        optimal_workers = ParallelProcessor.get_optimal_workers()
        logger.info(f"最適なワーカー数: {optimal_workers}")
        
        # 処理結果の統計情報
        total_stats = {
            'total': len(stock_codes),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'batches_completed': 0
        }
        
        # 処理開始時間を記録
        start_time = time.time()
        
        # バッチ処理の実行（シーケンシャルに処理）
        batch_results = []
        for batch_data in batches:
            result = process_stock_batch(batch_data)
            batch_results.append(result)
            
            # 統計情報の更新
            total_stats['success'] += result.get('success', 0)
            total_stats['failed'] += result.get('failed', 0)
            total_stats['skipped'] += result.get('skipped', 0)
            total_stats['batches_completed'] += 1
            
            # 進捗状況の表示
            progress = (total_stats['batches_completed'] / len(batches)) * 100
            logger.info(f"進捗状況: {progress:.1f}% ({total_stats['batches_completed']}/{len(batches)}バッチ完了)")
            
            # メモリ使用状況の表示
            memory_manager.check_memory(force_log=True)
            
            # CPU使用率が90%を超えた場合は長めの一時停止
            if psutil.cpu_percent(interval=0.1) > 90:
                logger.warning("CPU使用率が非常に高いため、5秒間処理を一時停止します")
                time.sleep(5)
        
        # 処理時間を計算
        elapsed_time = time.time() - start_time
        
        # 処理結果の表示
        logger.info("処理完了")
        logger.info(f"処理時間: {elapsed_time:.1f}秒")
        logger.info(f"処理結果: 成功={total_stats['success']}, 失敗={total_stats['failed']}, スキップ={total_stats['skipped']}")
        
        if total_stats['total'] > 0:
            success_rate = (total_stats['success'] / total_stats['total']) * 100
            logger.info(f"成功率: {success_rate:.1f}%")
        
        # 最終的なメモリ使用状況をログに記録
        memory_manager.check_memory(force_log=True)
                
    except Exception as e:
        logger.error(f"処理全体でエラーが発生しました: {str(e)}")
    finally:
        if 'stock_repository' in locals() and stock_repository:
            stock_repository.close()
            
if __name__ == "__main__":
    main() 