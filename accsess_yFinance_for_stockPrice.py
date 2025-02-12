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
                raise ValueError(
                    f"No data retrieved for code {yf_code} from yfinance API."
                )

            data = []
            # DataFrame から必要なデータを抽出してリストに格納
            for index, row in df.iterrows():
                data.append(
                    {
                        "code": self.code,
                        "date": index.strftime("%Y%m%d"),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row["Volume"]),
                    }
                )
            return data
        except Exception as e:
            print(f"Error fetching data for {self.code} from yfinance API: {e}")
            return None




def _remove_trailing_zero(code):
    # 株式コードの末尾のゼロが存在する場合に削除します
    return code[:-1] if code.endswith("0") else code


if __name__ == "__main__":
    stock_code = "2753"
    stock_price_api = StockPriceAPI(stock_code)
    price_data = stock_price_api.fetch_data_yfinance()
    print(price_data)
