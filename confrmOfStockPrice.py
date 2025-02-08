import json
import re
import sys
from stock_dao import StockDAO
from indicator_calculator import IndicatorCalculator
from api_handler import ApiHandler
from accsess_yFinance_for_stockPrice import StockPriceAPI
from table_category import TableCategory

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
    
def perse_response(full_data, gemini_result):
    last_record = full_data[-1]
    insert_response = {
        "date": last_record["date"],
        "code": last_record["code"],
        "close": last_record["close"],
    }
    
    if isinstance(gemini_result, dict):
        # 辞書型の場合はそのまま各項目を取得
        insert_response["isEntry"] = gemini_result.get("isEntry", "")
        insert_response["reason"] = gemini_result.get("reason", "")
        rule = gemini_result.get("rule", {})
        insert_response["rule_entry_price"] = rule.get("entryPrice", "")
        insert_response["rule_stop_limit"] = rule.get("sl", "")
        insert_response["rule_top_price"] = rule.get("tp", "")
        insert_response["rule_period"] = rule.get("period", "")
    elif isinstance(gemini_result, str):
        # 文字列の場合：先頭に「【出力形式】」があれば削除
        response_text = gemini_result.strip()
        if response_text.startswith("【出力形式】"):
            response_text = response_text.split("\n", 1)[-1]
        # コードブロック（pythonまたはjson）の内容を抽出する
        match = re.search(r"```(?:python|json)?\s*(.*?)\s*```", response_text, re.DOTALL)
        if match:
            json_text = match.group(1)
        else:
            json_text = response_text
        try:
            parsed = json.loads(json_text)
            insert_response["isEntry"] = parsed.get("isEntry", "")
            insert_response["reason"] = parsed.get("reason", "")
            rule = parsed.get("rule", {})
            insert_response["rule_entry_price"] = rule.get("entryPrice", "")
            insert_response["rule_stop_limit"] = rule.get("sl", "")
            insert_response["rule_top_price"] = rule.get("tp", "")
            insert_response["rule_period"] = rule.get("period", "")
        except Exception as e:
            print("APIレスポンスのパースに失敗しました:", e)
            # パースに失敗した場合は、そのまま生テキストをreasonとして格納する
            insert_response["isEntry"] = ""
            insert_response["reason"] = gemini_result
            insert_response["rule_entry_price"] = ""
            insert_response["rule_stop_limit"] = ""
            insert_response["rule_top_price"] = ""
            insert_response["rule_period"] = ""
    return insert_response

if __name__ == "__main__":
    try:
        dao = StockDAO()
        stock_codes = dao.fetch_company_code_list()
        # stock_codes = stock_codes[68:] # 0-68はすでに取得済み
        # stock_codes = stock_codes[216:] # 0-216はすでに取得済み
        stock_codes = stock_codes[370:] # 0-370はすでに取得済み
        # print(stock_codes)
        # stock_code = stock_codes[10]
        for stock_code in stock_codes:
            if stock_code != "27530":
                continue
            stock_price_api = StockPriceAPI(stock_code)
            price_data = stock_price_api.fetch_data_yfinance()
            if not price_data:
                print(f"株価データの取得に失敗しました: {stock_code}")
                continue
            indi_instance = IndicatorCalculator(price_data)
            indicator = indi_instance.get_indicators()
            
            company_info = dao.fetch_company_info(stock_code)
            industry_name = TableCategory.get_table_prefix(company_info[3]) # 企業名の取得
            dao.insert_indicator_data(indicator, stock_code, industry_name)
            for price in price_data:
                company_info = dao.fetch_company_info(stock_code)
                # print(company_info)
                # print(f"industry_name: {industry_name}")
                dao.insert_stock_price_data(price, industry_name)
                # print(f"株価データを挿入しました: {price}")
            full_data = dao.get_stock_full_data_period(stock_code, industry_name)
            # print(f"full_data: {full_data}")
            handler = ApiHandler(full_data)
            response = handler.call_gemini_api()
            print("response:",response)
            insert_data = perse_response(full_data, response)
            print("insert_data:", insert_data)
            dao.insert_api_response(insert_data)

    except Exception as e:
        print(f"エラー発生: {e}")
    finally:
        dao.close()

