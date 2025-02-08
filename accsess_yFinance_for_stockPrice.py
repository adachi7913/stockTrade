import os
import yfinance as yf
from datetime import datetime, timedelta

class StockPriceAPI:
    def __init__(self, code):
        self.code = self._remove_trailing_zero(code)  # 株式コードの末尾のゼロを削除します

    def _remove_trailing_zero(self, code):
        # 株式コードの末尾のゼロを削除します（存在する場合）
        return code[:-1] if code.endswith("0") else code
    def fetch_data_yfinance(self):
        # yfinance APIを使用して株価データを取得します
        try:
            today = datetime.now()
            fetch_data_range = today - timedelta(days=os.environ.get("FETCH_DATA_RANGE", 1) * 365)
            # test26days_ago = today - timedelta(days=43)
            
            # yfinanceで日本株のコードには".T"をつける必要があります
            yf_code = self.code + ".T"
            
            # print(f"Fetching data for {yf_code} from yfinance API")
            
            # 期間を指定して株価データを取得
            ticker = yf.Ticker(yf_code)
            df = ticker.history(start=fetch_data_range, end=today)
            # df = ticker.history(start=test26days_ago, end=today)

            # df.sort_index(inplace=True) # 日付でソート
            # print(f"df.index.is_monotonic_increasing: {df.index.is_monotonic_increasing}") # インデックスが日付順にソートされているか確認
            df.fillna(0, inplace=True) # 欠損値を0で埋める
            if df.empty:
                raise ValueError(f"No data retrieved for code {yf_code} from yfinance API.")

            data = []
            # DataFrameから必要なデータを抽出してリストに格納
            for index, row in df.iterrows():
                data.append({
                    "code": self.code,
                    "date": index.strftime('%Y%m%d'), # 日付の形式をDD-MM-YYYYに変換
                    "open": (float(row['Open'])),
                    "high": (float(row['High'])),
                    "low": (float(row['Low'])),
                    "close": (float(row['Close'])),
                    "volume": int(row['Volume'])
                })                
        # print(f"Successfully fetched {len(data)} days of data from yfinance API.")
            return data
        except Exception as e:
            print(f"Error fetching data for {self.code} from yfinance API: {e}")
            return None

if __name__ == "__main__":
    stock_code = "2753"
    stock_price_api = StockPriceAPI(stock_code)
    price_data = stock_price_api.fetch_data_yfinance()
    print(price_data)
