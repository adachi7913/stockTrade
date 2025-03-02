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

def validate_response_data(data, logger=None):
    """レスポンスデータの検証"""
    # ロガーの設定
    log = logger if logger else logging.getLogger()
    
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
        'risk_reward': (str, int, float),        # 数値型も許容
        'no_entry_span': int
    }
    
    # オプションフィールドの定義
    optional_fields = {
        'entry_conditions': str,
        'exit_conditions': str,
        'short_term_trend': str,
        'mid_term_trend': str,
        'long_term_trend': str,
        'support_resistance': str,
        'technical_patterns': str,
        'indicator_analysis': str
    }
    
    # 必須フィールドのチェック
    for field, expected_type in required_fields.items():
        if field not in data:
            log.error(f"Missing required field: {field}")
            return False
        
        value = data[field]
        if not isinstance(value, expected_type):
            try:
                if field in ['rule_entry_price', 'rule_stop_limit', 'rule_top_price', 'risk_reward']:
                    # ルールのNG値や範囲値は文字列として許容
                    if isinstance(value, str) and (value == "NG" or "-" in value):
                        continue
                    # 数値型の場合は文字列に変換して許容
                    if isinstance(value, (int, float)) and str(value):
                        continue
                # 数値型へ変換可能な文字列は許容（例: "100"）
                if field in ['close', 'entry_score', 'no_entry_span'] and isinstance(value, str) and value.isdigit():
                    continue
                log.error(f"Field {field} has unexpected type. Expected {expected_type}, got {type(value)}")
                return False
            except Exception as e:
                log.error(f"Error processing field {field}: {e}")
                return False
    
    # オプションフィールドのチェック（存在する場合のみ型チェック）
    for field, expected_type in optional_fields.items():
        if field in data and data[field] is not None:
            value = data[field]
            if not isinstance(value, expected_type):
                try:
                    # 空の値の場合は許容
                    if value == "" or value is None:
                        continue
                        
                    # リスト型を文字列として処理
                    if isinstance(value, list) and expected_type == str:
                        log.info(f"リスト型のフィールド {field} を文字列に変換します")
                        data[field] = "\n".join([f"- {item}" for item in value]) if value else ""
                        continue
                        
                    log.warning(f"Optional field {field} has unexpected type. Expected {expected_type}, got {type(value)}")
                    # オプションフィールドなので、型不一致でもエラーではなく警告に留める
                    data[field] = str(value)  # 強制的に文字列型に変換
                except Exception as e:
                    log.warning(f"Error processing optional field {field}: {e}")
                    data[field] = ""  # エラー時は空文字を設定
    
    # 日付のフォーマット検証
    if not validate_date_format(data['date']):
        log.error(f"Invalid date format: {data['date']}")
        return False
    
    # エントリースコアの範囲検証（0〜1000）
    entry_score = data['entry_score']
    if not (0 <= entry_score <= 1000):
        log.error(f"entry_score out of range: {entry_score}")
        return False
    
    # エントリー期間の再判断日数（1〜14日）
    no_entry_span = data['no_entry_span']
    if not (1 <= no_entry_span <= 14):
        log.error(f"no_entry_span out of range: {data['no_entry_span']}")
        return False
    
    return True

