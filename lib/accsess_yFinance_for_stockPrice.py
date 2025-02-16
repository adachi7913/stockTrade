import os
import sys
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import logging
from repository.stock_repository import StockRepository


class StockPriceAPI:
    def __init__(self, code, expairy=None):
        """
        コンストラクタ

        Parameters:
            code (str): 株式コード。末尾のゼロは自動的に削除します。
            expairy (int or str, optional): 取得期間としての年数。指定された場合は、今日から expairy 年前までのデータを取得します。
                指定しない場合は、最新の1件のみのデータを取得します。
                .envから取得した場合、空文字の場合は None として扱います。
        """
        self.code = _remove_trailing_zero(code)
        # .env で空文字の場合は None として扱う
        self.expairy = expairy if expairy not in (None, "") else None

    def fetch_data_yfinance(self):
        """
        yfinance API を使用して株価データを取得するメソッド。

        - expairy が指定されている場合、今日から expairy 日前までのデータを取得します。
        - expairy が指定されていない場合、最新の1件のみを取得します。

        Returns:
            list: 日ごとの株価データのリスト（dict 型のリスト）。取得に失敗した場合は None を返します。
        """
        try:
            today = datetime.now()
            yf_code = self.code + ".T"
            ticker = yf.Ticker(yf_code)
            ticker_info = ticker.info
            market_cap = ticker_info.get("marketCap")
            if market_cap is not None:
                stock_dao = StockRepository()
                stock_dao.update_market_cap(self.code, market_cap)
                stock_dao.close()

            if self.expairy is not None:
                # confirmOfStockPrice用：指定された日数分のデータを取得
                start_date = today - timedelta(days=int(self.expairy))
                df = ticker.history(start=start_date, end=today)
            else:
                # daily_update用：5日分のデータを取得
                df = ticker.history(period="5d")

            if df.empty:
                raise ValueError(f"No valid data for code {yf_code}")

            data = []
            for index, row in df.iterrows():
                # 出来高のバリデーション
                vol = row["Volume"]
                if pd.isna(vol) or vol == 0:
                    # logging.warning(f"Invalid volume data detected for {yf_code} on {index}")
                    continue
                
                # 価格データのバリデーション
                price_cols = ["Open", "High", "Low", "Close"]
                if any(pd.isna(row[col]) or row[col] <= 0 for col in price_cols):
                    logging.warning(f"Invalid price data detected for {yf_code} on {index}")
                    continue
                
                # 値の整合性チェック
                if not (row["Low"] <= row["Open"] <= row["High"] and 
                       row["Low"] <= row["Close"] <= row["High"]):
                    logging.warning(f"Inconsistent OHLC data for {yf_code} on {index}")
                    continue

                data.append({
                    "code": self.code,
                    "date": index.strftime("%Y%m%d"),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(vol),
                })

            if not data:
                raise ValueError(f"No valid records after validation for {yf_code}")
                
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
            tickers = yf.Tickers(ticker_symbols)

            if expairy is not None:
                df = tickers.history(start=start_date, end=today)
            else:
                df = tickers.history(period="1d")
            df.fillna(0, inplace=True)
            if df.empty:
                print("一部もしくは全ティッカーでデータが取得できませんでした。")
                return {}

            results = {}
            # 単一ティッカーの場合、またはMultiIndexでない場合は別処理
            if len(ticker_symbols) == 1 or not isinstance(df.columns, pd.MultiIndex):
                ticker = ticker_symbols[0]
                records = []
                if expairy is None:
                    try:
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
                    except Exception as e:
                        print(f"{ticker} の最新データ抽出でエラー: {e}")
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
            else:
                # 複数ティッカーの場合の処理
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
            return results
        except Exception as e:
            print("Error fetching batch data for tickers:", e)
            return {}


def _remove_trailing_zero(code):
    # 株式コードの末尾のゼロが存在する場合に削除します
    return code[:-1] if code.endswith("0") else code


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


# if __name__ == "__main__":
#     stock_dao = StockRepository()
#     stock_dao.update_market_cap("1301", 1000000000)
#     print("OK")
