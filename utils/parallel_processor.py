#!/usr/bin/env python3
import os
import time
import logging
import psutil
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Callable, Tuple, Optional, Union, TypeVar, Generic
import signal
import functools
import threading
from queue import Queue, Empty
import pickle

# ジェネリック型の定義
T = TypeVar('T')  # 入力型
R = TypeVar('R')  # 結果型

class ParallelProcessor:
    """
    並列処理を最適化するためのユーティリティクラス
    """
    
    def __init__(self, 
                 use_processes: bool = True, 
                 max_workers: Optional[int] = None,
                 cpu_threshold: float = 90.0,
                 memory_threshold: float = 80.0,
                 adaptive: bool = True,
                 batch_size: int = 20):
        """
        並列プロセッサの初期化
        
        Args:
            use_processes (bool): プロセスを使用するかスレッドを使用するか
            max_workers (Optional[int]): 最大ワーカー数（Noneの場合は自動設定）
            cpu_threshold (float): CPU使用率の警告閾値（%）
            memory_threshold (float): メモリ使用率の警告閾値（%）
            adaptive (bool): 動的にワーカー数を調整するかどうか
            batch_size (int): デフォルトのバッチサイズ
        """
        self.logger = logging.getLogger(__name__)
        self.use_processes = use_processes
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.adaptive = adaptive
        self.batch_size = batch_size
        
        # 最大ワーカー数の設定
        cpu_count = multiprocessing.cpu_count()
        if max_workers is None:
            # デフォルトはCPU数-1（最低1）
            self.max_workers = max(1, cpu_count - 1)
        else:
            # 指定された値とCPU数の小さい方を使用
            self.max_workers = min(max_workers, cpu_count)
            
        # 現在のワーカー数（初期値は最大値）
        self.current_workers = self.max_workers
        
        # 処理統計情報
        self.stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "start_time": None,
            "end_time": None,
            "cpu_usage": [],
            "memory_usage": []
        }
        
        self.logger.info(
            f"並列プロセッサを初期化: "
            f"モード={'プロセス' if use_processes else 'スレッド'}, "
            f"ワーカー数={self.max_workers}, "
            f"適応型={'有効' if adaptive else '無効'}"
        )
    
    def _get_executor(self, workers: Optional[int] = None) -> Union[ProcessPoolExecutor, ThreadPoolExecutor]:
        """
        適切なエグゼキュータを取得
        
        Args:
            workers (Optional[int]): ワーカー数（Noneの場合は現在の設定を使用）
            
        Returns:
            Union[ProcessPoolExecutor, ThreadPoolExecutor]: エグゼキュータ
        """
        worker_count = workers if workers is not None else self.current_workers
        
        if self.use_processes:
            return ProcessPoolExecutor(max_workers=worker_count)
        else:
            return ThreadPoolExecutor(max_workers=worker_count)
    
    def _check_resources(self) -> Dict[str, float]:
        """
        システムリソースの使用状況をチェック
        
        Returns:
            Dict[str, float]: リソース使用状況
        """
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory_percent = psutil.virtual_memory().percent
        
        # 統計情報を更新
        self.stats["cpu_usage"].append(cpu_percent)
        self.stats["memory_usage"].append(memory_percent)
        
        # リソース使用状況をログに記録
        if cpu_percent > self.cpu_threshold:
            self.logger.warning(f"CPU使用率が高いです: {cpu_percent:.1f}%")
        
        if memory_percent > self.memory_threshold:
            self.logger.warning(f"メモリ使用率が高いです: {memory_percent:.1f}%")
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent
        }
    
    def _adjust_workers(self) -> int:
        """
        リソース使用状況に基づいてワーカー数を調整
        
        Returns:
            int: 調整後のワーカー数
        """
        if not self.adaptive:
            return self.current_workers
        
        resources = self._check_resources()
        cpu_percent = resources["cpu_percent"]
        memory_percent = resources["memory_percent"]
        
        # CPU使用率が閾値を超えている場合はワーカー数を減らす
        if cpu_percent > self.cpu_threshold:
            new_workers = max(1, self.current_workers - 1)
            if new_workers < self.current_workers:
                self.logger.info(
                    f"CPU使用率が高いため、ワーカー数を調整: "
                    f"{self.current_workers} → {new_workers}"
                )
                self.current_workers = new_workers
        
        # メモリ使用率が閾値を超えている場合もワーカー数を減らす
        elif memory_percent > self.memory_threshold:
            new_workers = max(1, self.current_workers - 1)
            if new_workers < self.current_workers:
                self.logger.info(
                    f"メモリ使用率が高いため、ワーカー数を調整: "
                    f"{self.current_workers} → {new_workers}"
                )
                self.current_workers = new_workers
        
        # リソースに余裕がある場合はワーカー数を増やす（最大値まで）
        elif cpu_percent < self.cpu_threshold * 0.7 and memory_percent < self.memory_threshold * 0.7:
            new_workers = min(self.max_workers, self.current_workers + 1)
            if new_workers > self.current_workers:
                self.logger.info(
                    f"リソースに余裕があるため、ワーカー数を調整: "
                    f"{self.current_workers} → {new_workers}"
                )
                self.current_workers = new_workers
        
        return self.current_workers
    
    def _prepare_batches(self, items: List[T], batch_size: Optional[int] = None) -> List[List[T]]:
        """
        アイテムをバッチに分割
        
        Args:
            items (List[T]): 処理するアイテムのリスト
            batch_size (Optional[int]): バッチサイズ（Noneの場合はデフォルト値を使用）
            
        Returns:
            List[List[T]]: バッチのリスト
        """
        size = batch_size if batch_size is not None else self.batch_size
        
        # バッチに分割
        batches = []
        for i in range(0, len(items), size):
            batch = items[i:i + size]
            batches.append(batch)
        
        self.logger.info(f"{len(items)}個のアイテムを{len(batches)}バッチに分割しました（バッチサイズ: {size}）")
        return batches
    
    def process_items(self, 
                      items: List[T], 
                      process_func: Callable[[T], R],
                      batch_size: Optional[int] = None,
                      show_progress: bool = True,
                      timeout: Optional[float] = None) -> List[R]:
        """
        アイテムを並列処理
        
        Args:
            items (List[T]): 処理するアイテムのリスト
            process_func (Callable[[T], R]): 各アイテムを処理する関数
            batch_size (Optional[int]): バッチサイズ（Noneの場合はデフォルト値を使用）
            show_progress (bool): 進捗状況を表示するかどうか
            timeout (Optional[float]): タイムアウト時間（秒）
            
        Returns:
            List[R]: 処理結果のリスト
        """
        if not items:
            self.logger.warning("処理するアイテムがありません")
            return []
        
        # 統計情報の初期化
        self.stats["total_tasks"] = len(items)
        self.stats["completed_tasks"] = 0
        self.stats["failed_tasks"] = 0
        self.stats["start_time"] = time.time()
        
        results = []
        
        try:
            # エグゼキュータを作成
            with self._get_executor() as executor:
                # 各アイテムを処理
                futures = {executor.submit(process_func, item): i for i, item in enumerate(items)}
                
                # 完了したタスクを処理
                for future in as_completed(futures, timeout=timeout):
                    try:
                        result = future.result()
                        results.append(result)
                        self.stats["completed_tasks"] += 1
                    except Exception as e:
                        self.logger.error(f"タスク処理中にエラーが発生しました: {str(e)}")
                        self.stats["failed_tasks"] += 1
                    
                    # 進捗状況の表示
                    if show_progress:
                        completed = self.stats["completed_tasks"] + self.stats["failed_tasks"]
                        progress = (completed / self.stats["total_tasks"]) * 100
                        self.logger.info(f"進捗状況: {progress:.1f}% ({completed}/{self.stats['total_tasks']})")
                    
                    # リソース使用状況のチェックとワーカー数の調整
                    if self.adaptive and completed % 10 == 0:
                        self._adjust_workers()
        
        except TimeoutError:
            self.logger.error(f"処理がタイムアウトしました（{timeout}秒）")
        
        except Exception as e:
            self.logger.error(f"並列処理中にエラーが発生しました: {str(e)}")
        
        finally:
            # 統計情報の更新
            self.stats["end_time"] = time.time()
            elapsed = self.stats["end_time"] - self.stats["start_time"]
            
            self.logger.info(
                f"処理完了: 成功={self.stats['completed_tasks']}, "
                f"失敗={self.stats['failed_tasks']}, "
                f"合計={self.stats['total_tasks']}, "
                f"経過時間={elapsed:.1f}秒"
            )
        
        return results
    
    def process_batches(self, 
                        items: List[T], 
                        process_func: Callable[[List[T], int], Dict[str, Any]],
                        batch_size: Optional[int] = None,
                        show_progress: bool = True,
                        timeout: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        アイテムをバッチ単位で並列処理
        
        Args:
            items (List[T]): 処理するアイテムのリスト
            process_func (Callable[[List[T], int], Dict[str, Any]]): バッチを処理する関数
            batch_size (Optional[int]): バッチサイズ（Noneの場合はデフォルト値を使用）
            show_progress (bool): 進捗状況を表示するかどうか
            timeout (Optional[float]): タイムアウト時間（秒）
            
        Returns:
            List[Dict[str, Any]]: 処理結果のリスト
        """
        if not items:
            self.logger.warning("処理するアイテムがありません")
            return []
        
        # バッチに分割
        batches = self._prepare_batches(items, batch_size)
        
        # 統計情報の初期化
        self.stats["total_tasks"] = len(batches)
        self.stats["completed_tasks"] = 0
        self.stats["failed_tasks"] = 0
        self.stats["start_time"] = time.time()
        
        batch_results = []
        
        # マルチプロセッシングの場合は、シンプルな方法で処理
        if self.use_processes:
            try:
                # 各バッチを順番に処理
                for i, batch in enumerate(batches):
                    try:
                        # バッチを処理
                        result = process_func(batch, i)
                        batch_results.append(result)
                        self.stats["completed_tasks"] += 1
                    except Exception as e:
                        self.logger.error(f"バッチ処理中にエラーが発生しました: {str(e)}")
                        self.stats["failed_tasks"] += 1
                    
                    # 進捗状況の表示
                    if show_progress:
                        completed = self.stats["completed_tasks"] + self.stats["failed_tasks"]
                        progress = (completed / self.stats["total_tasks"]) * 100
                        self.logger.info(f"進捗状況: {progress:.1f}% ({completed}/{self.stats['total_tasks']}バッチ)")
                    
                    # リソース使用状況のチェックとワーカー数の調整
                    if self.adaptive and completed % 5 == 0:
                        self._adjust_workers()
            except Exception as e:
                self.logger.error(f"並列処理中にエラーが発生しました: {str(e)}")
        else:
            # スレッドの場合は、ThreadPoolExecutorを使用
            try:
                # エグゼキュータを作成
                with self._get_executor() as executor:
                    # 各バッチを処理
                    futures = {executor.submit(process_func, batch, i): i for i, batch in enumerate(batches)}
                    
                    # 完了したタスクを処理
                    for future in as_completed(futures, timeout=timeout):
                        try:
                            result = future.result()
                            batch_results.append(result)
                            self.stats["completed_tasks"] += 1
                        except Exception as e:
                            self.logger.error(f"バッチ処理中にエラーが発生しました: {str(e)}")
                            self.stats["failed_tasks"] += 1
                        
                        # 進捗状況の表示
                        if show_progress:
                            completed = self.stats["completed_tasks"] + self.stats["failed_tasks"]
                            progress = (completed / self.stats["total_tasks"]) * 100
                            self.logger.info(f"進捗状況: {progress:.1f}% ({completed}/{self.stats['total_tasks']}バッチ)")
                        
                        # リソース使用状況のチェックとワーカー数の調整
                        if self.adaptive and completed % 5 == 0:
                            self._adjust_workers()
            
            except TimeoutError:
                self.logger.error(f"処理がタイムアウトしました（{timeout}秒）")
            
            except Exception as e:
                self.logger.error(f"並列処理中にエラーが発生しました: {str(e)}")
        
        # 統計情報の更新
        self.stats["end_time"] = time.time()
        elapsed = self.stats["end_time"] - self.stats["start_time"]
        
        self.logger.info(
            f"バッチ処理完了: 成功={self.stats['completed_tasks']}, "
            f"失敗={self.stats['failed_tasks']}, "
            f"合計={self.stats['total_tasks']}バッチ, "
            f"経過時間={elapsed:.1f}秒"
        )
        
        return batch_results
    
    def get_stats(self) -> Dict[str, Any]:
        """
        処理統計情報を取得
        
        Returns:
            Dict[str, Any]: 統計情報
        """
        stats = self.stats.copy()
        
        # 追加の統計情報を計算
        if stats["start_time"] and stats["end_time"]:
            stats["elapsed_time"] = stats["end_time"] - stats["start_time"]
            
            # 処理速度（アイテム/秒）
            if stats["completed_tasks"] > 0 and stats["elapsed_time"] > 0:
                stats["items_per_second"] = stats["completed_tasks"] / stats["elapsed_time"]
            else:
                stats["items_per_second"] = 0
        
        # CPU/メモリ使用率の平均値
        if stats["cpu_usage"]:
            stats["avg_cpu_percent"] = sum(stats["cpu_usage"]) / len(stats["cpu_usage"])
            stats["max_cpu_percent"] = max(stats["cpu_usage"])
        
        if stats["memory_usage"]:
            stats["avg_memory_percent"] = sum(stats["memory_usage"]) / len(stats["memory_usage"])
            stats["max_memory_percent"] = max(stats["memory_usage"])
        
        return stats
    
    def log_stats(self) -> None:
        """
        処理統計情報をログに記録
        """
        stats = self.get_stats()
        
        if "elapsed_time" in stats:
            self.logger.info(f"処理時間: {stats['elapsed_time']:.1f}秒")
        
        if "items_per_second" in stats:
            self.logger.info(f"処理速度: {stats['items_per_second']:.1f}アイテム/秒")
        
        if "avg_cpu_percent" in stats:
            self.logger.info(f"CPU使用率: 平均={stats['avg_cpu_percent']:.1f}%, 最大={stats['max_cpu_percent']:.1f}%")
        
        if "avg_memory_percent" in stats:
            self.logger.info(f"メモリ使用率: 平均={stats['avg_memory_percent']:.1f}%, 最大={stats['max_memory_percent']:.1f}%")
        
        self.logger.info(
            f"処理結果: 成功={stats['completed_tasks']}, "
            f"失敗={stats['failed_tasks']}, "
            f"合計={stats['total_tasks']}"
        )
    
    @staticmethod
    def get_optimal_batch_size(total_items: int, target_batches: int = 20) -> int:
        """
        最適なバッチサイズを計算
        
        Args:
            total_items (int): 総アイテム数
            target_batches (int): 目標バッチ数
            
        Returns:
            int: 最適なバッチサイズ
        """
        if total_items <= 0:
            return 1
        
        # 目標バッチ数に基づいてバッチサイズを計算
        batch_size = max(1, total_items // target_batches)
        
        # バッチサイズが大きすぎる場合は制限
        max_size = 100
        if batch_size > max_size:
            batch_size = max_size
        
        return batch_size
    
    @staticmethod
    def get_optimal_workers() -> int:
        """
        システムに最適なワーカー数を計算
        
        Returns:
            int: 最適なワーカー数
        """
        cpu_count = multiprocessing.cpu_count()
        
        # 一般的には (CPU数 - 1) が最適
        # 最低1、最大はCPU数
        return max(1, min(cpu_count - 1, cpu_count)) 