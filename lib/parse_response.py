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
        'no_entry_span': int,
        'position': str  # ★ positionフィールドの検証を追加
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
        # 範囲外の場合は自動的に修正する
        if no_entry_span > 14:
            log.warning(f"no_entry_span が14を超えています。14に制限します: {no_entry_span} -> 14")
            data['no_entry_span'] = 14
        elif no_entry_span < 1:
            log.warning(f"no_entry_span が1未満です。1に制限します: {no_entry_span} -> 1")
            data['no_entry_span'] = 1
        else:
            return False
    
    # ★ positionの値が 'long', 'short', 'hold' のいずれかであることを検証
    position = data.get('position', 'hold') # デフォルトは hold
    if position not in ['long', 'short', 'hold']:
        log.error(f"Invalid position value: {position}. Must be 'long', 'short', or 'hold'. Defaulting to 'hold'.")
        data['position'] = 'hold' # 不正な値の場合は hold に設定
    
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
        if isinstance(response, str):
            # まずJSONブロックを抽出
            json_text = extract_json_from_text(response, logger=log)
            
            # デバッグ用にJSON文字列の状態を出力
            log.debug(f"パース前のJSON文字列の型: {type(json_text)}")
            log.debug(f"パース前のJSON文字列の長さ: {len(json_text)}")
            
            try:
                # 文字列の前後の空白を除去してからパース
                json_text = json_text.strip()
                response_data = json.loads(json_text)
            except json.JSONDecodeError as e:
                log.error(f"JSONデコードエラー: {e}")
                log.error(f"対象テキスト: {json_text[:200]}...")  # 最初の200文字だけログ出力
                
                # エラーの詳細な位置情報を出力
                error_pos = e.pos
                context_start = max(0, error_pos - 20)
                context_end = min(len(json_text), error_pos + 20)
                error_context = json_text[context_start:context_end]
                log.error(f"エラー位置周辺のテキスト: {error_context}")
                log.error(f"エラー位置: {error_pos}")
                
                return None
        else:
            response_data = response
            
        if not isinstance(response_data, dict):
            log.error(f"レスポンスが辞書型ではありません: {type(response_data)}")
            return None
        
        entry_score = response_data.get("entry_score", 0)
        reason = response_data.get("reason", "")
        rule = response_data.get("rule", {})
        position = response_data.get("position", "hold") # ★ positionフィールドを取得 (デフォルトは hold)
        
        # 数値型の場合は文字列に変換する処理を追加
        if isinstance(rule, str):
            # rule が文字列の場合（"NG"など）は空の辞書として扱う
            rule_entry_price = "NG"
            rule_stop_limit = "NG"
            rule_top_price = "NG"
            rule_period = "NG"
            risk_reward = "NG"
        else:
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
            "date": datetime.now().strftime('%Y-%m-%d'),
            "code": stock_code,
            "close": full_data[-1]["close"] if full_data and len(full_data) > 0 and "close" in full_data[-1] else 0,
            "rule_entry_price": rule_entry_price,
            "rule_stop_limit": rule_stop_limit,
            "rule_top_price": rule_top_price,
            "rule_period": rule_period,
            "risk_reward": risk_reward,
            "no_entry_span": min(14, max(1, response_data.get("no_entry_span", 0))),  # 1～14の範囲に制限
            "entry_score": safe_int(entry_score),
            "expected_return": expected_return,
            "reason": reason,
            "update_when": datetime.now(),  # 現在日時を追加
            "position": position,  # ★ positionを追加
            # 新しいフィールドを追加
            "entry_conditions": str(response_data.get('entry_conditions', '')), # リストの場合も文字列化
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

