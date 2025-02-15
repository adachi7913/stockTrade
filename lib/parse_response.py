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
        'rule_entry_price': (str, int, float),  # 数値型も許容
        'rule_stop_limit': (str, int, float),   # 数値型も許容
        'rule_top_price': (str, int, float),    # 数値型も許容
        'rule_period': str,
        'riskReward': (str, int, float),        # 数値型も許容
        'no_entry_span': int
    }
    
    for field, expected_type in required_fields.items():
        if field not in data:
            logging.error(f"Missing required field: {field}")
            return False
        
        value = data[field]
        if not isinstance(value, expected_type):
            try:
                if field in ['rule_entry_price', 'rule_stop_limit', 'rule_top_price', 'riskReward']:
                    # 数値型の場合は文字列に変換
                    if isinstance(value, (int, float, Decimal)):
                        data[field] = str(value)
                    else:
                        logging.error(f"Invalid type for {field}: expected {expected_type}, got {type(value)}")
                        return False
                elif field == 'close' and isinstance(value, Decimal):
                    data[field] = float(value)  # Decimalをfloatに変換
                elif field == 'entry_score' and isinstance(value, str):
                    data[field] = int(float(value))  # 文字列の場合は数値に変換
                else:
                    logging.error(f"Invalid type for {field}: expected {expected_type}, got {type(value)}")
                    return False
            except (ValueError, TypeError) as e:
                logging.error(f"Value conversion error for {field}: {e}")
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

def parse_response(full_data, response):
    """
    AIからのレスポンスと株価データ（full_data）をもとに,
    DB挿入用のデータを返却する関数。
    """
    try:
        # レスポンスが文字列の場合はJSONに変換
        response_data = json.loads(response) if isinstance(response, str) else response
        
        entry_score = response_data.get("entry_score", 0)
        reason = response_data.get("reason", "")
        rule = response_data.get("rule", {})
        
        # 数値型の場合は文字列に変換する処理を追加
        rule_entry_price = str(rule.get("entryPrice", "NG"))
        rule_stop_limit = str(rule.get("sl", "NG"))
        rule_top_price = str(rule.get("tp", "NG"))
        rule_period = str(rule.get("period", "NG"))
        risk_reward = str(rule.get("riskReward", "NG"))
        
        # 想定リターンの計算（利確目標 - エントリー価格）
        try:
            if rule_entry_price != "NG" and rule_top_price != "NG":
                # 範囲指定の場合は中央値を使用
                entry_price = float(rule_entry_price.split("-")[0])  # 範囲指定の場合は最小値を使用
                top_price = float(rule_top_price.split("-")[0])     # 範囲指定の場合は最小値を使用
                expected_return = round(top_price - entry_price, 2)  # 小数点2桁で丸める
            else:
                expected_return = None  # NGの代わりにNULLを使用
        except Exception as e:
            logging.error(f"Expected return calculation error: {e}")
            expected_return = None

        insert_data = {
            "date": full_data[-1]["date"],
            "code": full_data[-1]["code"],
            "close": full_data[-1]["close"],
            "rule_entry_price": rule_entry_price,
            "rule_stop_limit": rule_stop_limit,
            "rule_top_price": rule_top_price,
            "rule_period": rule_period,
            "riskReward": risk_reward,
            "no_entry_span": response_data.get("no_entry_span", 0),
            "entry_score": entry_score,
            "expected_return": expected_return,
            "reason": reason
        }
        
        # データの検証
        if validate_response_data(insert_data):
            return insert_data
        return None
        
    except Exception as e:
        logging.error(f"パースエラー: {e}")
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