import time
import os
from dotenv import load_dotenv
from lib.accsess_yFinance_for_stockPrice import StockPriceAPI
from lib.indicator_calculator import IndicatorCalculator
from dao.stock_dao import StockDAO
from lib.table_category import TableCategory

def process_stock(stock_code):
    load_dotenv(override=True)
    dao = StockDAO()
    try:
        start_time = time.time()
        # StockPriceAPI を用いて最新の1件のみ取得（period="1d" として最新のデータに限定）
        stock_price_api = StockPriceAPI(stock_code)
        price_data = stock_price_api.fetch_data_yfinance()
        if not price_data:
            print(f"株価データの取得に失敗しました: {stock_code}")
            return

        indi_instance = IndicatorCalculator(price_data)
        indicator = indi_instance.get_indicators()
        
        company_info = dao.fetch_company_info(stock_code)
        if not company_info:
            print(f"企業情報取得失敗: {stock_code}")
            return
        industry_name = TableCategory.get_table_prefix(company_info[3])
        
        dao.insert_indicator_data(indicator, stock_code, industry_name)
        print("end insert_indicator_data")
        
        for price in price_data:
            dao.insert_stock_price_data(price, industry_name)
        print("end insert_stock_price_data")
        
        end_time = time.time()
        elapsed = end_time - start_time
        print(f"[ログ] 銘柄 {stock_code} の処理時間: {elapsed:.2f} 秒")
    except Exception as e:
        print(f"エラー({stock_code}): {e}")
    finally:
        dao.close()

if __name__ == "__main__":
    load_dotenv(override=True)
    dao = StockDAO()
    # すべての銘柄を取得
    stock_codes = dao.fetch_company_code_list()
    dao.close()
    print(f"[ログ] 総{len(stock_codes)}件の銘柄を処理します。")
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
         executor.map(process_stock, stock_codes)