def extract_json_from_text(text, logger=None):
    """テキストからJSON部分を抽出し、エスケープシーケンスを適切に処理"""
    log = logger if logger else logging.getLogger()
    
    try:
        # 入力テキストの前処理
        text = text.strip()
        
        # BOMがある場合は除去
        if text.startswith('\ufeff'):
            text = text[1:]
        
        # コードブロック内のJSONを探す
        code_block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if code_block_match:
            json_text = code_block_match.group(1)
            log.info("コードブロックからJSONを抽出しました")
        else:
            # 単純な{}で囲まれた部分を探す
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
                log.info("{}で囲まれた部分からJSONを抽出しました")
            else:
                json_text = text
                log.info("テキスト全体をJSONとして扱います")
        
        # JSONテキストの正規化
        json_text = json_text.strip()
        
        # 無効なエスケープシーケンスを修正
        json_text = re.sub(r'\\([^"\\/bfnrtu])', r'\1', json_text)
        
        # 配列内の末尾カンマを削除
        json_text = re.sub(r',\s*]', ']', json_text)
        
        # 文字列内のエスケープされていないダブルクォートをエスケープ（新規追加）
        # 正規表現で文字列を探し、その中のエスケープされていないダブルクォートをエスケープする
        def escape_quotes_in_strings(match):
            # 文字列全体を取得
            content = match.group(0)
            # 文字列内のエスケープされていないダブルクォートをエスケープ
            # ただし、既にエスケープされているものは除外
            content = re.sub(r'(?<!\\)"(?![:,}\]])', r'\"', content)
            return content
        
        # 文字列を検索してエスケープ処理
        json_text = re.sub(r':"[^"]*"', escape_quotes_in_strings, json_text)
        
        # インデントと改行を正規化
        json_text = re.sub(r'[\n\r\t ]+', ' ', json_text)
        
        # 不要なスペースを削除（ただし文字列内のスペースは保持）
        json_text = re.sub(r'\s*,\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', ',', json_text)
        json_text = re.sub(r'\s*:\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', ':', json_text)
        json_text = re.sub(r'\s*\{\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', '{', json_text)
        json_text = re.sub(r'\s*\}\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', '}', json_text)
        
        # プロパティ名をダブルクォートで囲む
        json_text = re.sub(r'([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', json_text)
        
        # 正規化したJSONをパースしてみる
        try:
            json.loads(json_text)
            log.info("JSONの構文チェックに成功しました")
        except json.JSONDecodeError as e:
            log.error(f"JSONの構文チェックに失敗: {e}")
            error_pos = e.pos
            context_start = max(0, error_pos - 20)
            context_end = min(len(json_text), error_pos + 20)
            log.error(f"エラー位置周辺のテキスト: {json_text[context_start:context_end]}")
            
            # エラー修復を試みる
            try:
                # 問題のある文字列をより詳細に分析して修正
                log.info("JSONエラー修復を試みます")
                if "," in json_text[error_pos-5:error_pos+5]:
                    # カンマが原因と思われる場合
                    json_text = json_text[:error_pos] + json_text[error_pos+1:]
                    log.info("問題のあるカンマを削除しました")
                
                # ダブルクォートの問題の場合（新規追加）
                elif '"' in json_text[error_pos-5:error_pos+5]:
                    # 問題のある位置の前後10文字を取得してログ出力
                    problem_area = json_text[max(0, error_pos-10):min(len(json_text), error_pos+10)]
                    log.info(f"ダブルクォート周辺の問題領域: {problem_area}")
                    
                    # 問題の可能性があるエスケープされていないダブルクォートを全てエスケープ
                    json_text = json_text[:error_pos-10] + re.sub(r'(?<!\\)"', r'\"', json_text[error_pos-10:error_pos+10]) + json_text[error_pos+10:]
                    log.info("問題のあるダブルクォートをエスケープしました")
                
                # 修復したJSONを再度パース
                json.loads(json_text)
                log.info("JSON修復に成功しました")
            except Exception as repair_error:
                log.error(f"JSON修復に失敗しました: {repair_error}")
            
        return json_text
        
    except Exception as e:
        log.error(f"JSON抽出中にエラー: {e}")
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