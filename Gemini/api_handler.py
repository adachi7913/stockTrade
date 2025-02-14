import requests
import os
import json  # json モジュールをインポート
import re
from decimal import Decimal
import time  # リトライ用に追加
import logging

class ApiHandler:
    def __init__(self, data):
        self.data = data

    def get_prompt(self):
        # Decimal 型の値を float に変換するヘルパー関数
        def convert_decimals(obj):
            if isinstance(obj, dict):
                return {k: convert_decimals(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_decimals(item) for item in obj]
            elif isinstance(obj, Decimal):
                return float(obj)
            return obj

        # 最新データ(full_data)から最終レコードを抽出
        latest_record = self.data[-1]
        # convert_decimals関数を使用して終値を整形（convert_decimalsは消さないでください）
        entry_close = convert_decimals(latest_record["close"])
        
        prompt = f"""
        【前提】
        英語で思考し、**日本語のみ**で回答してください。
        あなたは優秀な個人投資家かつトレード戦略構築のエキスパートです。過去のデータや各種テクニカル指標をもとに、エントリー判断を段階的フィルタリングで実施し、その結果に基づいてエントリーの信頼性を1000点満点で評価してください。

        【エントリー判断の評価基準】
        1. リスクリワード比が2.0以上の場合のみ有望と判断（基礎点300点）
        2. 各指標の整合性評価（最大400点）：
           - トレンド分析（一目均衡表、MACD）：100点
           - モメンタム（RSI、ストキャスティクス）：100点
           - ボラティリティ（ボリンジャーバンド、ATR）：100点
           - 出来高分析：100点
        3. バックテスト結果の反映（最大300点）：
           - 勝率と期待値：100点
           - ドローダウン：100点
           - 一貫性：100点

        【エントリー価格の設定】
        エントリー価格は、最新の終値（{entry_close} 円）付近に設定してください。大幅な乖離がある場合は、必ず最新の終値に近い価格に調整してください。

        【データ品質チェック】
        - 各指標の欠損や異常値をチェック
        - データ不備がある場合は、該当指標を明記し、スコアを減点

        【提供データ】
        {json.dumps(convert_decimals(self.data), ensure_ascii=False)}

        【タスク】
        1. 提供データを元に段階的フィルタリングを実施
        2. 各評価基準に基づいてスコアリング
        3. バックテストによる検証
        4. データ品質の確認と反映

        【出力形式】（以下のJSON形式を厳守し、その他の内容は含めないでください）
        {{
            "entry_score": <0〜1000の整数>,
            "reason": "エントリー判断の理由及び各段階での点数根拠",
            "rule": {{
                "entryPrice": "エントリー価格（金額のみ）" or "NG",
                "sl": "ストップロス価格" or "NG",
                "tp": "利確目標" or "NG",
                "period": "推奨保有期間（例：3日～5日）" or "NG",
                "riskReward": "リスクリワード比（計算結果）" or "NG"
            }},
            "no_entry_span": <再判断までの日数（整数）>
        }}
        """
        return prompt


    def _extract_json(self, content):
        """
        Gemini API のレスポンス中、マークダウンの ```json ... ``` 形式で囲まれている場合、
        その中身のみを抽出するヘルパー関数
        """
        match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            return match.group(1)
        return content

    def call_gemini_api(self):
        print("call_gemini_api() started")
        print("Calling Gemini API")
        api_key = os.environ.get("GEMINI_API_KEY")  # 環境変数からAPIキーを取得
        if not api_key:
            print("Error: GEMINI_API_KEY environment variable not set.")
            return "API key not set"  # APIキーがない場合はエラーメッセージを返す
        model = os.environ.get("GEMINI_MODEL")  # 環境変数からモデル名を取得
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        prompt = self.get_prompt() # getPrompt関数でプロンプトを生成
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt} # 生成したプロンプトをpayloadに設定
                    ]
                }
            ]
        }
        headers = {'Content-Type': 'application/json'}

        max_retries = 3  # 最大リトライ回数
        attempt = 0
        while attempt < max_retries:
            try:
                response = requests.post(api_url, json=payload, headers=headers)
                # 503の場合はリトライ
                if response.status_code == 503:
                    attempt += 1
                    print(f"Gemini API returned 503. Retrying {attempt}/{max_retries} after 5 seconds...")
                    time.sleep(5)
                    continue
                response.raise_for_status()
                json_response = response.json()
                # print("API response:", json_response)
                
                # Gemini APIからのレスポンスを処理します
                # if json_response and 'candidates' in json_response and json_response['candidates']:
                #     content = json_response['candidates'][0]['content']['parts']['text']
                try:
                    # usageMetadataからトークン情報をログ出力する
                    usage = json_response.get("usageMetadata", {})
                    logging.info("入力トークン(promptTokenCount): %s", usage.get("promptTokenCount", "不明"))
                    logging.info("候補トークン(candidatesTokenCount): %s", usage.get("candidatesTokenCount", "不明"))
                    logging.info("合計トークン(totalTokenCount): %s", usage.get("totalTokenCount", "不明"))
                    content = json_response['candidates'][0]['content']['parts'][0]['text']
                    json_text = self._extract_json(content)
                    return json_text
                except Exception as e:
                    print("JSON parse error:", e)
                    return {"error": "JSON parse error", "raw": json_response.get('candidates', [{}])[0].get('content')}
                # else:
                #     return {"error": "No prediction found or invalid API response"}
            except requests.RequestException as e:
                if e.response is not None and e.response.status_code == 503:
                    attempt += 1
                    print(f"RequestException with 503 received. Retrying {attempt}/{max_retries} after 5 seconds...")
                    time.sleep(5)
                    continue
                else:
                    print(f"Gemini API call failed: {e}, request: {e.request}, response: {e.response}")
                    return f"Gemini API call failed: {e}"
        return {"error": "Failed after multiple retries due to 503 response."}
    
    