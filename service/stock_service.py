import time
from datetime import date, timedelta
from dao.stock_dao import StockDAO
from lib.accsess_yFinance_for_stockPrice import StockPriceAPI
from lib.indicator_calculator import IndicatorCalculator
from lib.table_category import TableCategory

def run_stock_service():
    dao = StockDAO()
    try:
        start_time = time.time()
        stock_codes = dao.fetch_company_code_list()
        print("stock_codes:", stock_codes)
        for stock_code in stock_codes:
            stock_start_time = time.time()
            price_api = StockPriceAPI(stock_code)
            price_data = price_api.fetch_data_yfinance()
            if not price_data:
                print(f"株価データの取得に失敗しました: {stock_code}")
                continue
            # インジケーター計算
            indicator_calculator = IndicatorCalculator(price_data)
            indicator = indicator_calculator.get_indicators()

            company_info = dao.fetch_company_info(stock_code)
            # 企業情報から業種テーブルのプレフィックスを取得
            industry_name = TableCategory.get_table_prefix(company_info[3])
            dao.insert_indicator_data(indicator, stock_code, industry_name)

            for price in price_data:
                dao.insert_stock_price_data(price, industry_name)

            full_data = dao.get_stock_full_data_period(stock_code, industry_name)
            stock_elapsed = time.time() - stock_start_time
            print(f"[ログ] 銘柄 {stock_code} の処理時間: {stock_elapsed:.2f} 秒")

        total_elapsed = time.time() - start_time
        print(f"[ログ] 全体の処理時間: {total_elapsed:.2f} 秒")
    except Exception as e:
        print(f"エラー発生: {e}")
    finally:
        dao.close()

if __name__ == "__main__":
    run_stock_service() 