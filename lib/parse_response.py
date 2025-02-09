import json
import re


def parse_response(full_data, gemini_result):
    """
    Gemini API のレスポンス（gemini_result）と株価データ（full_data）のリストから、
    DB挿入用の株価エントリールール情報を抽出します。

    出力の辞書フォーマット:
      {
        "date": 日付,
        "code": 株式コード,
        "close": 終値,
        "isEntry": "可能" または "不可",
        "reason": 理由,
        "rule_entry_price": Entry価格帯 または "NG",
        "rule_stop_limit": SL価格 または "NG",
        "rule_top_price": 利確目標 または "NG",
        "rule_period": 推奨保有期間 または "NG",
        "riskReward": リスクリワード（テキスト） または "NG",
        "score": スコア（整数; 0 〜 100）,
        "no_entry_span": 再評価までの期間（数値）
      }

    ※ full_data が空の場合は処理をスキップして None を返します。
    """
    if not full_data:
        print("株価データが空のため、処理をスキップします。")
        return None
    last_record = full_data[-1]
    insert_response = {
        "date": last_record["date"],
        "code": last_record["code"],
        "close": last_record["close"],
    }

    # score を安全に整数変換するヘルパー
    def safe_int(int_value):
        try:
            return int(int_value)
        except (ValueError, TypeError):
            return 0

    if isinstance(gemini_result, dict):
        # 辞書型の場合はそのまま各項目を取得
        insert_response["isEntry"] = gemini_result.get("isEntry", "")
        insert_response["reason"] = gemini_result.get("reason", "")
        rule = gemini_result.get("rule", {})
        insert_response["rule_entry_price"] = rule.get("entryPrice", "")
        insert_response["rule_stop_limit"] = rule.get("sl", "")
        insert_response["rule_top_price"] = rule.get("tp", "")
        insert_response["rule_period"] = rule.get("period", "")
        insert_response["riskReward"] = rule.get("riskReward", "")
        score_raw = gemini_result.get("score", "0")
        insert_response["score"] = safe_int(score_raw)
        no_entry_raw = gemini_result.get("no_entry_span", "0")
        insert_response["no_entry_span"] = safe_int(no_entry_raw)
    elif isinstance(gemini_result, str):
        # 文字列の場合：先頭に「【出力形式】」があれば削除
        response_text = gemini_result.strip()
        if response_text.startswith("【出力形式】"):
            response_text = response_text.split("\n", 1)[-1]
        # コードブロック（pythonまたはjson）の内容を抽出する
        match = re.search(
            r"```(?:python|json)?\s*(.*?)\s*```", response_text, re.DOTALL
        )
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
            insert_response["riskReward"] = rule.get("riskReward", "")
            score_raw = parsed.get("score", "0")
            insert_response["score"] = safe_int(score_raw)
            no_entry_raw = parsed.get("no_entry_span", "0")
            insert_response["no_entry_span"] = safe_int(no_entry_raw)
        except Exception as e:
            print("APIレスポンスのパースに失敗しました:", e)
            # パースに失敗した場合は、そのまま生テキストをreasonとして格納する
            insert_response["isEntry"] = ""
            insert_response["reason"] = gemini_result
            insert_response["rule_entry_price"] = ""
            insert_response["rule_stop_limit"] = ""
            insert_response["rule_top_price"] = ""
            insert_response["rule_period"] = ""
            insert_response["riskReward"] = ""
            insert_response["score"] = 0
            insert_response["no_entry_span"] = 0
    return insert_response