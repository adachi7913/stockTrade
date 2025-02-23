#!/usr/bin/env python3
import numpy as np
import pandas as pd
import pandas_ta as ta
from sklearn.decomposition import PCA
import logging
from sklearn.preprocessing import StandardScaler
import psutil
import time


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
        self.validate_input_data(data)
        self.df = pd.DataFrame(data)
        self.df['date'] = pd.to_datetime(self.df['date'])
        self.df = self.df.sort_values('date')
        self.df = self.df.reset_index(drop=True)
        
        # データの品質チェック
        self.check_data_quality()
        
        # PCA計算用の設定
        self.pca_batch_size = 100  # PCA計算のバッチサイズ
        self.max_cpu_percent = 80  # CPU使用率の上限

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
            
            # 極端な外れ値をチェック
            mean = self.df[col].mean()
            std = self.df[col].std()
            outliers = self.df[col].apply(lambda x: abs(x - mean) > 3 * std)
            # if outliers.any():
            #     logging.warning(f"Outliers detected in {col}")
        
        # OHLC価格の整合性チェック
        if not all(self.df['high'] >= self.df['low']):
            logging.error("High price is lower than low price")
        if not all(self.df['high'] >= self.df['open']) or not all(self.df['high'] >= self.df['close']):
            logging.error("High price is lower than open/close price")
        if not all(self.df['low'] <= self.df['open']) or not all(self.df['low'] <= self.df['close']):
            logging.error("Low price is higher than open/close price")

    def _check_cpu_usage(self):
        """CPU使用率をチェックし、必要に応じて一時停止"""
        if psutil.cpu_percent(interval=1) > self.max_cpu_percent:
            logging.debug("CPU使用率が高いため、処理を一時停止します")
            time.sleep(2)

    def calculate_indicators(self):
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

            results = []
            for idx, row in self.df.iterrows():
                if idx < min_required_records - 1:
                    continue

                # CPU使用率をチェック
                self._check_cpu_usage()

                window_data = self.df.iloc[max(0, idx - min_required_records + 1):idx + 1]
                
                try:
                    indicators = {
                        'date': row['date'].strftime('%Y%m%d'),
                        'ichimoku_tenkan': self._calculate_ichimoku_tenkan(window_data),
                        'ichimoku_kijun': self._calculate_ichimoku_kijun(window_data),
                        'ichimoku_senkou_a': self._calculate_ichimoku_senkou_a(window_data),
                        'ichimoku_senkou_b': self._calculate_ichimoku_senkou_b(window_data),
                        'adx': self._calculate_adx(window_data),
                        'bb_lower': self._calculate_bollinger_bands(window_data)['lower'],
                        'bb_middle': self._calculate_bollinger_bands(window_data)['middle'],
                        'bb_upper': self._calculate_bollinger_bands(window_data)['upper'],
                        'stoch_k': self._calculate_stochastic(window_data)['k'],
                        'stoch_d': self._calculate_stochastic(window_data)['d'],
                        'atr': self._calculate_atr(window_data),
                        'rsi': self._calculate_rsi(window_data),
                        'macd': self._calculate_macd(window_data),
                        'dynamic_threshold': self._calculate_dynamic_threshold(window_data),
                        'weekly_trend': self._calculate_weekly_trend(window_data),
                        'pca_signal': self._calculate_pca_signal(window_data)
                    }
                    
                    # インジケーターの妥当性チェック
                    if self._validate_indicators(indicators):
                        results.append(indicators)
                    # else:
                        # logging.warning(f"Invalid indicator values detected for date {row['date']}")
                        
                except Exception as e:
                    logging.error(f"Error calculating indicators for date {row['date']}: {str(e)}")
                    continue

            # forループ終了後
            expected_calculations = len(self.df) - (min_required_records - 1)
            if len(results) < expected_calculations:
                logging.warning(f"期待される計算件数は {expected_calculations} 件ですが、実際の計算結果は {len(results)} 件でした。データ不良の可能性があります。")
            return results
        except Exception as e:
            logging.error(f"Error in calculate_indicators: {str(e)}")
            raise

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

    def get_indicators(self):
        """全てのインジケーターを計算"""
        try:
            # 十分なデータがあるか確認
            min_required_records = 78  # 最低限必要なレコード数
            if len(self.df) < min_required_records:
                logging.warning(f"データ不足: {len(self.df)}レコード（必要数: {min_required_records}）")
                latest_row = self.df.iloc[-1]
                return [{
                    'date': latest_row['date'].strftime('%Y%m%d'),
                    'code': latest_row.get('code', ''),
                    'open': latest_row.get('open', 0),
                    'high': latest_row.get('high', 0),
                    'low': latest_row.get('low', 0),
                    'close': latest_row.get('close', 0),
                    'volume': latest_row.get('volume', 0),
                    'ichimoku_tenkan': None,
                    'ichimoku_kijun': None,
                    'ichimoku_senkou_a': None,
                    'ichimoku_senkou_b': None,
                    'adx': None,
                    'bb_lower': None,
                    'bb_middle': None,
                    'bb_upper': None,
                    'stoch_k': None,
                    'stoch_d': None,
                    'atr': None,
                    'rsi': None,
                    'macd': None,
                    'dynamic_threshold': None,
                    'weekly_trend': None,
                    'pca_signal': None
                }]

            results = []
            for idx, row in self.df.iterrows():
                if idx < min_required_records - 1:
                    continue

                window_data = self.df.iloc[max(0, idx - min_required_records + 1): idx + 1]
                
                try:
                    indicators = {
                        'date': row['date'].strftime('%Y%m%d'),
                        'code': row.get('code', ''),
                        'open': row.get('open', 0),
                        'high': row.get('high', 0),
                        'low': row.get('low', 0),
                        'close': row.get('close', 0),
                        'volume': row.get('volume', 0),
                        'ichimoku_tenkan': self._calculate_ichimoku_tenkan(window_data),
                        'ichimoku_kijun': self._calculate_ichimoku_kijun(window_data),
                        'ichimoku_senkou_a': self._calculate_ichimoku_senkou_a(window_data),
                        'ichimoku_senkou_b': self._calculate_ichimoku_senkou_b(window_data),
                        'adx': self._calculate_adx(window_data),
                        'bb_lower': self._calculate_bollinger_bands(window_data)['lower'],
                        'bb_middle': self._calculate_bollinger_bands(window_data)['middle'],
                        'bb_upper': self._calculate_bollinger_bands(window_data)['upper'],
                        'stoch_k': self._calculate_stochastic(window_data)['k'],
                        'stoch_d': self._calculate_stochastic(window_data)['d'],
                        'atr': self._calculate_atr(window_data),
                        'rsi': self._calculate_rsi(window_data),
                        'macd': self._calculate_macd(window_data),
                        'dynamic_threshold': self._calculate_dynamic_threshold(window_data),
                        'weekly_trend': self._calculate_weekly_trend(window_data),
                        'pca_signal': self._calculate_pca_signal(window_data)
                    }
                    
                    if self._validate_indicators(indicators):
                        results.append(indicators)
                    
                except Exception as e:
                    logging.error(f"Error calculating indicators for date {row['date']}: {str(e)}")
                    continue

            # forループ終了後
            expected_calculations = len(self.df) - (min_required_records - 1)
            if len(results) < expected_calculations:
                logging.warning(f"期待される計算件数は {expected_calculations} 件ですが、実際の計算結果は {len(results)} 件でした。データ不良の可能性があります。")
            return results
        except Exception as e:
            logging.error(f"Error in calculate_indicators: {str(e)}")
            raise

    def prepare_ohlc_data(self, current_date_data):
        ohlc_data = pd.DataFrame(current_date_data)
        ohlc_data.drop_duplicates(inplace=True)
        ohlc_data["date"] = pd.to_datetime(ohlc_data["date"], format="%Y%m%d", dayfirst=True)
        return ohlc_data
    
    def extract_series(self, ohlc_data):
        closes = pd.Series(ohlc_data["close"]).astype(float)
        high = pd.Series(ohlc_data["high"]).astype(float)
        low = pd.Series(ohlc_data["low"]).astype(float)
        return closes, high, low
    
    def _calculate_ichimoku(self, ohlc_data, high, low):
        if len(ohlc_data) >= 52:
            return calculate_ichimoku(high, low)
        else:
            return {"tenkan": 0, "kijun": 0, "senkou_a": 0, "senkou_b": 0}
    
    def _calculate_adx(self, data):
        if len(data) >= 14:
            adx_df = ta.adx(high=data['high'], low=data['low'], close=data['close'], length=14)
            return float(adx_df["ADX_14"].iloc[-1]) if "ADX_14" in adx_df.columns and not pd.isna(adx_df["ADX_14"].iloc[-1]) else 0
        else:
            return 0
    
    def _calculate_bollinger_bands(self, data):
        closes = data['close']
        if len(closes) >= 20:
            bb_df = ta.bbands(closes, length=20, std=2)
            return {
                "lower": float(bb_df["BBL_20_2.0"].iloc[-1]) if "BBL_20_2.0" in bb_df.columns else 0,
                "middle": float(bb_df["BBM_20_2.0"].iloc[-1]) if "BBM_20_2.0" in bb_df.columns else 0,
                "upper": float(bb_df["BBU_20_2.0"].iloc[-1]) if "BBU_20_2.0" in bb_df.columns else 0,
            }
        else:
            return {"lower": 0, "middle": 0, "upper": 0}

    def _calculate_stochastic(self, data):
        if len(data) >= 14:
            try:
                stoch_df = ta.stoch(high=data['high'], low=data['low'], close=data['close'], k=14, d=3, smooth_k=3)
                if stoch_df is None or stoch_df.empty or stoch_df["STOCHk_14_3_3"].isnull().all():
                    return {"k": 0, "d": 0}
                else:
                    return {
                        "k": float(stoch_df["STOCHk_14_3_3"].iloc[-1]),
                        "d": float(stoch_df["STOCHd_14_3_3"].iloc[-1]),
                    }
            except Exception:
                return {"k": 0, "d": 0}
        else:
            return {"k": 0, "d": 0}
        
    def _calculate_atr(self, data):
        """ATR（平均真実範囲）を計算"""
        df = data.copy()
        df.loc[:, 'H-L'] = df['high'] - df['low']
        df.loc[:, 'H-PC'] = abs(df['high'] - df['close'].shift(1))
        df.loc[:, 'L-PC'] = abs(df['low'] - df['close'].shift(1))
        df.loc[:, 'TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
        atr = df['TR'].rolling(window=14).mean()
        return atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0

    def _calculate_rsi(self, data, length=14):
        closes = data['close']
        if len(closes) < length:
            return 0
        try:
            rsi_series = ta.rsi(closes, length=length)
            return float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 0
        except Exception:
            return 0

    def _calculate_macd(self, data, fast=12, slow=26, signal=9):
        closes = data['close']
        if len(closes) < slow:
            return 0
        try:
            macd_df = ta.macd(closes, fast=fast, slow=slow, signal=signal)
            if "MACD_12_26_9" in macd_df.columns:
                macd_value = float(macd_df["MACD_12_26_9"].iloc[-1])
                return macd_value
            else:
                return 0
        except Exception:
            return 0

    def _calculate_ichimoku_tenkan(self, data):
        """一目均衡表の転換線を計算し、最新のスカラー値を返す"""
        high_9 = data['high'].rolling(window=9).max()
        low_9 = data['low'].rolling(window=9).min()
        result = (high_9 + low_9) / 2
        return float(result.iloc[-1]) if not pd.isna(result.iloc[-1]) else 0

    def _calculate_ichimoku_kijun(self, data):
        """一目均衡表の基準線を計算し、最新のスカラー値を返す"""
        high_26 = data['high'].rolling(window=26).max()
        low_26 = data['low'].rolling(window=26).min()
        result = (high_26 + low_26) / 2
        return float(result.iloc[-1]) if not pd.isna(result.iloc[-1]) else 0

    def _calculate_ichimoku_senkou_a(self, data):
        """一目均衡表の先行スパンAを計算し、最新のスカラー値を返す"""
        high_9 = data['high'].rolling(window=9).max()
        low_9 = data['low'].rolling(window=9).min()
        tenkan_series = (high_9 + low_9) / 2
        high_26 = data['high'].rolling(window=26).max()
        low_26 = data['low'].rolling(window=26).min()
        kijun_series = (high_26 + low_26) / 2
        senkou_a_series = ((tenkan_series + kijun_series) / 2).shift(26)
        return float(senkou_a_series.iloc[-1]) if not pd.isna(senkou_a_series.iloc[-1]) else 0

    def _calculate_ichimoku_senkou_b(self, data):
        """一目均衡表の先行スパンBを計算し、最新のスカラー値を返す"""
        high_52 = data['high'].rolling(window=52).max()
        low_52 = data['low'].rolling(window=52).min()
        senkou_b_series = ((high_52 + low_52) / 2).shift(26)
        return float(senkou_b_series.iloc[-1]) if not pd.isna(senkou_b_series.iloc[-1]) else 0

    def _calculate_dynamic_threshold(self, data):
        """動的閾値を計算"""
        atr = self._calculate_atr(data)
        close = data['close'].iloc[-1]
        atr_ratio = (atr / close) * 100
        base_threshold = 5.0
        return base_threshold * (atr_ratio / base_threshold)

    def _calculate_weekly_trend(self, data):
        """週別トレンドを計算"""
        weekly_data = data.resample('W', on='date').last()
        sma_5 = weekly_data['close'].rolling(window=5).mean()
        if len(sma_5) < 2:
            return "UNKNOWN"
        return "UP" if sma_5.iloc[-1] > sma_5.iloc[-2] else "DOWN"

    def _calculate_pca_signal(self, data):
        """PCAシグナルを計算（各インジケーターの時系列を用いてPCAを実施）"""
        try:
            # 十分なデータがなければPCAは実施できない
            if len(data) < 20:
                return 0
            # 各インジケーターの時系列を計算
            tenkan_series = (data['high'].rolling(window=9).max() + data['low'].rolling(window=9).min()) / 2
            kijun_series = (data['high'].rolling(window=26).max() + data['low'].rolling(window=26).min()) / 2
            adx_df = ta.adx(high=data['high'], low=data['low'], close=data['close'], length=14)
            adx_series = adx_df["ADX_14"] if "ADX_14" in adx_df.columns else pd.Series(0, index=data.index)
            bb_df = ta.bbands(data['close'], length=20, std=2)
            bb_lower_series = bb_df["BBL_20_2.0"] if "BBL_20_2.0" in bb_df.columns else pd.Series(0, index=data.index)
            bb_middle_series = bb_df["BBM_20_2.0"] if "BBM_20_2.0" in bb_df.columns else pd.Series(0, index=data.index)
            bb_upper_series = bb_df["BBU_20_2.0"] if "BBU_20_2.0" in bb_df.columns else pd.Series(0, index=data.index)
            stoch_df = ta.stoch(high=data['high'], low=data['low'], close=data['close'], k=14, d=3, smooth_k=3)
            stoch_k_series = stoch_df["STOCHk_14_3_3"] if "STOCHk_14_3_3" in stoch_df.columns else pd.Series(0, index=data.index)
            stoch_d_series = stoch_df["STOCHd_14_3_3"] if "STOCHd_14_3_3" in stoch_df.columns else pd.Series(0, index=data.index)
            # ATRの時系列計算
            df_atr = data.copy()
            df_atr['H-L'] = df_atr['high'] - df_atr['low']
            df_atr['H-PC'] = abs(df_atr['high'] - df_atr['close'].shift(1))
            df_atr['L-PC'] = abs(df_atr['low'] - df_atr['close'].shift(1))
            df_atr['TR'] = df_atr[['H-L', 'H-PC', 'L-PC']].max(axis=1)
            atr_series = df_atr['TR'].rolling(window=14).mean()
            rsi_series = ta.rsi(data['close'], length=14)
            macd_df = ta.macd(data['close'], fast=12, slow=26, signal=9)
            macd_series = macd_df["MACD_12_26_9"] if "MACD_12_26_9" in macd_df.columns else pd.Series(0, index=data.index)
            # DataFrame作成（各列は時系列データ）
            indicators = pd.DataFrame({
            'ichimoku_tenkan': tenkan_series,
            'ichimoku_kijun': kijun_series,
            'adx': adx_series,
            'bb_lower': bb_lower_series,
            'bb_middle': bb_middle_series,
            'bb_upper': bb_upper_series,
            'stoch_k': stoch_k_series,
            'stoch_d': stoch_d_series,
            'atr': atr_series,
            'rsi': rsi_series,
            'macd': macd_series
            }, index=data.index)
            # 欠損値、無限大のチェックと補完
            indicators = indicators.ffill().bfill()
            if not indicators.replace([np.inf, -np.inf], np.nan).notna().all().all():
                # logging.warning("無限大または非数値が検出されました")
                return 0
            # PCAには最低20日分の行が必要
            if len(indicators) >= 20:
                for col in indicators.columns:
                    mean = indicators[col].mean()
                    std = indicators[col].std()
                    outliers = indicators[col].apply(lambda x: abs(x - mean) > 3 * std)
                    if outliers.any():
                        logging.debug(f"{col}で異常値を検出: {indicators[col][outliers].values}")
                    scaler = StandardScaler()
                    scaled_data = scaler.fit_transform(indicators)
                    pca = PCA(n_components=3)
                    principal_components = pca.fit_transform(scaled_data)
                    explained_variance_ratio = pca.explained_variance_ratio_
                    logging.debug(f"PCA説明寄与率: {explained_variance_ratio}")
                    return float(principal_components[-1, 0])
                return 0
        except Exception as e:
            logging.error(f"PCAシグナル計算エラー: {str(e)}")
            return 0


def calculate_ichimoku(high, low):
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
    senkou_b_high = high.rolling(window=52).max()
    senkou_b_low = low.rolling(window=52).min()
    senkou_b = (senkou_b_high + senkou_b_low) / 2
    senkou_b = senkou_b.shift(26)
    return {
        "tenkan": float(tenkan.iloc[-1]) if not pd.isna(tenkan.iloc[-1]) else 0,
        "kijun": float(kijun.iloc[-1]) if not pd.isna(kijun.iloc[-1]) else 0,
        "senkou_a": float(senkou_a.iloc[-1]) if not pd.isna(senkou_a.iloc[-1]) else 0,
        "senkou_b": float(senkou_b.iloc[-1]) if not pd.isna(senkou_b.iloc[-1]) else 0,
    }
