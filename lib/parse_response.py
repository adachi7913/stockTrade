import json
import re
import logging
from datetime import datetime
from decimal import Decimal

def validate_date_format(date_str):
    """日付形式の検証"""
    try:
        if len(date_str) == 8:  # YYYYMMDD形式
            datetime.strptime(date_str, '%Y%m%d')
            return True
        elif len(date_str) == 10:  # YYYY-MM-DD形式
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        return False
    except ValueError:
        return False

def convert_decimal_to_float(value):
    """Decimal型の値をfloatに変換"""
    if isinstance(value, Decimal):
        return float(value)
    return value

def validate_response_data(data):
    """レスポンスデータの検証"""
    required_fields = {
        'date': str,
        'code': str,
        'close': (int, float, Decimal),  # Decimalも許容
        'entry_score': (int, float),  # isEntryとscoreを統合
        'reason': str,
        'rule_entry_price': str,
        'rule_stop_limit': str,
        'rule_top_price': str,
        'rule_period': str,
        'riskReward': str,
        'no_entry_span': int
    }
    
    for field, expected_type in required_fields.items():
        if field not in data:
            logging.error(f"Missing required field: {field}")
            return False
        
        value = data[field]
        if not isinstance(value, expected_type):
            if field == 'close' and isinstance(value, Decimal):
                data[field] = float(value)  # Decimalをfloatに変換
            elif field == 'entry_score' and isinstance(value, str):
                try:
                    data[field] = int(float(value))  # 文字列の場合は数値に変換
                except ValueError:
                    logging.error(f"Invalid entry_score value: {value}")
                    return False
            else:
                logging.error(f"Invalid type for {field}: expected {expected_type}, got {type(value)}")
                return False
    
    # 日付フォーマットの検証
    if not validate_date_format(data['date']):
        logging.error(f"Invalid date format: {data['date']}")
        return False
    
    # entry_scoreの範囲検証
    if not (0 <= data['entry_score'] <= 1000):
        logging.error(f"entry_score out of range: {data['entry_score']}")
        return False
    
    # no_entry_spanの範囲検証
    if not (1 <= data['no_entry_span'] <= 14):
        logging.error(f"no_entry_span out of range: {data['no_entry_span']}")
        return False
    
    return True

def parse_response(full_data, gemini_result):
    """
    Gemini API のレスポンスと株価データのリストから、
    DB挿入用の株価エントリールール情報を抽出します。
    """
    if not full_data:
        logging.error("株価データが空のため、処理をスキップします。")
        return None

    try:
        last_record = full_data[-1]
        insert_response = {
            "date": last_record["date"],
            "code": last_record["code"],
            "close": convert_decimal_to_float(last_record["close"]),
            "entry_score": 0,
            "reason": "",
            "rule_entry_price": "",
            "rule_stop_limit": "",
            "rule_top_price": "",
            "rule_period": "",
            "riskReward": "",
            "no_entry_span": 0
        }

        # gemini_resultの型に応じた処理
        if isinstance(gemini_result, dict):
            parsed_data = gemini_result
        elif isinstance(gemini_result, str):
            json_text = extract_json_from_text(gemini_result)
            try:
                parsed_data = json.loads(json_text)
            except json.JSONDecodeError as e:
                logging.error(f"JSON parse error: {e}")
                insert_response["reason"] = "APIレスポンスのパースに失敗しました"
                return insert_response
        else:
            logging.error(f"Unexpected gemini_result type: {type(gemini_result)}")
            insert_response["reason"] = "不正なAPIレスポンス形式"
            return insert_response

        # パースしたデータを挿入用レスポンスに設定
        try:
            insert_response["entry_score"] = int(parsed_data.get("entry_score", 0))
            insert_response["reason"] = parsed_data.get("reason", "")
            rule = parsed_data.get("rule", {})
            insert_response["rule_entry_price"] = rule.get("entryPrice", "")
            insert_response["rule_stop_limit"] = rule.get("sl", "")
            insert_response["rule_top_price"] = rule.get("tp", "")
            insert_response["rule_period"] = rule.get("period", "")
            insert_response["riskReward"] = rule.get("riskReward", "")
            insert_response["no_entry_span"] = safe_int(parsed_data.get("no_entry_span", "0"))
        except Exception as e:
            logging.error(f"Error setting response values: {e}")
            insert_response["reason"] = "レスポンスデータの設定に失敗しました"
            return insert_response

        # データの検証
        if not validate_response_data(insert_response):
            logging.error("Response data validation failed")
            insert_response["reason"] = "レスポンスデータの検証に失敗しました"
            return insert_response

        return insert_response

    except Exception as e:
        logging.error(f"Unexpected error in parse_response: {e}")
        return None

def extract_json_from_text(text):
    """テキストからJSON部分を抽出"""
    # コードブロック内のJSONを探す
    code_block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if code_block_match:
        return code_block_match.group(1)
    
    # 単純な{}で囲まれた部分を探す
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        return json_match.group(0)
    
    return text

def safe_int(value):
    """安全に整数に変換"""
    try:
        if isinstance(value, (int, float)):
            return int(value)
        elif isinstance(value, str):
            return int(float(value))
        return 0
    except (ValueError, TypeError):
        return 0