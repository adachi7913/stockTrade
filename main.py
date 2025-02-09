import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'pandas-ta'))

import requests


if __name__ == "__main__":
    # from accsessEdinet import EdinetHandler  # edinet_handler.py から EdinetHandler をインポート
    # EdinetHandler.getEdinetData()
    import os
    from lib.accsess_yFinance_for_stockPrice import (
        StockScraper,
    )  # data_scraper.py から StooqScraper をインポート
    from lib.indicator_calculator import (
        IndicatorCalculator,
    )  # indicator_calculator.py から IndicatorCalculator をインポート
    from Gemini.api_handler import ApiHandler  # api_handler.py から ApiHandler をインポート

# メイン処理: データ取得とAPI連携を実行します

url = os.environ.get("GAS_ENDPOINT")
funcURL = url + "?func=getStockNumberList"
print("funcURL:", funcURL)
response = requests.get(funcURL)
stockList = response.json()
print("stockList:", stockList)

scraper = StockScraper("7205")  # StockScraperのインスタンスを作成
stock_data = scraper.fetch_data_yfinance()  # 株価データを取得
# print("Stock data:", stock_data)
indicator_calculator = IndicatorCalculator(
    stock_data
)  # IndicatorCalculatorのインスタンスを作成
indicators = indicator_calculator.get_indicators()  # 指標を計算
print("Indicators:", indicators, end="\n\n")
api_handler = ApiHandler(stock_data, indicators)  # ApiHandlerのインスタンスを作成
gemini_result = api_handler.call_gemini_api()  # Gemini APIを呼び出す
print("Result from Gemini API:", gemini_result)
