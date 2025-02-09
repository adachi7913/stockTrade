import os
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

class StockPriceAPI:
    def __init__(self, code, expairy=None):
        """
        コンストラクタ
        
        Parameters:
            code (str): 株式コード。末尾のゼロは自動的に削除します。
            expairy (int, optional): 取得期間としての年数。指定された場合は、今日から expairy 年前までのデータを取得します。
                                      指定しない場合は、最新の1件のみのデータを取得します。
        """
        self.code = _remove_trailing_zero(code)
        self.expairy = expairy


    def fetch_data_yfinance(self):
        """
        yfinance API を使用して株価データを取得するメソッド。
        
        - expairy が指定されている場合、今日から expairy 年前までのデータを取得します。
        - expairy が指定されていない場合、最新の1件のみを取得します。

        Returns:
            list: 日ごとの株価データのリスト（dict 型のリスト）。取得に失敗した場合は None を返します。
        """
        try:
            today = datetime.now()
            yf_code = self.code + ".T"
            ticker = yf.Ticker(yf_code)

            if self.expairy is not None:
                # 指定された年数分のデータを取得
                start_date = today - timedelta(days=int(self.expairy) * 365)
                df = ticker.history(start=start_date, end=today)
            else:
                # expairy が指定されていない場合は、最新の取引日の全レコードを取得した後、
                # 最新の1件のみを抽出する
                df = ticker.history(period="1d")
                if not df.empty:
                    df = df.iloc[[-1]]  # 最新の1件に絞る

            df.fillna(0, inplace=True)
            if df.empty:
                raise ValueError(f"No data retrieved for code {yf_code} from yfinance API.")

            data = []
            # DataFrame から必要なデータを抽出してリストに格納
            for index, row in df.iterrows():
                data.append({
                    "code": self.code,
                    "date": index.strftime('%Y%m%d'),
                    "open": float(row['Open']),
                    "high": float(row['High']),
                    "low": float(row['Low']),
                    "close": float(row['Close']),
                    "volume": int(row['Volume'])
                })
            return data
        except Exception as e:
            print(f"Error fetching data for {self.code} from yfinance API: {e}")
            return None

def fetch_batch_data_yfinance(stock_codes, expairy=None):
    """
    複数の銘柄コードを一度のリクエストでyfinanceから取得する関数。

    Parameters:
        stock_codes (list): 銘柄コードのリスト（例: ['2753', '7203', ...]）
        expairy (int, optional): 取得期間としての年数。指定された場合は、今日から expairy 年前までのデータを取得します。
                                 指定しない場合は、最新の1件のみを取得します。

    Returns:
        dict: 各銘柄コードをキー、取得した株価データのリスト（辞書のリスト）を値とする辞書。
              データが取得できなかった銘柄は結果に含まれません。
    """
    try:
        
        today = datetime.now()
        if expairy is not None:
            start_date = today - timedelta(days=int(expairy) * 365)
        # 銘柄コードに対して ".T" を付加
        ticker_symbols = [_remove_trailing_zero(code) for code in stock_codes]
        ticker_symbols = [code + ".T" for code in stock_codes]
        tickers_str = " ".join(ticker_symbols)
        tickers = yf.Tickers(tickers_str)

        if expairy is not None:
            df = tickers.history(start=start_date, end=today)
        else:
            df = tickers.history(period="1d")
        df.fillna(0, inplace=True)
        if df.empty:
            raise ValueError("No data retrieved for tickers")

        results = {}
        # 取得結果は複数ティッカーの場合、MultiIndex のカラムとなるため、
        # 各ティッカーごとに DataFrame を抽出して処理します
        if isinstance(df.columns, pd.MultiIndex):
            for ticker in ticker_symbols:
                # データが存在しない場合はスキップ
                if ticker not in df.columns.get_level_values(0):
                    continue
                ticker_df = df[ticker]
                records = []
                if expairy is None:
                    # 最新1件のみ取得
                    record = ticker_df.iloc[-1]
                    date_str = record.name.strftime('%Y%m%d')
                    record_dict = {
                        "code": ticker.replace(".T", ""),
                        "date": date_str,
                        "open": float(record["Open"]),
                        "high": float(record["High"]),
                        "low": float(record["Low"]),
                        "close": float(record["Close"]),
                        "volume": int(record["Volume"])
                    }
                    records.append(record_dict)
                else:
                    for index, row in ticker_df.iterrows():
                        date_str = index.strftime('%Y%m%d')
                        record_dict = {
                            "code": ticker.replace(".T", ""),
                            "date": date_str,
                            "open": float(row["Open"]),
                            "high": float(row["High"]),
                            "low": float(row["Low"]),
                            "close": float(row["Close"]),
                            "volume": int(row["Volume"])
                        }
                        records.append(record_dict)
                results[ticker.replace(".T", "")] = records
        else:
            # 単一ティッカーの場合
            ticker = ticker_symbols[0]
            records = []
            if expairy is None:
                record = df.iloc[-1]
                date_str = record.name.strftime('%Y%m%d')
                record_dict = {
                    "code": ticker.replace(".T", ""),
                    "date": date_str,
                    "open": float(record["Open"]),
                    "high": float(record["High"]),
                    "low": float(record["Low"]),
                    "close": float(record["Close"]),
                    "volume": int(record["Volume"])
                }
                records.append(record_dict)
            else:
                for index, row in df.iterrows():
                    date_str = index.strftime('%Y%m%d')
                    record_dict = {
                        "code": ticker.replace(".T", ""),
                        "date": date_str,
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row["Volume"])
                    }
                    records.append(record_dict)
            results[ticker.replace(".T", "")] = records

        return results

    except Exception as e:
        print("Error fetching batch data for tickers:", e)
        return None

def _remove_trailing_zero(code):
    # 株式コードの末尾のゼロが存在する場合に削除します
    return code[:-1] if code.endswith("0") else code

if __name__ == "__main__":
    stock_code = "2753"
    stock_price_api = StockPriceAPI(stock_code)
    price_data = stock_price_api.fetch_data_yfinance()
    print(price_data)
