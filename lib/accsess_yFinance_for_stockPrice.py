import os
import sys
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

from dao.stock_dao import StockDAO



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

            # --- DB更新用の処理（時価総額を companies テーブルに反映） ---
            ticker_info = ticker.info
            market_cap = ticker_info.get("marketCap")
            if market_cap is not None:
                stock_dao = StockDAO()
                stock_dao.update_market_cap(self.code, market_cap)

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

    def fetch_batch_data_yfinance(stock_codes, expairy=None):
        try:
            today = datetime.now()
            if expairy is not None:
                start_date = today - timedelta(days=int(expairy) * 365)
            ticker_symbols = [code + ".T" for code in stock_codes]
            tickers_str = " ".join(ticker_symbols)
            tickers = yf.Tickers(ticker_symbols)

            if expairy is not None:
                df = tickers.history(start=start_date, end=today)
            else:
                df = tickers.history(period="1d")
            df.fillna(0, inplace=True)
            if df.empty:
                print("一部もしくは全ティッカーでデータが取得できませんでした。")
                return {}

            # 以下、各ティッカーごとにレコードを抽出する処理
            # ※個別にエラーになったティッカーは結果に含めないようにする
            results = {}
            if isinstance(df.columns, pd.MultiIndex):
                for ticker in ticker_symbols:
                    if ticker not in df.columns.get_level_values(0):
                        print(f"{ticker} のデータは取得できませんでした。")
                        continue
                    ticker_df = df[ticker]
                    records = []
                    if expairy is None:
                        try:
                            record = ticker_df.iloc[-1]
                            date_str = record.name.strftime("%Y%m%d")
                            record_dict = {
                                "code": ticker.replace(".T", ""),
                                "date": date_str,
                                "open": float(record["Open"]),
                                "high": float(record["High"]),
                                "low": float(record["Low"]),
                                "close": float(record["Close"]),
                                "volume": int(record["Volume"]),
                            }
                            records.append(record_dict)
                        except Exception as e:
                            print(f"{ticker} の最新データ抽出でエラー: {e}")
                            continue
                    else:
                        for index, row in ticker_df.iterrows():
                            date_str = index.strftime("%Y%m%d")
                            record_dict = {
                                "code": ticker.replace(".T", ""),
                                "date": date_str,
                                "open": float(row["Open"]),
                                "high": float(row["High"]),
                                "low": float(row["Low"]),
                                "close": float(row["Close"]),
                                "volume": int(row["Volume"]),
                            }
                            records.append(record_dict)
                    results[ticker.replace(".T", "")] = records
            else:
                # 単一ティッカーの場合の処理
                ticker = ticker_symbols[0]
                records = []
                if expairy is None:
                    record = df.iloc[-1]
                    date_str = record.name.strftime("%Y%m%d")
                    record_dict = {
                        "code": ticker.replace(".T", ""),
                        "date": date_str,
                        "open": float(record["Open"]),
                        "high": float(record["High"]),
                        "low": float(record["Low"]),
                        "close": float(record["Close"]),
                        "volume": int(record["Volume"]),
                    }
                    records.append(record_dict)
                else:
                    for index, row in df.iterrows():
                        date_str = index.strftime("%Y%m%d")
                        record_dict = {
                            "code": ticker.replace(".T", ""),
                            "date": date_str,
                            "open": float(row["Open"]),
                            "high": float(row["High"]),
                            "low": float(row["Low"]),
                            "close": float(row["Close"]),
                            "volume": int(row["Volume"]),
                        }
                        records.append(record_dict)
                results[ticker.replace(".T", "")] = records
            return results
        except Exception as e:
            print("Error fetching batch data for tickers:", e)
            return {}


def _remove_trailing_zero(code):
    # 株式コードの末尾のゼロが存在する場合に削除します
    return code[:-1] if code.endswith("0") else code


if __name__ == "__main__":
    stock_dao = StockDAO()
    stock_dao.update_market_cap("1301", 1000000000)
    print("OK")
