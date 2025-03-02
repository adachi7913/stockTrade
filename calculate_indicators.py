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

# 5桁銘柄コードを4桁に変換する関数
def convert_5digit_to_4digit(code: str) -> str:
    """
    5桁の銘柄コードを4桁に変換します。
    末尾が '0' の場合、それを除去します。
    
    Args:
        code (str): 5桁の銘柄コード
        
    Returns:
        str: 4桁の銘柄コード
    """
    if not code or len(code) < 5:
        return code
        
    if code[-1] == '0':
        return code[:-1]
    else:
        # 末尾が0以外の場合はそのまま返す（最近の銘柄では末尾が5などのケースもある）
        return code

# グローバルスコープに配置（マルチプロセッシングで共有できるようにするため）
def process_stock_batch(batch_codes: List[str], batch_idx: int = 0) -> Dict[str, Any]:
    """
    銘柄コードのバッチを処理する

    Args:
        batch_codes: 銘柄コードのリスト
        batch_idx: バッチ番号（デフォルト: 0）

    Returns:
        処理結果の辞書
    """
    # 統一されたロガーを使用する
    batch_logger = setup_logging("calculate_indicators")
    batch_logger.info(f"バッチ {batch_idx} の処理を開始: {len(batch_codes)} 銘柄")
    
    # 型チェック - バッチが期待通りか確認
    if not isinstance(batch_codes, list):
        batch_logger.error(f"バッチ {batch_idx}: batch_codes の型が list ではなく {type(batch_codes)} です")
        # 空のリストとして処理
        batch_codes = []
    
    # バッチがリストのリストの場合、最初のリストを取得
    if batch_codes and isinstance(batch_codes[0], list):
        batch_logger.info(f"バッチ {batch_idx}: batch_codes が二重リスト構造です。最初のリストを使用します。")
        batch_codes = batch_codes[0]
    
    # 結果を格納する辞書
    results = {
        "processed": 0,
        "errors": 0,
        "batch_idx": batch_idx,
        "total_codes": len(batch_codes),
        "memory_usage": 0,
        "start_time": time.time()
    }
    
    # メモリ使用量の初期値を記録
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB単位
    peak_memory = initial_memory
    
    try:
        # 各コードに対するインジケーター計算
        stock_repo = StockRepository()
        
        # 統一されたロガーをIndicatorServiceに渡す
        try:
            # 最初にロガーを渡す形で試みる
            indicator_service = IndicatorService(stock_repository=stock_repo, logger=batch_logger)
        except TypeError:
            # ロガー引数に対応していない場合は通常の方法でインスタンス化
            batch_logger.warning("IndicatorServiceはロガー引数に対応していないため、デフォルトロガーを使用します")
            indicator_service = IndicatorService(stock_repository=stock_repo)
        
        for i, code in enumerate(batch_codes):
            try:
                # codeの型をチェック
                if not isinstance(code, str):
                    batch_logger.warning(f"バッチ {batch_idx}: インデックス {i} の code の型が str ではなく {type(code)} です。スキップします。")
                    results["errors"] += 1
                    continue
                
                # メモリ使用量をモニタリング
                current_memory = process.memory_info().rss / 1024 / 1024  # MB単位
                if current_memory > peak_memory:
                    peak_memory = current_memory
                
                # 進捗状況をログに出力
                if i > 0 and i % 5 == 0:
                    batch_logger.info(f"バッチ {batch_idx} - 進捗: {i}/{len(batch_codes)} 銘柄処理完了 (メモリ使用量: {current_memory:.2f} MB)")
                
                # 業種名を取得
                # 注: fetch_industry_name_prefixは5桁コードを期待している
                try:
                    # デバッグ用に生のコードを記録
                    batch_logger.debug(f"業種名取得処理: コード '{code}'")
                    
                    # 業種名取得には5桁コードを使用
                    industry_name = stock_repo.fetch_industry_name_prefix(code)
                    
                    # 業種名の型と値を詳細にチェック
                    batch_logger.debug(f"取得した業種名: '{industry_name}' (型: {type(industry_name)})")
                    
                    if industry_name is None or not isinstance(industry_name, str) or industry_name.strip() == "":
                        batch_logger.warning(f"コード {code} の業種名が無効です (値: '{industry_name}'). スキップします。")
                        results["errors"] += 1
                        continue
                        
                    # デバッグ情報
                    batch_logger.debug(f"コード {code} の業種名: '{industry_name}'")
                    
                except Exception as e:
                    batch_logger.error(f"コード {code} の業種名取得時にエラーが発生: {str(e)}")
                    results["errors"] += 1
                    continue
                
                # 株価データを取得
                try:
                    # 5桁コードを4桁コードに変換
                    code_4digit = convert_5digit_to_4digit(code)
                    batch_logger.debug(f"5桁コード '{code}' を4桁コード '{code_4digit}' に変換しました")
                    
                    # 4桁コードで株価データを取得
                    stock_data = indicator_service.get_stock_price_data(code_4digit, industry_name)
                    
                    if not stock_data:
                        batch_logger.warning(f"コード {code_4digit} の株価データが取得できません。スキップします。")
                        results["errors"] += 1
                        continue
                        
                    batch_logger.debug(f"コード {code_4digit} の株価データを取得: {len(stock_data)} レコード")
                except Exception as e:
                    batch_logger.error(f"コード {code} の株価データ取得中にエラーが発生: {str(e)}")
                    results["errors"] += 1
                    continue
                
                # インジケーターを計算
                try:
                    # 引数をデバッグ出力
                    batch_logger.debug(f"calculate_and_save_indicators呼び出し: データ数={len(stock_data)}, コード='{code_4digit}', 業種名='{industry_name}'")
                    
                    # 正しい順序で引数を渡す - 4桁コードを使用
                    indicator_service.calculate_and_save_indicators(
                        stock_data=stock_data,
                        code=code_4digit,
                        industry_name=industry_name
                    )
                    results["processed"] += 1
                except Exception as e:
                    batch_logger.error(f"インジケーター計算中にエラー: {str(e)}")
                    results["errors"] += 1
                    continue
                
                # 各銘柄処理後にメモリを解放
                stock_data = None
                
                # メモリ使用量が高い場合はGCを強制実行
                current_memory = process.memory_info().rss / 1024 / 1024
                if current_memory > initial_memory * 1.5 or current_memory > 500:  # 初期メモリの1.5倍または500MB以上
                    batch_logger.debug(f"メモリ使用量が増加したため、ガベージコレクションを実行します: {current_memory:.2f} MB")
                    gc.collect()
                    # GC後のメモリ使用量を確認
                    after_gc_memory = process.memory_info().rss / 1024 / 1024
                    batch_logger.debug(f"GC後のメモリ使用量: {after_gc_memory:.2f} MB (削減量: {current_memory - after_gc_memory:.2f} MB)")
                    
            except Exception as e:
                batch_logger.error(f"コード {code} の処理中にエラーが発生: {str(e)}")
                batch_logger.error(f"エラーの詳細: {str(e.__class__.__name__)}: {str(e)}")
                import traceback
                batch_logger.error(traceback.format_exc())
                results["errors"] += 1
                continue
        
        # 最終的なメモリ使用量
        current_memory = process.memory_info().rss / 1024 / 1024  # MB単位
        results["memory_usage"] = current_memory
        results["peak_memory"] = peak_memory
        results["end_time"] = time.time()
        results["elapsed_time"] = results["end_time"] - results["start_time"]
        
        # バッチ処理完了後に強制的にGCを実行
        gc.collect()
        
    except Exception as e:
        batch_logger.error(f"バッチ {batch_idx} の処理中に予期せぬエラーが発生: {str(e)}")
        import traceback
        batch_logger.error(traceback.format_exc())
        results["errors"] = len(batch_codes) - results["processed"]
        results["end_time"] = time.time()
        results["elapsed_time"] = results["end_time"] - results["start_time"]
    
    batch_logger.info(f"バッチ {batch_idx} の処理が完了: {results['processed']}/{len(batch_codes)} 銘柄を処理 (エラー: {results['errors']}件, 経過時間: {results['elapsed_time']:.1f}秒, ピークメモリ: {peak_memory:.1f} MB)")
    return results

