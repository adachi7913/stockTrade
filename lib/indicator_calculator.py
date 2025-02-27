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
        """データ品質のチェック"""
        # 欠損値のチェック
        if self.df.isnull().any().any():
            logging.warning("Missing values detected in the input data")
            # 欠損値の補完
            self.df = self.df.interpolate(method='linear', limit_direction='both')
            self.df = self.df.ffill().bfill()
        
        # 異常値のチェック
        for col in ['open', 'high', 'low', 'close']:
            # 0以下の値をチェック
            if (self.df[col] <= 0).any():
                logging.warning(f"Non-positive values detected in {col}")
        
        # OHLC価格の整合性チェック
        if not all(self.df['high'] >= self.df['low']):
            logging.error("High price is lower than low price")
        if not all(self.df['high'] >= self.df['open']) or not all(self.df['high'] >= self.df['close']):
            logging.error("High price is lower than open/close price")
        if not all(self.df['low'] <= self.df['open']) or not all(self.df['low'] <= self.df['close']):
            logging.error("Low price is higher than open/close price")

    def _check_cpu_usage(self):
        """CPU使用率をチェックし、必要に応じて一時停止"""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        if cpu_percent > self.max_cpu_percent:
            logging.debug(f"CPU使用率が高いため、処理を一時停止します: {cpu_percent:.1f}%")
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
            logging.debug(f"メモリ使用量が増加したため、ガベージコレクションを実行します: {current_memory:.1f} MB")
            gc.collect()
            return True
        
        return False

    def calculate_indicators(self) -> List[Dict[str, Any]]:
        """全てのインジケーターを計算"""
        try:
            # 十分なデータがあるか確認
            min_required_records = 78  # 最低限必要なレコード数
            if len(self.df) < min_required_records:
                logging.warning(f"データ不足: {len(self.df)}レコード（必要数: {min_required_records}）")
                latest_row = self.df.iloc[-1]
                return [{
                    'date': latest_row['date'].strftime('%Y%m%d'),
                    'ichimoku_tenkan': 0,
                    'ichimoku_kijun': 0,
                    'ichimoku_senkou_a': 0,
                    'ichimoku_senkou_b': 0,
                    'adx': 0,
                    'bb_lower': 0,
                    'bb_middle': 0,
                    'bb_upper': 0,
                    'stoch_k': 0,
                    'stoch_d': 0,
                    'atr': 0,
                    'rsi': 0,
                    'macd': 0,
                    'dynamic_threshold': 0,
                    'weekly_trend': "UNKNOWN",
                    'pca_signal': 0
                }]

            # 事前計算（ベクトル化）
            self._precalculate_indicators()
            
            results = []
            batch_count = 0
            
            for idx, row in self.df.iterrows():
                if idx < min_required_records - 1:
                    continue

                # 定期的にリソース使用状況をチェック
                batch_count += 1
                if batch_count % 20 == 0:
                    self._check_cpu_usage()
                    self._check_memory_usage()

                window_data = self.df.iloc[max(0, idx - min_required_records + 1):idx + 1]
                
                try:
                    indicators = {
                        'date': row['date'].strftime('%Y%m%d'),
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
                        'dynamic_threshold': self._calculate_dynamic_threshold(window_data),
                        'weekly_trend': self._calculate_weekly_trend(window_data),
                        'pca_signal': self._get_cached_value('pca_signal', idx)
                    }
                    
                    # インジケーターの妥当性チェック
                    if self._validate_indicators(indicators):
                        results.append(indicators)
                        
                except Exception as e:
                    logging.error(f"Error calculating indicators for date {row['date']}: {str(e)}")
                    continue

            # forループ終了後
            expected_calculations = len(self.df) - (min_required_records - 1)
            if len(results) < expected_calculations:
                logging.warning(f"期待される計算件数は {expected_calculations} 件ですが、実際の計算結果は {len(results)} 件でした。データ不良の可能性があります。")
            
            # キャッシュをクリア
            self._clear_cache()
            
            return results
        except Exception as e:
            logging.error(f"Error in calculate_indicators: {str(e)}")
            raise

    def _precalculate_indicators(self):
        """インジケーターを事前計算してキャッシュに格納（ベクトル化計算）"""
        try:
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
            stoch_df = ta.stoch(high=self.df['high'], low=self.df['low'], close=self.df['close'], k=14, d=3, smooth_k=3)
            if "STOCHk_14_3_3" in stoch_df.columns:
                self._cache['stoch_k'] = stoch_df["STOCHk_14_3_3"]
            if "STOCHd_14_3_3" in stoch_df.columns:
                self._cache['stoch_d'] = stoch_df["STOCHd_14_3_3"]
            
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
            
            logging.debug("インジケーターの事前計算が完了しました")
            
        except Exception as e:
            logging.error(f"インジケーターの事前計算中にエラーが発生しました: {str(e)}")

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
            logging.error(f"PCAシグナルの事前計算中にエラーが発生しました: {str(e)}")
            self._cache['pca_signal'] = pd.Series(np.zeros(len(self.df), dtype=np.float32), index=self.df.index)

    def _get_cached_value(self, key: str, idx: int) -> float:
        """キャッシュから値を取得"""
        if key in self._cache and idx < len(self._cache[key]):
            value = self._cache[key].iloc[idx]
            return float(value) if not pd.isna(value) else 0
        return 0

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
                    logging.debug(f"無効な{ind}値: {value}")
                    return False
                
            # 範囲チェック
            if not (0 <= indicators['stoch_k'] <= 100 and 0 <= indicators['stoch_d'] <= 100):
                logging.debug(f"ストキャスティクス値が範囲外: K={indicators['stoch_k']}, D={indicators['stoch_d']}")
                return False
                
            if not (0 <= indicators['rsi'] <= 100):
                logging.debug(f"RSI値が範囲外: {indicators['rsi']}")
                return False
                
            if not (0 <= indicators['adx'] <= 100):
                logging.debug(f"ADX値が範囲外: {indicators['adx']}")
                return False
                
            # ボリンジャーバンドの整合性チェック
            bb_values = [indicators['bb_lower'], indicators['bb_middle'], indicators['bb_upper']]
            if any(np.isnan(v) or np.isinf(v) for v in bb_values) or not (bb_values[0] <= bb_values[1] <= bb_values[2]):
                logging.debug(f"ボリンジャーバンド値が不整合: Lower={bb_values[0]}, Middle={bb_values[1]}, Upper={bb_values[2]}")
                return False
            
            return True
            
        except Exception as e:
            logging.error(f"インジケーター検証エラー: {str(e)}")
            return False

    def get_indicators(self) -> List[Dict[str, Any]]:
        """全てのインジケーターを計算（互換性のために残す）"""
        return self.calculate_indicators()

    def _calculate_dynamic_threshold(self, data):
        """動的閾値を計算（異常値は前後の値から推測）"""
        try:
            # キャッシュからATRを取得
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
            dynamic_threshold = base_threshold * (atr_ratio / base_threshold)
            
            # 計算結果の妥当性チェック
            if pd.isna(dynamic_threshold) or np.isinf(dynamic_threshold):
                return 0.0
            
            return dynamic_threshold
            
        except Exception as e:
            logging.error(f"動的閾値計算エラー: {str(e)}")
            return 0.0

    def _calculate_weekly_trend(self, data):
        """週別トレンドを計算"""
        try:
            weekly_data = data.resample('W', on='date').last()
            sma_5 = weekly_data['close'].rolling(window=5).mean()
            if len(sma_5) < 2:
                return "UNKNOWN"
            return "UP" if sma_5.iloc[-1] > sma_5.iloc[-2] else "DOWN"
        except Exception as e:
            logging.error(f"週別トレンド計算エラー: {str(e)}")
            return "UNKNOWN"


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
