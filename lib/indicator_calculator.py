import numpy as np
import pandas as pd
import pandas_ta as ta
from sklearn.decomposition import PCA


class IndicatorCalculator:
    def __init__(self, price_data):
        self.price_data = price_data  # 例: [{'code': 'XXXX', 'date': '20250212', 'open': 123.4, 'high':135.6, ...}, ...]

    def get_indicators(self):
        # Price_data をDataFrameに変換
        df = pd.DataFrame(self.price_data)
        # 例：'date'が "YYYYMMDD"形式の場合、datetimeに変換
        df['date'] = pd.to_datetime(df['date'], format="%Y%m%d")
        df.sort_values('date', inplace=True)

        # -------------------------------
        # (1) 動的パラメータ調整（ATR・ATR_ratio・dynamic_threshold）
        # ※ATRは「True Range」の移動平均として計算
        df['H-L']   = df['high'] - df['low']
        df['H-PC']  = np.abs(df['high'] - df['close'].shift(1))
        df['L-PC']  = np.abs(df['low'] - df['close'].shift(1))
        df['TR']    = df[['H-L','H-PC','L-PC']].max(axis=1)
        df['ATR']   = df['TR'].rolling(window=20).mean()
        df['ATR_ratio'] = (df['ATR'] / df['close']) * 100
        base_threshold = 5.0
        # サンプルコードに倣い、シンプルにATR_ratioをdynamic_thresholdとする
        df['dynamic_threshold'] = df['ATR_ratio']

        # -------------------------------
        # (2) 多時系列分析: 週足データへの変換と週足SMAによるトレンド判定
        df.set_index('date', inplace=True)
        df_weekly = df.resample('W').last()
        df_weekly['SMA_5'] = df_weekly['close'].rolling(window=5).mean()
        if len(df_weekly) >= 2:
            weekly_trend = "UP" if df_weekly['SMA_5'].iloc[-1] > df_weekly['SMA_5'].iloc[-2] else "DOWN"
        else:
            weekly_trend = "UNKNOWN"
        df['weekly_trend'] = weekly_trend
        df.reset_index(inplace=True)

        # -------------------------------
        # Compute missing indicators before PCA

        # Compute Ichimoku values using the entire high and low series
        ichimoku = calculate_ichimoku(df['high'], df['low'])
        df['ichimoku_tenkan'] = ichimoku['tenkan']
        df['ichimoku_kijun'] = ichimoku['kijun']
        df['ichimoku_senkou_a'] = ichimoku['senkou_a']
        df['ichimoku_senkou_b'] = ichimoku['senkou_b']

        # Compute Bollinger Bands using the close series
        bb = self.calculate_bollinger_bands(df['close'])
        df['bb_lower'] = bb['lower']
        df['bb_middle'] = bb['middle']
        df['bb_upper'] = bb['upper']

        # Compute Stochastic using extracted series
        closes, high_series, low_series = self.extract_series(df)
        stoch = self.calculate_stochastic(df, high_series, low_series, closes)
        df['stoch_k'] = stoch['stoch_k']
        df['stoch_d'] = stoch['stoch_d']

        # Compute RSI using close series
        df['rsi'] = self.calculate_rsi(df['close'])

        # Compute MACD using close series
        df['macd'] = self.calculate_macd(df['close'])

        # Compute ADX using the current high, low, close data
        adx_value = self.calculate_adx(df, df['high'], df['low'], df['close'])
        df['adx'] = adx_value

        # -------------------------------
        # (3) インジケーターの組み合わせ最適化：PCAによる次元削減
        # 使用するインジケーターのカラム（既存値。なければNaNになるため後でfillna）
        indicator_cols = ['ichimoku_tenkan', 'ichimoku_kijun', 'adx', 'bb_lower', 'bb_middle', 'bb_upper', 'stoch_k', 'stoch_d', 'ATR', 'rsi', 'macd']
        for col in indicator_cols:
            if col not in df.columns:
                df[col] = np.nan
        pca_df = df[indicator_cols].dropna()
        if not pca_df.empty:
            pca = PCA(n_components=3)
            principal_components = pca.fit_transform(pca_df)
            # ここでは最新行の第一主成分をpca_signalとして利用
            pca_signal = principal_components[-1, 0]
        else:
            pca_signal = 0
        df['pca_signal'] = pca_signal  # 同じ値を全行に付与

        # -------------------------------
        # インジケーター算出結果を、既存のものに加えて出力
        indicators = []
        for _, row in df.iterrows():
            record = {
                "code": row.get("code"),
                "date": row['date'].strftime("%Y%m%d"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "ichimoku_tenkan": row.get("ichimoku_tenkan") if not pd.isna(row.get("ichimoku_tenkan")) else 0,
                "ichimoku_kijun": row.get("ichimoku_kijun") if not pd.isna(row.get("ichimoku_kijun")) else 0,
                "ichimoku_senkou_a": row.get("ichimoku_senkou_a") if not pd.isna(row.get("ichimoku_senkou_a")) else 0,
                "ichimoku_senkou_b": row.get("ichimoku_senkou_b") if not pd.isna(row.get("ichimoku_senkou_b")) else 0,
                "adx": row.get("adx") if not pd.isna(row.get("adx")) else 0,
                "bb_lower": row.get("bb_lower") if not pd.isna(row.get("bb_lower")) else 0,
                "bb_middle": row.get("bb_middle") if not pd.isna(row.get("bb_middle")) else 0,
                "bb_upper": row.get("bb_upper") if not pd.isna(row.get("bb_upper")) else 0,
                "stoch_k": row.get("stoch_k") if not pd.isna(row.get("stoch_k")) else 0,
                "stoch_d": row.get("stoch_d") if not pd.isna(row.get("stoch_d")) else 0,
                "atr": row.get("ATR") if not pd.isna(row.get("ATR")) else 0,
                "rsi": row.get("rsi") if not pd.isna(row.get("rsi")) else 0,
                "macd": row.get("macd") if not pd.isna(row.get("macd")) else 0,
                "dynamic_threshold": row.get("dynamic_threshold") if not pd.isna(row.get("dynamic_threshold")) else 0,
                "weekly_trend": row.get("weekly_trend"),
                "pca_signal": row.get("pca_signal") if row.get("pca_signal") is not None else 0
            }
            indicators.append(record)
        return indicators

    def prepare_ohlc_data(self, current_date_data):
        ohlc_data = pd.DataFrame(current_date_data)
        ohlc_data.drop_duplicates(inplace=True)
        # print("ohlc_data:", ohlc_data)
        ohlc_data["date"] = pd.to_datetime(ohlc_data["date"], format="%Y%m%d",dayfirst=True)
        return ohlc_data
    
    def extract_series(self, ohlc_data):
        closes = pd.Series(ohlc_data["close"]).astype(float)
        high = pd.Series(ohlc_data["high"]).astype(float)
        low = pd.Series(ohlc_data["low"]).astype(float)
        return closes, high, low
    
    def calculate_ichimoku(self, ohlc_data, high, low):
        if len(ohlc_data) >= 52:
            return calculate_ichimoku(high, low)
        else:
            return {"tenkan": 0, "kijun": 0, "senkou_a": 0, "senkou_b": 0}
    
    def calculate_adx(self, ohlc_data, high, low, closes):
        if len(ohlc_data) >= 14:
            adx_df = ta.adx(high=high, low=low, close=closes, length=14)
            return float(adx_df["ADX_14"].iloc[-1]) if "ADX_14" in adx_df.columns else None
        else:
            return 0
    
    def calculate_bollinger_bands(self, closes):
        if len(closes) >= 20:
            bb_df = ta.bbands(closes, length=20, std=2)
            return {
                "lower": float(bb_df["BBL_20_2.0"].iloc[-1]) if "BBL_20_2.0" in bb_df.columns else 0,
                "middle": float(bb_df["BBM_20_2.0"].iloc[-1]) if "BBM_20_2.0" in bb_df.columns else 0,
                "upper": float(bb_df["BBU_20_2.0"].iloc[-1]) if "BBU_20_2.0" in bb_df.columns else 0,
            }
        else:
            # データが足りない場合は必ず辞書で返す
            return {"lower": 0, "middle": 0, "upper": 0}

    def calculate_stochastic(self, ohlc_data, high, low, closes):
        if len(ohlc_data) >= 14:
            try:
                stoch_df = ta.stoch(high=high, low=low, close=closes, k=14, d=3, smooth_k=3)
                if stoch_df is None or stoch_df.empty or stoch_df["STOCHk_14_3_3"].isnull().all():
                    return {"stoch_k": 0, "stoch_d": 0}
                else:
                    return {
                        "stoch_k": float(stoch_df["STOCHk_14_3_3"].iloc[-1]),
                        "stoch_d": float(stoch_df["STOCHd_14_3_3"].iloc[-1]),
                    }
            except Exception:
                # print("Stochastic calculation error:", e)
                return {"stoch_k": 0, "stoch_d": 0}
        else:
            return {"stoch_k": 0, "stoch_d": 0}
        
    def calculate_atr(self, ohlc_data, high, low, closes):
        if len(ohlc_data) >= 14:
            atr_series = ta.atr(high=high, low=low, close=closes, length=14)
            return float(atr_series.iloc[-1])
        else:
            return 0

    def calculate_rsi(self, closes, length=14):
        if len(closes) < length:
            return 0
        try:
            rsi_series = ta.rsi(closes, length=length)
            return float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 0
        except Exception:
            return 0

    def calculate_macd(self, closes, fast=12, slow=26, signal=9):
        if len(closes) < slow:
            return 0
        try:
            macd_df = ta.macd(closes, fast=fast, slow=slow, signal=signal)
            # MACDラインのみを使う（MACD_12_26_9）
            if "MACD_12_26_9" in macd_df.columns:
                macd_value = float(macd_df["MACD_12_26_9"].iloc[-1])
                return macd_value
            else:
                return 0
        except Exception:
            return 0


def calculate_ichimoku(high, low):
    # デバッグ情報
    # print("High values head:")
    # print(high.head())
    # print("\nLow values head:")
    # print(low.head())

    # 先行スパンBのデバッグ
    senkou_b_high = high.rolling(window=52).max()
    senkou_b_low = low.rolling(window=52).min()
    # print("\nsenkou_b_high head:")
    # print(senkou_b_high.head())
    # print("\nsenkou_b_low head:")
    # print(senkou_b_low.head())

    # 先行スパンB計算
    senkou_b = (senkou_b_high + senkou_b_low) / 2

    # シフト前の値を確認
    # print("\nsenkou_b before shift:")
    # print(senkou_b.tail())

    # シフト処理（26日先行）
    senkou_b = senkou_b.shift(26)

    # シフト後の値を確認
    # print("\nsenkou_b after shift:")
    # print(senkou_b.tail())

    # 転換線 = (n日間の高値 + n日間の安値) / 2
    tenkan_high = high.rolling(window=9).max()
    tenkan_low = low.rolling(window=9).min()
    tenkan = (tenkan_high + tenkan_low) / 2

    # 基準線 = (n日間の高値 + n日間の安値) / 2
    kijun_high = high.rolling(window=26).max()
    kijun_low = low.rolling(window=26).min()
    kijun = (kijun_high + kijun_low) / 2

    # 先行スパンA = (転換線 + 基準線) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)

    # 先行スパンBの計算を修正
    senkou_b_high = high.rolling(window=52).max()
    senkou_b_low = low.rolling(window=52).min()
    senkou_b = (senkou_b_high + senkou_b_low) / 2

    # シフト処理を修正（26日先行）
    senkou_b = senkou_b.shift(26)

    # 計算結果の確認
    # print(f"senkou_b values:\n{senkou_b.tail()}")

    return {
        "tenkan": float(tenkan.iloc[-1]) if not pd.isna(tenkan.iloc[-1]) else 0,
        "kijun": float(kijun.iloc[-1]) if not pd.isna(kijun.iloc[-1]) else 0,
        "senkou_a": float(senkou_a.iloc[-1]) if not pd.isna(senkou_a.iloc[-1]) else 0,
        "senkou_b": float(senkou_b.iloc[-1]) if not pd.isna(senkou_b.iloc[-1]) else 0,
    }
