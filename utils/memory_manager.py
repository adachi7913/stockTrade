#!/usr/bin/env python3
import gc
import os
import psutil
import logging
import time
import tracemalloc
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

class MemoryManager:
    """
    メモリ使用量の監視と最適化を行うユーティリティクラス
    """
    
    def __init__(self, 
                 enable_tracemalloc: bool = False, 
                 log_interval: int = 10, 
                 memory_threshold: float = 80.0,
                 auto_collect: bool = True):
        """
        メモリマネージャーの初期化
        
        Args:
            enable_tracemalloc (bool): tracemallocによるメモリ追跡を有効にするかどうか
            log_interval (int): メモリ使用量のログ記録間隔（処理回数）
            memory_threshold (float): メモリ使用率の警告閾値（%）
            auto_collect (bool): 閾値を超えた場合に自動的にガベージコレクションを実行するかどうか
        """
        self.logger = logging.getLogger(__name__)
        self.process = psutil.Process(os.getpid())
        self.enable_tracemalloc = enable_tracemalloc
        self.log_interval = log_interval
        self.memory_threshold = memory_threshold
        self.auto_collect = auto_collect
        self.counter = 0
        self.peak_memory = 0
        
        # tracemallocの初期化
        if self.enable_tracemalloc:
            tracemalloc.start()
            self.logger.info("メモリトレース機能を有効化しました")
            
        # 初期メモリ使用量を記録
        self.initial_memory = self.get_memory_usage()
        self.logger.info(f"初期メモリ使用量: {self.initial_memory:.2f} MB")
        
        # 最適化のためにGCを設定
        gc.enable()
        
    def get_memory_usage(self) -> float:
        """
        現在のメモリ使用量をMB単位で取得
        
        Returns:
            float: メモリ使用量（MB）
        """
        return self.process.memory_info().rss / (1024 * 1024)
    
    def get_memory_percent(self) -> float:
        """
        システム全体のメモリ使用率を取得
        
        Returns:
            float: メモリ使用率（%）
        """
        return psutil.virtual_memory().percent
    
    def check_memory(self, force_log: bool = False) -> Dict[str, float]:
        """
        メモリ使用状況をチェックし、必要に応じてログに記録
        
        Args:
            force_log (bool): 強制的にログに記録するかどうか
            
        Returns:
            Dict[str, float]: メモリ使用状況の情報
        """
        self.counter += 1
        current_memory = self.get_memory_usage()
        memory_percent = self.get_memory_percent()
        memory_diff = current_memory - self.initial_memory
        
        # ピークメモリを更新
        if current_memory > self.peak_memory:
            self.peak_memory = current_memory
        
        # メモリ情報を辞書にまとめる
        memory_info = {
            "current_mb": current_memory,
            "initial_mb": self.initial_memory,
            "diff_mb": memory_diff,
            "peak_mb": self.peak_memory,
            "system_percent": memory_percent
        }
        
        # ログ間隔に達したか、強制ログが指定された場合にログを記録
        if force_log or self.counter % self.log_interval == 0:
            self.logger.info(
                f"メモリ使用量: {current_memory:.2f} MB "
                f"(初期比: {memory_diff:+.2f} MB, "
                f"ピーク: {self.peak_memory:.2f} MB, "
                f"システム全体: {memory_percent:.1f}%)"
            )
        
        # メモリ使用率が閾値を超えた場合の処理
        if memory_percent > self.memory_threshold:
            self.logger.warning(
                f"メモリ使用率が閾値を超えています: {memory_percent:.1f}% > {self.memory_threshold:.1f}%"
            )
            if self.auto_collect:
                self.collect_garbage()
        
        return memory_info
    
    def collect_garbage(self) -> int:
        """
        ガベージコレクションを実行し、解放されたオブジェクト数を返す
        
        Returns:
            int: 解放されたオブジェクト数
        """
        # 実行前のメモリ使用量
        before = self.get_memory_usage()
        
        # ガベージコレクションを実行
        gc.collect()
        
        # 実行後のメモリ使用量
        after = self.get_memory_usage()
        freed = before - after
        
        self.logger.info(f"ガベージコレクション実行: {freed:.2f} MB解放")
        return gc.collect()
    
    def get_memory_snapshot(self) -> Optional[List[Tuple[int, str]]]:
        """
        現在のメモリ使用状況のスナップショットを取得
        
        Returns:
            Optional[List[Tuple[int, str]]]: メモリ使用量の多い上位10オブジェクト
        """
        if not self.enable_tracemalloc:
            self.logger.warning("tracemallocが有効になっていないため、スナップショットを取得できません")
            return None
        
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')
        
        return [(stat.size, str(stat)) for stat in top_stats[:10]]
    
    def log_memory_snapshot(self) -> None:
        """
        メモリ使用状況のスナップショットをログに記録
        """
        if not self.enable_tracemalloc:
            return
        
        snapshot = self.get_memory_snapshot()
        if snapshot:
            self.logger.info("メモリ使用量の多いオブジェクト:")
            for size, stat in snapshot:
                self.logger.info(f"{size / 1024:.1f} KB: {stat}")
    
    def optimize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        DataFrameのメモリ使用量を最適化
        
        Args:
            df (pd.DataFrame): 最適化するDataFrame
            
        Returns:
            pd.DataFrame: 最適化されたDataFrame
        """
        start_mem = df.memory_usage(deep=True).sum() / 1024**2
        
        # 数値型カラムの最適化
        for col in df.select_dtypes(include=['int']).columns:
            col_min = df[col].min()
            col_max = df[col].max()
            
            # 適切なデータ型を選択
            if col_min >= 0:
                if col_max < 255:
                    df[col] = df[col].astype(np.uint8)
                elif col_max < 65535:
                    df[col] = df[col].astype(np.uint16)
                elif col_max < 4294967295:
                    df[col] = df[col].astype(np.uint32)
                else:
                    df[col] = df[col].astype(np.uint64)
            else:
                if col_min > -128 and col_max < 127:
                    df[col] = df[col].astype(np.int8)
                elif col_min > -32768 and col_max < 32767:
                    df[col] = df[col].astype(np.int16)
                elif col_min > -2147483648 and col_max < 2147483647:
                    df[col] = df[col].astype(np.int32)
                else:
                    df[col] = df[col].astype(np.int64)
        
        # 浮動小数点型カラムの最適化
        for col in df.select_dtypes(include=['float']).columns:
            df[col] = df[col].astype(np.float32)
        
        # 文字列型カラムの最適化
        for col in df.select_dtypes(include=['object']).columns:
            if df[col].nunique() / len(df) < 0.5:  # カテゴリ型に変換する閾値
                df[col] = df[col].astype('category')
        
        end_mem = df.memory_usage(deep=True).sum() / 1024**2
        reduction = 100 * (start_mem - end_mem) / start_mem
        
        self.logger.info(f"DataFrame最適化: {start_mem:.2f} MB → {end_mem:.2f} MB ({reduction:.1f}%削減)")
        
        return df
    
    def clear_pandas_cache(self) -> None:
        """
        pandasの内部キャッシュをクリア
        """
        for name in dir(pd):
            if name.startswith('_') and name.endswith('_cache'):
                cache = getattr(pd, name)
                if hasattr(cache, 'clear'):
                    cache.clear()
        
        self.logger.debug("pandasの内部キャッシュをクリアしました")
    
    def monitor_batch_process(self, batch_id: int, total_batches: int) -> Dict[str, Any]:
        """
        バッチ処理のメモリ使用状況を監視
        
        Args:
            batch_id (int): 現在のバッチID
            total_batches (int): 総バッチ数
            
        Returns:
            Dict[str, Any]: メモリ監視情報
        """
        # 進捗状況を計算
        progress = (batch_id / total_batches) * 100
        
        # メモリ使用状況をチェック
        memory_info = self.check_memory(force_log=True)
        
        # CPU使用率を取得
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # 監視情報を辞書にまとめる
        monitor_info = {
            "batch_id": batch_id,
            "total_batches": total_batches,
            "progress": progress,
            "memory": memory_info,
            "cpu_percent": cpu_percent,
            "timestamp": time.time()
        }
        
        # CPU使用率が高い場合は警告
        if cpu_percent > 90:
            self.logger.warning(f"CPU使用率が非常に高いです: {cpu_percent:.1f}%")
        
        # 定期的にガベージコレクションを実行
        if batch_id % 5 == 0:
            self.collect_garbage()
        
        # 定期的にメモリスナップショットを記録
        if self.enable_tracemalloc and batch_id % 20 == 0:
            self.log_memory_snapshot()
        
        return monitor_info
    
    def __del__(self):
        """
        オブジェクト破棄時の処理
        """
        if self.enable_tracemalloc:
            tracemalloc.stop()
        
        # 最終的なメモリ使用状況をログに記録
        final_memory = self.get_memory_usage()
        memory_diff = final_memory - self.initial_memory
        
        self.logger.info(
            f"最終メモリ使用量: {final_memory:.2f} MB "
            f"(初期比: {memory_diff:+.2f} MB, "
            f"ピーク: {self.peak_memory:.2f} MB)"
        ) 