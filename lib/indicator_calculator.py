#!/usr/bin/env python3
import numpy as np
import pandas as pd
import pandas_ta as ta
from sklearn.decomposition import PCA
import logging
from sklearn.preprocessing import StandardScaler
import psutil
import time
import gc
from typing import Dict, List, Any, Optional, Union, Tuple
import traceback
from datetime import datetime  # datetimeクラスをインポート


class IndicatorCalculator:
    def __init__(self, data):
        """
        株価データからインジケーターを計算するクラス
        
        Args:
            data (list): 株価データのリスト。各要素は以下のキーを持つ辞書:
                - date: 日付
                - open: 始値
                - high: 高値
                - low: 安値
                - close: 終値
                - volume: 出来高
        """
        # ロガーの初期化
        self.logger = logging.getLogger(__name__)
        
        self.validate_input_data(data)
        
        # データフレームの最適化
        self.df = self._optimize_dataframe(pd.DataFrame(data))
        self.df['date'] = pd.to_datetime(self.df['date'])
        self.df = self.df.sort_values('date')
        self.df = self.df.reset_index(drop=True)
        
        # データの品質チェック
        self.check_data_quality()
        
        # 計算結果のキャッシュ
        self._cache = {}
        
        # PCA計算用の設定
        self.pca_batch_size = 100  # PCA計算のバッチサイズ
        self.max_cpu_percent = 80  # CPU使用率の上限
        
        # メモリ使用量の監視
        self.initial_memory = self._get_memory_usage()
        self.peak_memory = self.initial_memory

    def _get_memory_usage(self) -> float:
        """現在のメモリ使用量をMB単位で取得"""
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)
    
    def _optimize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """DataFrameのメモリ使用量を最適化"""
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
        
        return df

    def validate_input_data(self, data):
        """入力データの検証"""
        if not data or not isinstance(data, list):
            raise ValueError("Input data must be a non-empty list")
        
        required_fields = ['date', 'open', 'high', 'low', 'close', 'volume']
        for record in data:
            if not isinstance(record, dict):
                raise ValueError("Each record must be a dictionary")
            
            for field in required_fields:
                if field not in record:
                    raise ValueError(f"Missing required field: {field}")
                
                if field != 'date' and not isinstance(record[field], (int, float)):
                    try:
                        record[field] = float(record[field])
                    except Exception:
                        raise ValueError(f"Invalid type for {field}: expected number")

    def check_data_quality(self):
        """データの品質をチェックし、必要に応じて修正する"""
        # 欠損値の処理
        if self.df.isnull().any().any():
            self.logger.warning("データに欠損値が検出されました。前方/後方補完で埋めます。")
            self.df = self.df.ffill().bfill()
        
        # 異常値のチェック
        for col in ['open', 'high', 'low', 'close']:
            # 0以下の値をチェック
            if (self.df[col] <= 0).any():
                self.logger.warning(f"{col}に0以下の値が検出されました")
        
        # OHLC価格の整合性チェック
        if not all(self.df['high'] >= self.df['low']):
            self.logger.error("高値が安値より低い異常データが検出されました")
        
        # 日付の連続性チェック
        date_diff = self.df['date'].diff().dt.days
        if (date_diff > 5).any():
            self.logger.warning("日付の連続性に大きな隔たりが検出されました")

    def _check_cpu_usage(self):
        """CPU使用率をチェックし、必要に応じて一時停止"""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        if cpu_percent > self.max_cpu_percent:
            self.logger.debug(f"CPU使用率が高いため、処理を一時停止します: {cpu_percent:.1f}%")
            time.sleep(1)
            return True
        return False

    def _check_memory_usage(self):
        """メモリ使用状況をチェックし、必要に応じてガベージコレクションを実行"""
        current_memory = self._get_memory_usage()
        
        # ピークメモリを更新
        if current_memory > self.peak_memory:
            self.peak_memory = current_memory
        
        # メモリ使用量が急増した場合はガベージコレクションを実行
        if current_memory > self.initial_memory * 1.5:
            self.logger.debug(f"メモリ使用量が増加したため、ガベージコレクションを実行します: {current_memory:.1f} MB")
            gc.collect()
            return True
        
        return False

    def calculate_indicators(self) -> List[Dict[str, Any]]:
        """すべての日付に対してインジケーターを計算し、リストとして返す"""
        try:
            if self.df is None or len(self.df) == 0:
                self.logger.error("データフレームが空です")
                return []
            
            # CPU/メモリ使用状況をチェック
            self._check_cpu_usage()
            self._check_memory_usage()
            
            # データフレームのサイズ
            self.logger.debug(f"データフレームサイズ: {len(self.df)}行 x {len(self.df.columns)}列")
            
            # インジケーターを事前計算
            start_time = time.time()
            self._precalculate_indicators()
            precalc_time = time.time() - start_time
            self.logger.debug(f"インジケーター事前計算完了: {precalc_time:.2f}秒")
            
            # PCAシグナルを計算
            start_time = time.time()
            self._precalculate_pca_signal()
            pca_time = time.time() - start_time
            self.logger.debug(f"PCAシグナル計算完了: {pca_time:.2f}秒")
            
            # 結果をリストとして整形
            result = []
            for idx in range(len(self.df)):
                # 元のデータフレームから正しい日付を取得
                date_obj = self.df.iloc[idx]['date']
                
                # 日付のフォーマットを確保
                if isinstance(date_obj, pd.Timestamp) or isinstance(date_obj, datetime):
                    date_str = date_obj.strftime('%Y-%m-%d')
                elif isinstance(date_obj, str):
                    # 既に文字列の場合はフォーマットを確認
                    try:
                        # YYYYMMDDの場合はハイフン付きに変換
                        if len(date_obj) == 8 and date_obj.isdigit():
                            date_str = f"{date_obj[:4]}-{date_obj[4:6]}-{date_obj[6:8]}"
                        else:
                            date_str = date_obj  # 既にフォーマット済みとして使用
                    except Exception:
                        date_str = date_obj  # 変換できない場合は元の値を使用
                else:
                    # どうしても日付が取得できない場合は現在日付を使用
                    import datetime as dt
                    date_str = dt.datetime.now().strftime('%Y-%m-%d')
                    self.logger.warning(f"日付の取得に失敗しました（インデックス: {idx}）。現在日付を使用します: {date_str}")
                
                # 基本データの取得
                record = {
                    'date': date_str,
                    'open': float(self.df.iloc[idx]['open']),
                    'high': float(self.df.iloc[idx]['high']),
                    'low': float(self.df.iloc[idx]['low']),
                    'close': float(self.df.iloc[idx]['close']),
                    'volume': int(self.df.iloc[idx]['volume']),
                    
                    # インジケーターデータは後で追加（NaN対策としてgetを使用）
                    'ichimoku_tenkan': self._get_cached_value('ichimoku_tenkan', idx),
                    'ichimoku_kijun': self._get_cached_value('ichimoku_kijun', idx),
                    'ichimoku_senkou_a': self._get_cached_value('ichimoku_senkou_a', idx),
                    'ichimoku_senkou_b': self._get_cached_value('ichimoku_senkou_b', idx),
                    'adx': self._get_cached_value('adx', idx),
                    'bb_lower': self._get_cached_value('bb_lower', idx),
                    'bb_middle': self._get_cached_value('bb_middle', idx),
                    'bb_upper': self._get_cached_value('bb_upper', idx),
                    'stoch_k': self._get_cached_value('stoch_k', idx),
                    'stoch_d': self._get_cached_value('stoch_d', idx),
                    'atr': self._get_cached_value('atr', idx),
                    'rsi': self._get_cached_value('rsi', idx),
                    'macd': self._get_cached_value('macd', idx),
                    'pca_signal': self._get_cached_value('pca_signal', idx),
                }
                
                # 動的閾値の計算
                record['dynamic_threshold'] = self._calculate_dynamic_threshold(record)
                
                # 週次トレンドの計算
                record['weekly_trend'] = self._calculate_weekly_trend(record)
                
                # 値の検証とクリーニング
                if not self._validate_indicators(record):
                    self.logger.warning(f"インジケーター値の検証に失敗しました: {date_str}")
                    # Note: _validate_indicatorsは直接recordを修正するよう変更されているため、
                    # ここで更に修正は必要ありません。
                
                result.append(record)
            
            self.logger.debug(f"インジケーター計算完了: 全{len(result)}レコード")
            return result
            
        except Exception as e:
            self.logger.error(f"インジケーター計算中にエラーが発生: {str(e)}")
            self.logger.error(traceback.format_exc())
            return []

    def _precalculate_indicators(self):
        """インジケーターを事前計算してキャッシュに格納（ベクトル化計算）"""
        try:
            # データ量のチェック
            min_data_length = 78  # 52（一目均衡表の期間）+ 26（シフト）
            actual_length = len(self.df)
            
            if actual_length < min_data_length:
                self.logger.warning(f"データ不足: {actual_length}レコード（必要数: {min_data_length}）")
                # データ不足の警告だけで終了せず、可能な限り計算する
            
            # 一目均衡表の計算
            high_9 = self.df['high'].rolling(window=9).max()
            low_9 = self.df['low'].rolling(window=9).min()
            tenkan_series = (high_9 + low_9) / 2
            
            high_26 = self.df['high'].rolling(window=26).max()
            low_26 = self.df['low'].rolling(window=26).min()
            kijun_series = (high_26 + low_26) / 2
            
            senkou_a_series = ((tenkan_series + kijun_series) / 2).shift(26)
            
            high_52 = self.df['high'].rolling(window=52).max()
            low_52 = self.df['low'].rolling(window=52).min()
            senkou_b_series = ((high_52 + low_52) / 2).shift(26)
            
            self._cache['ichimoku_tenkan'] = tenkan_series
            self._cache['ichimoku_kijun'] = kijun_series
            self._cache['ichimoku_senkou_a'] = senkou_a_series
            self._cache['ichimoku_senkou_b'] = senkou_b_series
            
            # ADXの計算
            adx_df = ta.adx(high=self.df['high'], low=self.df['low'], close=self.df['close'], length=14)
            if "ADX_14" in adx_df.columns:
                self._cache['adx'] = adx_df["ADX_14"]
            
            # ボリンジャーバンドの計算
            bb_df = ta.bbands(self.df['close'], length=20, std=2)
            if "BBL_20_2.0" in bb_df.columns:
                self._cache['bb_lower'] = bb_df["BBL_20_2.0"]
            if "BBM_20_2.0" in bb_df.columns:
                self._cache['bb_middle'] = bb_df["BBM_20_2.0"]
            if "BBU_20_2.0" in bb_df.columns:
                self._cache['bb_upper'] = bb_df["BBU_20_2.0"]
            
            # ストキャスティクスの計算
            # pandas_ta のストキャスティクス計算
            stoch_df = ta.stoch(high=self.df['high'], low=self.df['low'], close=self.df['close'], k=14, d=3, smooth_k=3)
            
            # 手動でストキャスティクスを計算（バックアップとして）
            try:
                # 14日間の高値と安値
                high_14 = self.df['high'].rolling(window=14).max()
                low_14 = self.df['low'].rolling(window=14).min()
                
                # %K の生の値を計算
                k_raw = 100 * ((self.df['close'] - low_14) / (high_14 - low_14))
                
                # 無効な値（NaN、Inf）の処理
                k_raw = k_raw.replace([np.inf, -np.inf], np.nan)
                
                # 3日間の移動平均でスムージング
                k_smooth = k_raw.rolling(window=3).mean()
                
                # 最終的な%K
                manual_k = k_smooth.fillna(50)  # 計算不能な場合は50（中立）を使用
                
                # 結果を検証
                if "STOCHk_14_3_3" in stoch_df.columns:
                    # pandas_ta の結果があればそれを使う
                    pandas_ta_k = stoch_df["STOCHk_14_3_3"]
                    
                    # pandas_ta の結果に0が多い場合は手動計算を使う
                    zero_count = (pandas_ta_k == 0).sum()
                    if zero_count > len(pandas_ta_k) * 0.3:  # 30%以上が0の場合
                        self.logger.warning(f"pandas_ta のストキャスティクス計算で0が多すぎます（{zero_count}/{len(pandas_ta_k)}）。手動計算を使用します。")
                        stoch_k = manual_k
                    else:
                        stoch_k = pandas_ta_k
                else:
                    # pandas_ta の結果がなければ手動計算を使う
                    self.logger.warning("pandas_ta でストキャスティクス計算に失敗しました。手動計算を使用します。")
                    stoch_k = manual_k
                
                # %Dの計算（%Kの3日移動平均）
                stoch_d = stoch_k.rolling(window=3).mean().fillna(50)
                
                # データ長の調整（不足分を50で埋める）
                required_length = len(self.df)
                if len(stoch_k) < required_length:
                    missing_count = required_length - len(stoch_k)
                    # ストキャスティクスは最初の17日間分(14日間ウィンドウ+3日間移動平均)は計算できないため、
                    # 先頭部分のデータ不足は正常。異常な欠落がある場合のみログ出力
                    expected_missing = 17  # 理論上の不足データ数
                    if missing_count > expected_missing + 5:  # 許容範囲を超える場合のみログ出力
                        self.logger.warning(f"ストキャスティクスKの長さが不足しています: {len(stoch_k)}/{required_length}, 許容範囲を超える不足データが検出されました")
                    
                    # append() はpandas 2.0で削除されたため、pd.concatを使用
                    padding = pd.Series([50.0] * missing_count)
                    stoch_k = pd.concat([padding, stoch_k]).reset_index(drop=True)
                
                if len(stoch_d) < required_length:
                    missing_count = required_length - len(stoch_d)
                    # 同様に、異常な欠落がある場合のみログ出力
                    expected_missing = 17  # 理論上の不足データ数
                    if missing_count > expected_missing + 5:  # 許容範囲を超える場合のみログ出力
                        self.logger.warning(f"ストキャスティクスDの長さが不足しています: {len(stoch_d)}/{required_length}, 許容範囲を超える不足データが検出されました")
                    
                    # append() はpandas 2.0で削除されたため、pd.concatを使用
                    padding = pd.Series([50.0] * missing_count)
                    stoch_d = pd.concat([padding, stoch_d]).reset_index(drop=True)
                
                # キャッシュに保存
                self._cache['stoch_k'] = stoch_k
                self._cache['stoch_d'] = stoch_d
            
            except Exception as e:
                self.logger.error(f"ストキャスティクスの手動計算でエラー: {str(e)}")
                # エラー時はデフォルト値としてpandas_taの結果を使用（あれば）
                if "STOCHk_14_3_3" in stoch_df.columns:
                    stoch_k = stoch_df["STOCHk_14_3_3"]
                else:
                    # 最終的なフォールバック
                    stoch_k = pd.Series(50, index=self.df.index)
                    
                if "STOCHd_14_3_3" in stoch_df.columns:
                    stoch_d = stoch_df["STOCHd_14_3_3"]
                else:
                    stoch_d = pd.Series(50, index=self.df.index)
                
                # データ長の調整（不足分を50で埋める）
                required_length = len(self.df)
                if len(stoch_k) < required_length:
                    missing_count = required_length - len(stoch_k)
                    expected_missing = 17  # 理論上の不足データ数
                    if missing_count > expected_missing + 5:  # 許容範囲を超える場合のみログ出力
                        self.logger.warning(f"ストキャスティクスKの長さが不足しています: {len(stoch_k)}/{required_length}, 許容範囲を超える不足データが検出されました")
                    
                    padding = pd.Series([50.0] * missing_count)
                    stoch_k = pd.concat([padding, stoch_k]).reset_index(drop=True)
                
                if len(stoch_d) < required_length:
                    missing_count = required_length - len(stoch_d)
                    expected_missing = 17  # 理論上の不足データ数
                    if missing_count > expected_missing + 5:  # 許容範囲を超える場合のみログ出力
                        self.logger.warning(f"ストキャスティクスDの長さが不足しています: {len(stoch_d)}/{required_length}, 許容範囲を超える不足データが検出されました")
                    
                    padding = pd.Series([50.0] * missing_count)
                    stoch_d = pd.concat([padding, stoch_d]).reset_index(drop=True)
                
                # キャッシュに保存
                self._cache['stoch_k'] = stoch_k
                self._cache['stoch_d'] = stoch_d
            
            # ATRの計算
            df_atr = self.df.copy()
            df_atr['H-L'] = df_atr['high'] - df_atr['low']
            df_atr['H-PC'] = abs(df_atr['high'] - df_atr['close'].shift(1))
            df_atr['L-PC'] = abs(df_atr['low'] - df_atr['close'].shift(1))
            df_atr['TR'] = df_atr[['H-L', 'H-PC', 'L-PC']].max(axis=1)
            self._cache['atr'] = df_atr['TR'].rolling(window=14).mean()
            
            # RSIの計算
            self._cache['rsi'] = ta.rsi(self.df['close'], length=14)
            
            # MACDの計算
            macd_df = ta.macd(self.df['close'], fast=12, slow=26, signal=9)
            if "MACD_12_26_9" in macd_df.columns:
                self._cache['macd'] = macd_df["MACD_12_26_9"]
            
            # PCAシグナルの計算（バッチ処理）
            self._precalculate_pca_signal()
            
            # メモリ使用量の最適化
            for key in self._cache:
                if isinstance(self._cache[key], pd.Series):
                    self._cache[key] = self._cache[key].astype(np.float32)
            
            self.logger.debug("インジケーターの事前計算が完了しました")
            
        except Exception as e:
            self.logger.error(f"インジケーターの事前計算中にエラーが発生しました: {str(e)}")

    def _precalculate_pca_signal(self):
        """PCAシグナルを事前計算"""
        try:
            # 十分なデータがなければPCAは実施できない
            if len(self.df) < 20:
                self._cache['pca_signal'] = pd.Series(0, index=self.df.index)
                return
            
            # 各インジケーターの時系列データを取得
            indicators = pd.DataFrame({
                'ichimoku_tenkan': self._cache.get('ichimoku_tenkan', pd.Series(0, index=self.df.index)),
                'ichimoku_kijun': self._cache.get('ichimoku_kijun', pd.Series(0, index=self.df.index)),
                'adx': self._cache.get('adx', pd.Series(0, index=self.df.index)),
                'bb_lower': self._cache.get('bb_lower', pd.Series(0, index=self.df.index)),
                'bb_middle': self._cache.get('bb_middle', pd.Series(0, index=self.df.index)),
                'bb_upper': self._cache.get('bb_upper', pd.Series(0, index=self.df.index)),
                'stoch_k': self._cache.get('stoch_k', pd.Series(0, index=self.df.index)),
                'stoch_d': self._cache.get('stoch_d', pd.Series(0, index=self.df.index)),
                'atr': self._cache.get('atr', pd.Series(0, index=self.df.index)),
                'rsi': self._cache.get('rsi', pd.Series(0, index=self.df.index)),
                'macd': self._cache.get('macd', pd.Series(0, index=self.df.index))
            }, index=self.df.index)
            
            # 欠損値、無限大のチェックと補完
            indicators = indicators.ffill().bfill()
            indicators = indicators.replace([np.inf, -np.inf], np.nan).fillna(0)
            
            # PCA計算用のシリーズを初期化（float32型で初期化）
            pca_signal_series = pd.Series(np.zeros(len(self.df), dtype=np.float32), index=self.df.index)
            
            # バッチ処理でPCAを計算
            batch_size = self.pca_batch_size
            for i in range(20, len(indicators), batch_size):
                end_idx = min(i + batch_size, len(indicators))
                batch_data = indicators.iloc[max(0, i - 20):end_idx]
                
                if len(batch_data) >= 20:
                    # 標準化
                    scaler = StandardScaler()
                    scaled_data = scaler.fit_transform(batch_data)
                    
                    # PCA計算
                    pca = PCA(n_components=3)
                    principal_components = pca.fit_transform(scaled_data)
                    
                    # 結果をシリーズに格納
                    for j in range(i, end_idx):
                        if j < len(principal_components) + i - 20:
                            # 明示的にfloat32型に変換
                            pca_signal_series.iloc[j] = np.float32(principal_components[j - i + 20 - 1, 0])
                
                # リソース使用状況をチェック
                self._check_cpu_usage()
                self._check_memory_usage()
            
            self._cache['pca_signal'] = pca_signal_series
            
        except Exception as e:
            self.logger.error(f"PCAシグナルの事前計算中にエラーが発生しました: {str(e)}")
            self._cache['pca_signal'] = pd.Series(np.zeros(len(self.df), dtype=np.float32), index=self.df.index)

    def _get_cached_value(self, key: str, idx: int) -> float:
        """キャッシュから値を取得し、適切な型に変換してNaNを処理"""
        try:
            series = self._cache.get(key)
            if series is None:
                # キーが存在しない場合はデフォルト値を返す
                default_values = {
                    'stoch_k': 50,
                    'stoch_d': 50,
                    'rsi': 50,
                    'adx': 25,
                    'pca_signal': 0
                }
                return default_values.get(key, 0)
            
            # インデックスが範囲外かチェック
            if idx >= len(series):
                self.logger.debug(f"インデックス範囲外: {key}[{idx}], キャッシュサイズ={len(series)}, デフォルト値を使用")
                # 各指標のデフォルト値を設定
                default_values = {
                    'stoch_k': 50,
                    'stoch_d': 50,
                    'rsi': 50,
                    'adx': 25,
                    'pca_signal': 0
                }
                return default_values.get(key, 0)
            
            value = series.iloc[idx]
            
            # NaN、無限大をチェック
            if pd.isna(value) or np.isinf(value):
                # 各指標のデフォルト値を設定
                default_values = {
                    'stoch_k': 50,
                    'stoch_d': 50,
                    'rsi': 50,
                    'adx': 25,
                    'pca_signal': 0
                }
                return default_values.get(key, 0)
                
            # ストキャスティクスが0で分母がゼロの可能性がある場合の特別処理
            if key in ['stoch_k', 'stoch_d'] and value == 0:
                # 直前14日間のデータを取得
                if idx >= 14:
                    window_high = max(self.df['high'].iloc[idx-14:idx+1])
                    window_low = min(self.df['low'].iloc[idx-14:idx+1])
                    # 高値と安値が同じなら50を返す（中立）
                    if window_high == window_low:
                        self.logger.debug(f"{key}が0で、14日間の高値と安値が同じです。50を返します。")
                        return 50
                
            return float(value)
            
        except Exception as e:
            # エラーのアウトプットをデバッグレベルに変更（大量の警告を減らす）
            self.logger.debug(f"_get_cached_valueでエラー({key}, {idx}): {e}")
            # エラー時のデフォルト値
            default_values = {
                'stoch_k': 50,
                'stoch_d': 50,
                'rsi': 50,
                'adx': 25,
                'pca_signal': 0
            }
            return default_values.get(key, 0)

    def _clear_cache(self):
        """キャッシュをクリア"""
        self._cache.clear()
        gc.collect()

    def _validate_indicators(self, indicators):
        """インジケーター値の妥当性チェック"""
        try:
            # 数値型チェック
            numeric_indicators = [
                'ichimoku_tenkan', 'ichimoku_kijun', 'ichimoku_senkou_a', 
                'ichimoku_senkou_b', 'adx', 'bb_lower', 'bb_middle', 'bb_upper',
                'stoch_k', 'stoch_d', 'atr', 'rsi', 'macd', 'pca_signal'
            ]
            
            for ind in numeric_indicators:
                value = indicators.get(ind)
                if value is None or not isinstance(value, (int, float)) or np.isnan(value) or np.isinf(value):
                    self.logger.debug(f"無効な{ind}値: {value}")
                    # 無効値を検出した場合は適切なデフォルト値に置き換え
                    if ind in ['stoch_k', 'stoch_d', 'rsi']:
                        indicators[ind] = 50  # 中立値を使用
                    elif ind == 'adx':
                        indicators[ind] = 25  # 中立的なトレンド強度
                    else:
                        indicators[ind] = 0  # その他のインジケータは0
                    
            # 範囲チェック
            if not (0 <= indicators['stoch_k'] <= 100):
                self.logger.debug(f"ストキャスティクス%K値が範囲外: {indicators['stoch_k']}")
                # 範囲外の値を適切な範囲内に収める
                indicators['stoch_k'] = min(max(indicators['stoch_k'], 0), 100)
                
            if not (0 <= indicators['stoch_d'] <= 100):
                self.logger.debug(f"ストキャスティクス%D値が範囲外: {indicators['stoch_d']}")
                indicators['stoch_d'] = min(max(indicators['stoch_d'], 0), 100)
                
            if not (0 <= indicators['rsi'] <= 100):
                self.logger.debug(f"RSI値が範囲外: {indicators['rsi']}")
                indicators['rsi'] = min(max(indicators['rsi'], 0), 100)
            
            # ボリンジャーバンドの整合性チェック
            bb_values = [indicators['bb_lower'], indicators['bb_middle'], indicators['bb_upper']]
            if all(isinstance(v, (int, float)) and not np.isnan(v) and not np.isinf(v) for v in bb_values):
                if not (indicators['bb_lower'] <= indicators['bb_middle'] <= indicators['bb_upper']):
                    self.logger.debug(f"ボリンジャーバンドの整合性エラー: {bb_values}")
                    # 現在価格を中心にして妥当な幅に再設定
                    close = indicators.get('close', 0)
                    indicators['bb_middle'] = close
                    indicators['bb_lower'] = close * 0.95
                    indicators['bb_upper'] = close * 1.05
            
            # 検証成功
            return True
            
        except Exception as e:
            self.logger.error(f"インジケーター検証中にエラー: {e}")
            # エラー時は強制的に妥当な値に修正
            for ind in ['stoch_k', 'stoch_d', 'rsi']:
                indicators[ind] = 50
            for ind in ['adx']:
                indicators[ind] = 25
            indicators['macd'] = 0
            indicators['atr'] = indicators.get('close', 100) * 0.01  # 1%程度のATR
            
            if 'close' in indicators:
                close = indicators['close']
                indicators['bb_middle'] = close
                indicators['bb_lower'] = close * 0.95
                indicators['bb_upper'] = close * 1.05
                
                indicators['ichimoku_tenkan'] = close
                indicators['ichimoku_kijun'] = close
                indicators['ichimoku_senkou_a'] = close
                indicators['ichimoku_senkou_b'] = close
                
            # エラーがあったが値は修正済み
            return True

    def get_indicators(self) -> List[Dict[str, Any]]:
        """全てのインジケーターを計算（互換性のために残す）"""
        return self.calculate_indicators()

    def _calculate_dynamic_threshold(self, data):
        """動的閾値を計算（異常値は前後の値から推測）"""
        try:
            # 辞書型の場合と、DataFrameの場合で処理を分ける
            if isinstance(data, dict):
                # 辞書型の場合は直接値を取得
                atr = data.get('atr')
                close = data.get('close')
                
                # 異常値チェック
                if close is None or close <= 0 or pd.isna(close) or pd.isna(atr):
                    return 0.0  # 異常値の場合はデフォルト値を返す
                
                # 動的閾値の計算
                atr_ratio = (atr / close) * 100
                base_threshold = 5.0
                
                # ATRの大きさに応じて閾値を調整
                if atr_ratio > 3.0:  # 高ボラティリティ
                    adjusted_threshold = base_threshold * 1.5
                elif atr_ratio < 1.0:  # 低ボラティリティ
                    adjusted_threshold = base_threshold * 0.5
                else:
                    adjusted_threshold = base_threshold
                    
                return adjusted_threshold
            else:
                # DataFrameの場合（元の処理）
                idx = data.index[-1]
                atr = self._get_cached_value('atr', idx)
                close = data['close'].iloc[-1]
                
                # 異常値チェック
                if close <= 0 or pd.isna(close) or pd.isna(atr):
                    # 前後の正常データから推測値を算出
                    window_size = 5  # 前後5日分のデータを使用
                    
                    # closeが0または異常値の場合
                    if close <= 0 or pd.isna(close):
                        # 直近の正常なclose値を取得
                        valid_closes = data['close'][data['close'] > 0].dropna()
                        if len(valid_closes) >= 2:
                            # 直近の変動率を計算
                            close_changes = valid_closes.pct_change()
                            avg_change = close_changes.tail(window_size).mean()
                            # 最後の正常値から推測値を計算
                            close = valid_closes.iloc[-1] * (1 + avg_change)
                        else:
                            return 0.0
                    
                    # ATRが異常値の場合
                    if pd.isna(atr):
                        # キャッシュからATRの時系列を取得
                        if 'atr' in self._cache:
                            valid_atrs = self._cache['atr'].dropna()
                            if len(valid_atrs) > 0:
                                atr = valid_atrs.mean()
                            else:
                                return 0.0
                        else:
                            return 0.0
                
                # 動的閾値の計算
                atr_ratio = (atr / close) * 100
                base_threshold = 5.0
                
                # ATRの大きさに応じて閾値を調整
                if atr_ratio > 3.0:  # 高ボラティリティ
                    adjusted_threshold = base_threshold * 1.5
                elif atr_ratio < 1.0:  # 低ボラティリティ
                    adjusted_threshold = base_threshold * 0.5
                else:
                    adjusted_threshold = base_threshold
                    
                return adjusted_threshold
                
        except Exception as e:
            self.logger.error(f"動的閾値計算エラー: {str(e)}")
            return 2.0  # エラー時のデフォルト値
            
    def _calculate_weekly_trend(self, data):
        """週次トレンドを計算"""
        try:
            # 辞書型の場合と、DataFrameの場合で処理を分ける
            if isinstance(data, dict):
                # 辞書型の場合は、トレンド判定ロジックを簡略化
                close = data.get('close')
                ichimoku_kijun = data.get('ichimoku_kijun')
                macd = data.get('macd', 0)
                rsi = data.get('rsi', 50)
                
                if close is None or ichimoku_kijun is None:
                    return "neutral"  # データ不足の場合は中立
                
                # 簡易的なトレンド判定
                trend_signals = 0
                
                # 一目均衡表基準線との関係で判定
                if close > ichimoku_kijun:
                    trend_signals += 1
                elif close < ichimoku_kijun:
                    trend_signals -= 1
                    
                # MACDの符号で判定
                if macd > 0:
                    trend_signals += 1
                elif macd < 0:
                    trend_signals -= 1
                    
                # RSIで判定
                if rsi > 60:
                    trend_signals += 1
                elif rsi < 40:
                    trend_signals -= 1
                
                # 総合判定
                if trend_signals >= 2:
                    return "uptrend"
                elif trend_signals <= -2:
                    return "downtrend"
                else:
                    return "neutral"
            else:
                # DataFrameの場合（元の処理）
                # 週間リサンプリングで処理
                weekly_data = data.resample('W').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                })
                
                if len(weekly_data) < 4:  # 少なくとも4週間のデータが必要
                    return "neutral"
                
                # 週間移動平均の計算
                weekly_data['sma4'] = weekly_data['close'].rolling(window=4).mean()
                weekly_data['sma8'] = weekly_data['close'].rolling(window=8).mean()
                
                # 最新の状態を取得
                latest = weekly_data.iloc[-1]
                
                # トレンド判定
                if latest['close'] > latest['sma4'] > latest['sma8']:
                    # 追加確認: 3週連続の上昇かどうか
                    price_changes = weekly_data['close'].pct_change().tail(4)
                    if sum(price_changes > 0) >= 3:
                        return "strong_uptrend"
                    return "uptrend"
                elif latest['close'] < latest['sma4'] < latest['sma8']:
                    # 追加確認: 3週連続の下落かどうか
                    price_changes = weekly_data['close'].pct_change().tail(4)
                    if sum(price_changes < 0) >= 3:
                        return "strong_downtrend"
                    return "downtrend"
                # 移動平均の位置関係のみで判断
                elif latest['close'] > latest['sma8']:
                    return "weak_uptrend"
                elif latest['close'] < latest['sma8']:
                    return "weak_downtrend"
                else:
                    return "neutral"
                
        except Exception as e:
            self.logger.error(f"週別トレンド計算エラー: {str(e)}")
            return "neutral"  # エラー時のデフォルト値


def calculate_ichimoku(high, low):
    """一目均衡表の計算（互換性のために残す）"""
    senkou_b_high = high.rolling(window=52).max()
    senkou_b_low = low.rolling(window=52).min()
    senkou_b = (senkou_b_high + senkou_b_low) / 2
    senkou_b = senkou_b.shift(26)
    tenkan_high = high.rolling(window=9).max()
    tenkan_low = low.rolling(window=9).min()
    tenkan = (tenkan_high + tenkan_low) / 2
    kijun_high = high.rolling(window=26).max()
    kijun_low = low.rolling(window=26).min()
    kijun = (kijun_high + kijun_low) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    return {
        "tenkan": float(tenkan.iloc[-1]) if not pd.isna(tenkan.iloc[-1]) else 0,
        "kijun": float(kijun.iloc[-1]) if not pd.isna(kijun.iloc[-1]) else 0,
        "senkou_a": float(senkou_a.iloc[-1]) if not pd.isna(senkou_a.iloc[-1]) else 0,
        "senkou_b": float(senkou_b.iloc[-1]) if not pd.isna(senkou_b.iloc[-1]) else 0,
    }
