import numpy as np
import pandas as pd
import pandas_ta as ta
from sklearn.decomposition import PCA


class IndicatorCalculator:
    def __init__(self, price_data, atr_period=20, rsi_length=14, macd_fast=12, macd_slow=26, macd_signal=9, adx_length=14, pca_window=60, stoch_k=14, stoch_d=3, stoch_smooth=3, bb_length=20, bb_std=2):
        self.price_data = price_data  # 例: [{'code': 'XXXX', 'date': '20250212', 'open': 123.4, 'high':135.6, ...}, ...]
        self.atr_period = atr_period
        self.rsi_length = rsi_length
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.adx_length = adx_length
        self.pca_window = pca_window
        self.stoch_k = stoch_k
        self.stoch_d = stoch_d
        self.stoch_smooth = stoch_smooth
        self.bb_length = bb_length
        self.bb_std = bb_std

    def get_indicators(self):
        # Price_data をDataFrameに変換
        df = pd.DataFrame(self.price_data)
        # 'date' を datetime に変換 (フォーマット "YYYYMMDD")
        df['date'] = pd.to_datetime(df['date'], format="%Y%m%d")
        df.sort_values('date', inplace=True)
        df.reset_index(drop=True, inplace=True)

        # -------------------------------
        # (1) 動的パラメータ調整（ATR・ATR_ratio・dynamic_threshold）
        # ATR計算用のヘルパー関数を定義
        def calculate_atr(df, period=20):
            df['H-L'] = df['high'] - df['low']
            df['H-PC'] = np.abs(df['high'] - df['close'].shift(1))
            df['L-PC'] = np.abs(df['low'] - df['close'].shift(1))
            df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
            atr = df['TR'].rolling(window=period).mean()
            return atr

        # ATRを計算（atr_period日分）
        df['ATR'] = calculate_atr(df, period=self.atr_period)
        # ATR_ratio を計算（終値に対するATRの割合 [%]）
        df['ATR_ratio'] = (df['ATR'] / df['close']) * 100

        # 基準閾値（ここでは5%をベースとして設定）
        base_threshold = 5.0
        # ボラティリティに応じた動的閾値の算出
        df['dynamic_threshold'] = base_threshold * (df['ATR_ratio'] / base_threshold)

        # -------------------------------
        # (2) 一目均衡表 (Ichimoku) の日毎計算
        df['tenkan'] = (df['high'].rolling(window=9).max() + df['low'].rolling(window=9).min()) / 2
        df['kijun'] = (df['high'].rolling(window=26).max() + df['low'].rolling(window=26).min()) / 2
        df['senkou_a'] = ((df['tenkan'] + df['kijun']) / 2).shift(26)
        df['senkou_b'] = ((df['high'].rolling(window=52).max() + df['low'].rolling(window=52).min()) / 2).shift(26)
        # 統一のため後続で使用する列名にリネーム
        df['ichimoku_tenkan'] = df['tenkan']
        df['ichimoku_kijun'] = df['kijun']
        df['ichimoku_senkou_a'] = df['senkou_a']
        df['ichimoku_senkou_b'] = df['senkou_b']

        # -------------------------------
        # (3) Bollinger Bands の計算（日毎）
        bb_df = ta.bbands(df['close'], length=self.bb_length, std=self.bb_std)
        if not bb_df.empty:
            lower_key = f"BBL_{self.bb_length}_{self.bb_std:.1f}"
            middle_key = f"BBM_{self.bb_length}_{self.bb_std:.1f}"
            upper_key = f"BBU_{self.bb_length}_{self.bb_std:.1f}"
            if lower_key in bb_df.columns and middle_key in bb_df.columns and upper_key in bb_df.columns:
                df['bb_lower'] = bb_df[lower_key]
                df['bb_middle'] = bb_df[middle_key]
                df['bb_upper'] = bb_df[upper_key]
            else:
                df['bb_lower'] = bb_df.iloc[:,0]
                df['bb_middle'] = bb_df.iloc[:,1]
                df['bb_upper'] = bb_df.iloc[:,2]
        else:
            df['bb_lower'] = 0
            df['bb_middle'] = 0
            df['bb_upper'] = 0

        # -------------------------------
        # (4) Stochastic の計算（日毎）
        stoch_df = ta.stoch(high=df['high'], low=df['low'], close=df['close'], k=self.stoch_k, d=self.stoch_d, smooth_k=self.stoch_smooth)
        stoch_k_key = f"STOCHk_{self.stoch_k}_{self.stoch_d}_{self.stoch_smooth}"
        stoch_d_key = f"STOCHd_{self.stoch_k}_{self.stoch_d}_{self.stoch_smooth}"
        if not stoch_df.empty and stoch_k_key in stoch_df.columns and not stoch_df[stoch_k_key].isnull().all():
            df['stoch_k'] = stoch_df[stoch_k_key]
            df['stoch_d'] = stoch_df[stoch_d_key]
        else:
            df['stoch_k'] = 0
            df['stoch_d'] = 0

        # -------------------------------
        # (5) RSI の計算（日毎）
        rsi_series = ta.rsi(df['close'], length=self.rsi_length)
        df['rsi'] = rsi_series

        # -------------------------------
        # (6) MACD の計算（日毎）
        macd_df = ta.macd(df['close'], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)
        macd_key = f"MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}"
        if macd_key in macd_df.columns:
            df['macd'] = macd_df[macd_key]
        else:
            df['macd'] = 0

        # -------------------------------
        # (7) ADX の計算（日毎）
        adx_df = ta.adx(high=df['high'], low=df['low'], close=df['close'], length=self.adx_length)
        adx_key = f"ADX_{self.adx_length}"
        if adx_key in adx_df.columns:
            df['adx'] = adx_df[adx_key]
        else:
            df['adx'] = 0

        # -------------------------------
        # (8) PCAによる次元削減（日毎計算、ローリングウィンドウを使用）
        indicator_cols = ['ichimoku_tenkan', 'ichimoku_kijun', 'adx', 'bb_lower', 'bb_middle', 'bb_upper', 'stoch_k', 'stoch_d', 'ATR', 'rsi', 'macd']
        rolling_window = self.pca_window  # pca_window日分のローリングウィンドウを使用
        pca_signal_list = [np.nan] * len(df)
        pca = PCA(n_components=3)
        for i in range(rolling_window - 1, len(df)):
            window_data = df.iloc[i - rolling_window + 1:i + 1][indicator_cols].ffill().bfill()
            if len(window_data) == rolling_window:
                try:
                    principal_components = pca.fit_transform(window_data)
                    pca_signal_list[i] = principal_components[-1, 0]
                except Exception as e:
                    pca_signal_list[i] = np.nan
            else:
                pca_signal_list[i] = np.nan
        df['pca_signal'] = pca_signal_list

        # -------------------------------
        # NaN補完: 線形補間および前日値での補完を実施
        # 数値型カラムのみを抽出
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        # 数値型カラムに対してのみ補間を実施
        for col in numeric_cols:
            df[col] = df[col].interpolate(method='linear', limit_direction='both')
            df[col] = df[col].ffill().bfill()
        
        # 非数値型カラムはffill/bfillのみ実施
        object_cols = df.select_dtypes(include=['object']).columns
        for col in object_cols:
            df[col] = df[col].ffill().bfill()

        # -------------------------------
        # (9) 週別トレンドの計算（各週ごとに判定し、日々のレコードにマッピング）
        df_indexed = df.set_index('date')
        df_weekly = df_indexed.resample('W').last()
        df_weekly['SMA_5'] = df_weekly['close'].rolling(window=5).mean()
        df_weekly['weekly_trend'] = "UNKNOWN"
        for i in range(1, len(df_weekly)):
            if pd.notna(df_weekly['SMA_5'].iloc[i]) and pd.notna(df_weekly['SMA_5'].iloc[i-1]):
                trend = "UP" if df_weekly['SMA_5'].iloc[i] > df_weekly['SMA_5'].iloc[i-1] else "DOWN"
                df_weekly.iloc[i, df_weekly.columns.get_loc('weekly_trend')] = trend
            else:
                df_weekly.iloc[i, df_weekly.columns.get_loc('weekly_trend')] = "UNKNOWN"
        df_weekly = df_weekly.reset_index()
        df_weekly['week'] = df_weekly['date'].dt.to_period('W')
        df['week'] = df['date'].dt.to_period('W')
        mapping = df_weekly.set_index('week')['weekly_trend']
        df['weekly_trend'] = df['week'].map(mapping)
        df.drop(columns=['week'], inplace=True)
        df.reset_index(drop=True, inplace=True)

        # -------------------------------
        # (10) インジケーター算出結果のフォーマット
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
