import sys
from stock_dao import StockDAO
from indicator_calculator import IndicatorCalculator
from api_handler import ApiHandler
from accsess_yFinance_for_stockPrice import StockPriceAPI

def analyze_stocks():
    try:
        # 株価コード一覧取得
        stock_codes = StockDAO.fetch_company_code_list()

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

                    analysis = ApiHandler.call_gemini_api(prompt)
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
    try:
        dao = StockDAO()
        stock_codes = dao.fetch_company_code_list()
        print(stock_codes)
        stock_code = stock_codes[0]
        stock_price_api = StockPriceAPI(stock_code)
        price_data = stock_price_api.fetch_data_yfinance()
        print(price_data)
        for price in price_data:
            dao.insert_stock_price_data(price)
    except Exception as e:
        print(f"エラー発生: {e}")
    finally:
        dao.close()

