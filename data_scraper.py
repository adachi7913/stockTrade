import yfinance as yf
from datetime import datetime, timedelta

class StockScraper:
    def __init__(self, code, fetch_only_flg=False):
        self.code = self._remove_trailing_zero(code)  # 株式コードの末尾のゼロを削除します
        self.fetch_only_flg = fetch_only_flg

    def _remove_trailing_zero(self, code):
        # 株式コードの末尾のゼロを削除します（存在する場合）
        return code[:-1] if code.endswith("0") else code

    def fetch_data_yfinance(self):
        # yfinance APIを使用して株価データを取得します
        today = datetime.now()
        one_year_ago = today - timedelta(days=365)
        test26days_ago = today - timedelta(days=43)
        
        # yfinanceで日本株のコードには".T"をつける必要があります
        yf_code = self.code + ".T" 
        
        print(f"Fetching data for {yf_code} from yfinance API")
        
        # 期間を指定して株価データを取得
        ticker = yf.Ticker(yf_code)
        df = ticker.history(start=one_year_ago, end=today)
        # df = ticker.history(start=test26days_ago, end=today)

        # df.sort_index(inplace=True) # 日付でソート
        print(f"df.index.is_monotonic_increasing: {df.index.is_monotonic_increasing}") # インデックスが日付順にソートされているか確認
        df.fillna(0, inplace=True) # 欠損値を0で埋める
        if df.empty:
            raise ValueError(f"No data retrieved for code {yf_code} from yfinance API.")

        data = []
        # DataFrameから必要なデータを抽出してリストに格納
        for index, row in df.iterrows():
            data.append({
                "date": index.strftime('%d-%m-%Y'), # 日付の形式をDD-MM-YYYYに変換
                "open": (float(row['Open'])),
                "high": (float(row['High'])),
                "low": (float(row['Low'])),
                "close": (float(row['Close'])),
                "volume": int(row['Volume'])
            })
        print(f"Successfully fetched {len(data)} days of data from yfinance API.")
        # data.reverse() # リストを反転
        return data
