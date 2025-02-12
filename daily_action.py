import time
from lib.accsess_yFinance_for_stockPrice import fetch_batch_data_yfinance
from lib.indicator_calculator import IndicatorCalculator
from dao.stock_dao import StockDAO
from lib.table_category import TableCategory

# TODO: 最新日付のみのデータを取得するバッチ処理を実装する
# TODO:WebUIでSBI証券の取引を行う
# TODO:価格・インジ・情報で３分割し、.envでそれぞれ制御する
if __name__ == "__main__":
    try:
        dao = StockDAO()
        stock_codes = dao.fetch_company_code_list()
        total_codes = len(stock_codes)
        batch_size = 150

        print(f"[ログ] 総{total_codes}件の銘柄を、{batch_size}件ずつ処理します。")
        # 200件ずつ処理する
        for batch_start in range(0, total_codes, batch_size):
            batch_codes = stock_codes[batch_start: batch_start + batch_size]
            print(f"[ログ] {batch_start + 1}件目から{batch_start + len(batch_codes)}件目の処理を開始します...")
            
            # バッチ分まとめて株価データを１度のリクエストで取得（expairy 未指定の場合、最新1件）
            batch_data = fetch_batch_data_yfinance(batch_codes)
            if batch_data is None:
                print("バッチ全体の株価データ取得に失敗しました。")
                continue

            for stock_code, price_data in batch_data.items():
                start_time = time.time()  # 処理開始時刻を記録
                print(f"[ログ] 銘柄 {stock_code} の処理を開始します...")
                
                if not price_data:
                    print(f"株価データの取得に失敗しました: {stock_code}")
                    continue

                indi_instance = IndicatorCalculator(price_data)
                indicator = indi_instance.get_indicators()
                
                company_info = dao.fetch_company_info(stock_code)
                industry_name = TableCategory.get_table_prefix(company_info[3])  # 企業情報から業界名の取得
                
                dao.insert_indicator_data(indicator, stock_code, industry_name)
                print("end insert_indicator_data")
                
                for price in price_data:
                    dao.insert_stock_price_data(price, industry_name)
                print("end insert_stock_price_data")
                
                end_time = time.time()  # 処理終了時刻を記録
                elapsed = end_time - start_time
                print(f"[ログ] 銘柄 {stock_code} の処理時間: {elapsed:.2f} 秒")
            
            print(f"[ログ] {batch_start + 1}件目から{batch_start + len(batch_codes)}件目の処理が完了しました。")
            # 次のバッチ実行前に少し待機（例: 3秒間）
            time.sleep(3)

    except Exception as e:
        print(f"エラー発生: {e}")
    finally:
        dao.close()