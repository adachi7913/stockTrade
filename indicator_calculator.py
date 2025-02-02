import numpy as np
import math
import pandas as pd
import pandas_ta as ta


class IndicatorCalculator:
    def __init__(self, data):
        self.data = data

    def get_indicators(self):
        indicators_by_date = {}
        data_length = len(self.data)

        for i in range(data_length):
            # 現在の日付から過去すべてのデータを使用
            current_date_data = self.data[0 : i + 1]

            # DataFrame作成（重複除去、日付をDatetimeに変換、昇順ソート）
            ohlc_data = pd.DataFrame(current_date_data)
            ohlc_data.drop_duplicates(inplace=True)
            ohlc_data["date"] = pd.to_datetime(ohlc_data["date"], dayfirst=True)
            # ohlc_data = ohlc_data.set_index("date").sort_index(ascending=True)

            # シリーズ作成（float変換＆ソート）
            closes = pd.Series(ohlc_data["close"]).astype(float)
            high = pd.Series(ohlc_data["high"]).astype(float)
            low = pd.Series(ohlc_data["low"]).astype(float)
            volume = pd.Series(ohlc_data["volume"]).astype(float)

            # 初期値の設定
            ichimoku_values = 0

            # -------------------------------------------
            # 1. 一目均衡表 (Ichimoku Kinko Hyo)
            if len(ohlc_data) >= 52:
                ichimoku_values = calculate_ichimoku(high, low, closes)
            else:
                ichimoku_values = {
                    "tenkan": 0,
                    "kijun": 0,
                    "senkou_a": 0,
                    "senkou_b": 0,
                }

            # -------------------------------------------
            # 2. ADX (Average Directional Index)
            # 標準パラメーター: period=14
            if len(ohlc_data) >= 14:
                adx_df = ta.adx(high=high, low=low, close=closes, length=14)
                # pandas_ta.adx() は 'ADX_14' カラムを返す
                adx_value = (
                    float(adx_df["ADX_14"].iloc[-1])
                    if "ADX_14" in adx_df.columns
                    else None
                )
            else:
                adx_value = 0

            # -------------------------------------------
            # 3. ボリンジャーバンド (Bollinger Bands)
            # 標準パラメーター: length=20, std=2
            if len(closes) >= 20:
                bb_df = ta.bbands(closes, length=20, std=2)
                # 一般的なカラムは: 'BBL_20_2.0', 'BBM_20_2.0', 'BBU_20_2.0'
                bb_values = {
                    "lower": (
                        float(bb_df["BBL_20_2.0"].iloc[-1])
                        if "BBL_20_2.0" in bb_df.columns
                        else None
                    ),
                    "middle": (
                        float(bb_df["BBM_20_2.0"].iloc[-1])
                        if "BBM_20_2.0" in bb_df.columns
                        else None
                    ),
                    "upper": (
                        float(bb_df["BBU_20_2.0"].iloc[-1])
                        if "BBU_20_2.0" in bb_df.columns
                        else None
                    ),
                }
            else:
                bb_values = 0

            # -------------------------------------------
            # 4. ストキャスティクス (Stochastic Oscillator)
            # 標準パラメーター: %K=14, %D=3, smooth_k=3
            if len(ohlc_data) >= 14:
                try:
                    stoch_df = ta.stoch(
                        high=high, low=low, close=closes, k=14, d=3, smooth_k=3
                    )
                    # カラム例: 'STOCHk_14_3_3', 'STOCHd_14_3_3'
                    # もし計算結果が全部 NaN ならチェックしておく
                    if (
                        stoch_df is None
                        or stoch_df.empty
                        or stoch_df["STOCHk_14_3_3"].isnull().all()
                    ):
                        stoch_values = {"stoch_k": None, "stoch_d": None}
                    else:
                        stoch_values = {
                            "stoch_k": float(stoch_df["STOCHk_14_3_3"].iloc[-1]),
                            "stoch_d": float(stoch_df["STOCHd_14_3_3"].iloc[-1]),
                        }
                except Exception as e:
                    print("Stochastic calculation error:", e)
                    stoch_values = {"stoch_k": None, "stoch_d": None}
            else:
                stoch_values = 0

            # -------------------------------------------
            # 5. ATR (Average True Range)
            # 標準パラメーター: period=14
            if len(ohlc_data) >= 14:
                atr_series = ta.atr(high=high, low=low, close=closes, length=14)
                atr_value = float(atr_series.iloc[-1])
            else:
                atr_value = 0

            # 指標をまとめる
            indicators = {
                "ichimoku": ichimoku_values,
                "adx": adx_value,
                "bb": bb_values,
                "stoch": stoch_values,
                "atr": atr_value,
            }

            # 結果を、スライスの先頭の日付をキーにして格納
            indicators_by_date[self.data[i]["date"]] = indicators
        return indicators_by_date


def calculate_ichimoku(high, low, close):
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