def parse_response(full_data, response, code=None, logger=None):
    """
    AIからのレスポンスと株価データ（full_data）をもとに,
    DB挿入用のデータを返却する関数。
    
    Args:
        full_data (list): 株価データのリスト
        response (str/dict): AI APIからのレスポンス
        code (str, optional): 銘柄コード。指定されない場合はfull_dataから取得を試みる
        logger (logging.Logger, optional): ロガーオブジェクト
        
    Returns:
        dict or None: DB挿入用のデータ、解析失敗時はNone
    """
    # ロガーの設定
    log = logger if logger else logging.getLogger()
    
    try:
        # レスポンスが文字列の場合はJSONに変換
        response_data = json.loads(response) if isinstance(response, str) else response
        
        entry_score = response_data.get("entry_score", 0)
        reason = response_data.get("reason", "")
        rule = response_data.get("rule", {})
        
        # 数値型の場合は文字列に変換する処理を追加
        rule_entry_price = str(rule.get("entryPrice", "NG"))
        rule_stop_limit = str(rule.get("stop_loss", rule.get("sl", "NG")))  # stop_lossとslの両方に対応
        rule_top_price = str(rule.get("target_price", rule.get("tp", "NG")))  # target_priceとtpの両方に対応
        rule_period = str(rule.get("period", "NG"))
        risk_reward = str(rule.get("risk_reward", rule.get("riskReward", "NG")))  # risk_rewardとriskRewardの両方に対応
        
        # 新しいフィールドの取得
        entry_conditions = response_data.get("entry_conditions", "")
        exit_conditions = response_data.get("exit_conditions", "")
        
        # リスト型の場合は改行区切りの文字列に変換
        if isinstance(entry_conditions, list):
            entry_conditions = "\n".join([f"- {item}" for item in entry_conditions])
        
        if isinstance(exit_conditions, list):
            exit_conditions = "\n".join([f"- {item}" for item in exit_conditions])
        
        # 市場分析情報の取得
        market_analysis = response_data.get("market_analysis", {})
        if not isinstance(market_analysis, dict):
            log.warning(f"market_analysis is not a dictionary: {type(market_analysis)}")
            market_analysis = {}
            
        short_term_trend = market_analysis.get("short_term_trend", "") if isinstance(market_analysis, dict) else ""
        mid_term_trend = market_analysis.get("mid_term_trend", "") if isinstance(market_analysis, dict) else ""
        long_term_trend = market_analysis.get("long_term_trend", "") if isinstance(market_analysis, dict) else ""
        support_resistance = market_analysis.get("support_resistance", "") if isinstance(market_analysis, dict) else ""
        
        # support_resistanceがリスト型の場合は文字列に変換
        if isinstance(support_resistance, list):
            support_resistance = "\n".join([f"- {item}" for item in support_resistance])
        
        # テクニカルパターンとインジケーター分析
        technical_patterns = response_data.get("technical_patterns", "")
        indicator_analysis = response_data.get("indicator_analysis", "")
        
        # リスト型の場合は改行区切りの文字列に変換
        if isinstance(technical_patterns, list):
            technical_patterns = "\n".join([f"- {item}" for item in technical_patterns])
            
        if isinstance(indicator_analysis, list):
            indicator_analysis = "\n".join([f"- {item}" for item in indicator_analysis])
        
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
            log.error(f"Expected return calculation error: {e}")
            expected_return = None
            
        # コードの取得（引数で指定されていれば優先、そうでなければfull_dataから取得を試みる）
        stock_code = code
        if stock_code is None and full_data and len(full_data) > 0 and "code" in full_data[-1]:
            stock_code = full_data[-1]["code"]
        
        if stock_code is None:
            log.error("銘柄コードが見つかりません")
            return None

        insert_data = {
            "date": full_data[-1]["date"] if full_data and len(full_data) > 0 else datetime.now().strftime('%Y%m%d'),
            "code": stock_code,
            "close": full_data[-1]["close"] if full_data and len(full_data) > 0 and "close" in full_data[-1] else 0,
            "rule_entry_price": rule_entry_price,
            "rule_stop_limit": rule_stop_limit,
            "rule_top_price": rule_top_price,
            "rule_period": rule_period,
            "risk_reward": risk_reward,
            "no_entry_span": response_data.get("no_entry_span", 0),
            "entry_score": entry_score,
            "expected_return": expected_return,
            "reason": reason,
            # 新しいフィールドを追加
            "entry_conditions": entry_conditions,
            "exit_conditions": exit_conditions,
            "short_term_trend": short_term_trend,
            "mid_term_trend": mid_term_trend,
            "long_term_trend": long_term_trend,
            "support_resistance": support_resistance,
            "technical_patterns": technical_patterns,
            "indicator_analysis": indicator_analysis
        }
        
        # データの検証
        if validate_response_data(insert_data, logger=log):
            return insert_data
        return None
        
    except Exception as e:
        log.error(f"パースエラー: {e}")
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