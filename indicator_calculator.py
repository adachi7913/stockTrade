import numpy as np
import pandas as pd
import pandas_ta as ta


class IndicatorCalculator:
    def __init__(self, data):
        self.data = data

    def get_indicators(self):
        indicators_by_date = {}
        data_length = len(self.data)
    
        for i in range(data_length):
            current_date_data = self.data[0 : i + 1]
            ohlc_data = self.prepare_ohlc_data(current_date_data)
            closes, high, low = self.extract_series(ohlc_data)
    
            indicators = {
                "ichimoku": self.calculate_ichimoku(ohlc_data, high, low),
                "adx": self.calculate_adx(ohlc_data, high, low, closes),
                "bb": self.calculate_bollinger_bands(closes),
                "stoch": self.calculate_stochastic(ohlc_data, high, low, closes),
                "atr": self.calculate_atr(ohlc_data, high, low, closes),
            }
    
            indicators_by_date[self.data[i]["date"]] = indicators
        return indicators_by_date
    
    def prepare_ohlc_data(self, current_date_data):
        ohlc_data = pd.DataFrame(current_date_data)
        ohlc_data.drop_duplicates(inplace=True)
        ohlc_data["date"] = pd.to_datetime(ohlc_data["date"], dayfirst=True)
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
            except Exception as e:
                print("Stochastic calculation error:", e)
                return {"stoch_k": 0, "stoch_d": 0}
        else:
            return {"stoch_k": 0, "stoch_d": 0}
        
    def calculate_atr(self, ohlc_data, high, low, closes):
        if len(ohlc_data) >= 14:
            atr_series = ta.atr(high=high, low=low, close=closes, length=14)
            return float(atr_series.iloc[-1])
        else:
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
    print("\nsenkou_b_high head:")
    print(senkou_b_high.head())
    print("\nsenkou_b_low head:")
    print(senkou_b_low.head())

    # 先行スパンB計算
    senkou_b = (senkou_b_high + senkou_b_low) / 2

    # シフト前の値を確認
    print("\nsenkou_b before shift:")
    print(senkou_b.tail())

    # シフト処理（26日先行）
    senkou_b = senkou_b.shift(26)

    # シフト後の値を確認
    print("\nsenkou_b after shift:")
    print(senkou_b.tail())

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
    print(f"senkou_b values:\n{senkou_b.tail()}")

    return {
        "tenkan": float(tenkan.iloc[-1]) if not pd.isna(tenkan.iloc[-1]) else 0,
        "kijun": float(kijun.iloc[-1]) if not pd.isna(kijun.iloc[-1]) else 0,
        "senkou_a": float(senkou_a.iloc[-1]) if not pd.isna(senkou_a.iloc[-1]) else 0,
        "senkou_b": float(senkou_b.iloc[-1]) if not pd.isna(senkou_b.iloc[-1]) else 0,
    }