def main():
    # ロギング設定
    logger = setup_logging("calculate_indicators")
    logger.info("テクニカル指標計算処理を開始します")
    
    # 開始時間を記録
    start_time = time.time()
    
    # メモリ管理クラスのインスタンス化
    memory_manager = MemoryManager()
    initial_memory = memory_manager.get_memory_usage()
    logger.info(f"初期メモリ使用量: {initial_memory:.2f} MB")
    
    try:
        # 株式リポジトリのインスタンス化
        stock_repo = StockRepository()
        
        # 全銘柄コードを取得
        logger.info("全銘柄コードの取得を開始")
        all_codes = stock_repo.fetch_company_code_list()
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
        logger.info(f"並列処理を {worker_count} ワーカーで実行（利用可能CPU: {cpu_count}コア）")
        
        # バッチサイズの計算（大きな銘柄数を適切に分割）
        batch_size = max(10, min(100, len(all_codes) // worker_count))
        logger.info(f"バッチサイズ: {batch_size} 銘柄")
        
        # 並列処理実行クラスのインスタンス化
        processor = ParallelProcessor(
            max_workers=worker_count,
            adaptive=True,
            use_processes=True  # プロセスを使用する設定を明示的に指定
        )
        
        # 銘柄コードをバッチに分割
        batches = []
        for i in range(0, len(all_codes), batch_size):
            batch_codes = all_codes[i:i+batch_size]
            batches.append(batch_codes)
        
        logger.info(f"合計 {len(batches)} バッチに分割して処理を実行")
        
        # デバッグ: 最初のバッチの内容を確認
        if batches:
            first_batch = batches[0]
            logger.debug(f"最初のバッチの型: {type(first_batch)}, 長さ: {len(first_batch)}")
            if first_batch:
                first_code = first_batch[0]
                logger.debug(f"最初のコードの型: {type(first_code)}, 値: {first_code}")
        
        # 並列処理の実行方法を変更
        # 方法2: process_batchesメソッドを使用し、バッチサイズを1に設定して二重バッチ化を防ぐ
        results = processor.process_batches(
            items=batches,
            process_func=process_stock_batch,
            batch_size=1,  # バッチサイズを1に設定して二重バッチ化を防ぐ
            show_progress=True
        )
        
        # 結果の集計
        total_processed = sum(r.get("processed", 0) for r in results)
        total_errors = sum(r.get("errors", 0) for r in results)
        total_codes = sum(r.get("total_codes", 0) for r in results)
        
        # 処理時間の計算
        end_time = time.time()
        total_time = end_time - start_time
        avg_time_per_code = total_time / total_processed if total_processed > 0 else 0
        
        # メモリ使用状況の集計
        peak_memories = [r.get("peak_memory", 0) for r in results if "peak_memory" in r]
        avg_peak_memory = sum(peak_memories) / len(peak_memories) if peak_memories else 0
        max_peak_memory = max(peak_memories) if peak_memories else 0
        
        # 詳細な結果レポートを出力
        logger.info("=" * 50)
        logger.info("テクニカル指標計算処理の結果サマリー")
        logger.info("=" * 50)
        
        # 成功率の計算（ゼロ除算を防止）
        success_rate = (total_processed / total_codes * 100) if total_codes > 0 else 0.0
        logger.info(f"処理完了: 合計 {total_processed}/{total_codes} 銘柄を処理 (成功率: {success_rate:.1f}%)")
        logger.info(f"エラー数: {total_errors} 件")
        logger.info(f"総処理時間: {total_time:.1f} 秒 ({total_time/60:.1f} 分)")
        logger.info(f"1銘柄あたりの平均処理時間: {avg_time_per_code:.3f} 秒")
        logger.info(f"平均ピークメモリ使用量: {avg_peak_memory:.1f} MB")
        logger.info(f"最大ピークメモリ使用量: {max_peak_memory:.1f} MB")
        logger.info("=" * 50)
        
        # バッチごとの詳細情報（オプション）
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("バッチごとの詳細情報:")
            for i, result in enumerate(results):
                processed = result.get("processed", 0)
                errors = result.get("errors", 0)
                total = result.get("total_codes", 0)
                elapsed = result.get("elapsed_time", 0)
                memory = result.get("memory_usage", 0)
                peak_mem = result.get("peak_memory", 0)
                
                logger.debug(f"バッチ {i}: 処理={processed}/{total}, エラー={errors}, "
                           f"時間={elapsed:.1f}秒, メモリ={memory:.1f}MB, ピーク={peak_mem:.1f}MB")
        
        logger.info("テクニカル指標計算処理が正常に終了しました")
        
    except Exception as e:
        logger.error(f"処理中に予期せぬエラーが発生: {str(e)}")
        # スタックトレースも出力
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # 最終的なメモリ使用状況のレポート
        final_memory = memory_manager.get_memory_usage()
        memory_diff = final_memory - initial_memory
        logger.info(f"最終メモリ使用状況: {final_memory:.2f} MB (変化量: {memory_diff:+.2f} MB)")
        
        # 処理時間の表示
        end_time = time.time()
        total_time = end_time - start_time
        logger.info(f"総処理時間: {total_time:.1f} 秒 ({total_time/60:.1f} 分)")
        
        # 古いログファイルのクリーンアップ
        cleanup_old_logs("calculate_indicators")

if __name__ == "__main__":
    main() 