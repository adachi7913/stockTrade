
import numpy as np
import math  # math モジュールを追加
import pandas as pd
import pandas_ta as ta  # pandas_ta モジュールを追加

class IndicatorCalculator:
    def __init__(self, data):
        self.data = data

    def get_indicators(self):
        indicators_by_date = {}
        data_length = len(self.data)
        
        for i in range(data_length):
            if i + 26 <= data_length:
                # 末尾からのスライス: [i:i+26] で26日分を取得
                current_date_data = self.data[i:i+26]
                
                # データ長の確認
                # print(f"処理中の期間: {current_date_data[0]['date']} から {current_date_data[-1]['date']}")
                # print(f"データ件数: {len(current_date_data)}")
                
                df = pd.DataFrame(current_date_data) # DataFrame作成時にdateカラムをインデックスに設定しない
                # print(f"df.head():\n{df.head()}") # DataFrameの内容を確認
                # print(f"df.columns after creation: {df.columns}") # DataFrame作成直後のカラム名を確認

                ohlc_data = pd.DataFrame(current_date_data) # 各iterationで新しいDataFrameを作成 (修正)
                ohlc_data.drop_duplicates(inplace=True) # 日付の重複を削除
                
                # 明示的に降順から昇順に並び替え
                ohlc_data['date'] = pd.to_datetime(ohlc_data['date'], dayfirst=True)
                ohlc_data = ohlc_data.set_index('date')
                ohlc_data = ohlc_data.sort_index(ascending=True)  # 古い順にソート

                # 確認用プリント
                # print("Is index sorted:", ohlc_data.index.is_monotonic_increasing)
                # print("First date:", ohlc_data.index[0])
                # print("Last date:", ohlc_data.index[-1])

                # Seriesの作成とデータチェック（インデックスを保持）
                closes = pd.Series(ohlc_data['close'])
                closes = closes.astype(float)  # float型に明示的に変換
                closes = closes.sort_index()   # 時系列順にソート

                print("データ件数:", len(closes))
                print("closes head:\n", closes.head())
                print("closes tail:\n", closes.tail())

                # MACDの計算（values属性を使用せずにSeriesのまま渡す）
                if len(closes) >= 26:
                    try:
                        macd_dict = calculate_macd(closes)
                        print("MACD values:", macd_dict)
                    except Exception as e:
                        print(f"MACD calculation error: {e}")
                        macd_dict = {'macd': 0, 'signal': 0, 'histogram': 0}
                else:
                    print("Insufficient data for MACD")
                    macd_dict = {'macd': 0, 'signal': 0, 'histogram': 0}
                print("MACD_dict:", macd_dict)
                volumes = pd.Series(ohlc_data['volume'])

                # VWAP計算部分の修正
                ohlc_data = pd.DataFrame(current_date_data)
                ohlc_data['date'] = pd.to_datetime(ohlc_data['date'], dayfirst=True)
                ohlc_data = ohlc_data.set_index('date')
                ohlc_data = ohlc_data.sort_index()

                # 各Seriesの作成（DatetimeIndexを保持）
                high = pd.Series(ohlc_data['high'])
                low = pd.Series(ohlc_data['low'])
                close = pd.Series(ohlc_data['close'])
                volume = pd.Series(ohlc_data['volume'])

                # print("Index type:", type(high.index))
                # print("Index sample:", high.index[:5])

                # データを昇順にソート
                high = high.sort_index()
                low = low.sort_index()
                close = close.sort_index()
                volume = volume.sort_index()
                # 各種指標の計算
                indicators = {
                    'atr': ta.atr(high=ohlc_data['high'], low=ohlc_data['low'], close=ohlc_data['close']).iloc[-1] if len(ohlc_data) >= 14 else 0, # データが14日分以上ある場合のみ計算
                    'rsi': ta.rsi(closes).iloc[-1] if len(ohlc_data) >= 14 else 0, # データが14日分以上ある場合のみ計算
                    'bb': ta.bbands(closes).iloc[-1].to_dict() if len(closes) >= 20 else 0, # データが20日分以上ある場合のみ計算
                    'avgVolume': ta.sma(volumes, 20).iloc[-1] if len(volumes) >= 20 else 0, # データが20日分以上ある場合のみ計算, sma 関数をpandas_taで置き換え
                    'last5ATR': [ta.atr(high=ohlc_data[-(14 + j):]['high'], low=ohlc_data[-(14 + j):]['low'], close=ohlc_data[-(14 + j):]['close']).iloc[-1] if len(ohlc_data[-(14 + j):]) >= 14 else 0 for j in range(5)], # calculate_atr を ta.atr に置き換え
                    'vwap8': ta.vwap(high=high, low=low, close=close, volume=volume, period=8, anchor='D').iloc[-1] if len(ohlc_data) >= 8 else 0, # データが8日分以上ある場合のみ計算
                    'macd': macd_dict, # データが26日分以上ある場合のみ計算, NoneType エラー対策
                }
                indicators_by_date[self.data[i]['date']] = indicators # 日付をキーとして格納
        return indicators_by_date

def calculate_macd(closes, fast_period=12, slow_period=26, signal_period=9):
    """
    MACDを計算する独自実装
    """
    # EMAs
    exp1 = closes.ewm(span=fast_period, adjust=False).mean()
    exp2 = closes.ewm(span=slow_period, adjust=False).mean()
    
    # MACD Line
    macd_line = exp1 - exp2
    
    # Signal Line
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    
    # Histogram
    histogram = macd_line - signal_line
    
    return {
        'macd': float(macd_line.iloc[-1]),
        'signal': float(signal_line.iloc[-1]),
        'histogram': float(histogram.iloc[-1])
    }