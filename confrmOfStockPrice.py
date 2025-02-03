import sys
from stockDAO import fetch_company_code_list
from indicator_calculator import IndicatorCalculator
from api_handler import call_gemini_api
from getStockPriceFromYFinance import StockPriceAPI

def analyze_stocks():
    try:
        # 株価コード一覧取得
        stock_codes = fetch_company_code_list()

        # 各銘柄の分析
        for code in stock_codes:
            try:
                stock_price_api = StockPriceAPI(code)
                # 株価データ取得
                price_data = stock_price_api.fetch_data_yfinance()

                if price_data:
                    # インジケーター計算
                    calculator = IndicatorCalculator(price_data)
                    indicators = calculator.get_indicators()

                    # Geminiによる分析
                    prompt = f"""
                        銘柄コード: {code}
                        株価データ: {price_data}
                        テクニカル指標: {indicators}
                        
                        上記データから投資判断をお願いします。
                        """

                    analysis = call_gemini_api(prompt)
                    print(f"銘柄 {code} の分析結果:")
                    print(analysis)
                    print("-" * 50)

            except Exception as e:
                print(f"銘柄 {code} の処理中にエラー: {e}")
                continue

    except Exception as e:
        print(f"実行エラー: {e}")
        return None


if __name__ == "__main__":
    analyze_stocks()
