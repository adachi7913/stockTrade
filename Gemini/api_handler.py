import requests
import os
import json  # json モジュールをインポート
import re
from decimal import Decimal

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

        data_converted = convert_decimals(self.data)
        
        prompt = f"""
【前提】英語で思考し、**日本語のみ**で回答してください。
    【内容】
    あなたは優秀な個人投資家であり、短期スウィングトレードに精通しています。
    市場動向、各種インジケーター、そして株価の推移をもとに、エントリーの可否と最適なトレード戦略を構築してください。
    エントリー可否の判断は、以下のルールに従ってください:
    ・エントリー可否は、**可能/不可**のいずれかで回答してください。
    ・リスクリワードが2.0以上の場合のみエントリー可能とします。
    ・エントリーはロングのみとします
    ・作成したトレードルールを自己採点し、**Scoreを0 ~ 100で算出**してください。
    ・エントリー不可の場合、Scoreは0とします。

    今回は、DBから取得した最大過去５年間分の株価データと各インジケーター（以下がそのデータ構造）を提供します。
    各レコードは、次の構成になっています:

    　{{
    　　　"code": 株式コード,
    　　　"date": "YYYYMMDD形式の日付",
    　　　"open": 始値,
    　　　"high": 高値,
    　　　"low": 安値,
    　　　"close": 終値,
    　　　"volume": 出来高,
    　　　"ichimoku": {{
    　　　　"tenkan": 転換線,
    　　　　"kijun": 基準線,
    　　　　"senkou_a": 先行スパンA,
    　　　　"senkou_b": 先行スパンB
    　　　}},
    　　　"adx": ADX,
    　　　"bb": {{
    　　　　"lower": ボリンジャーバンド下限,
    　　　　"middle": ボリンジャーバンド中央値,
    　　　　"upper": ボリンジャーバンド上限
    　　　}},
    　　　"stoch": {{
    　　　　"stoch_k": ストキャスティクス%K,
    　　　　"stoch_d": ストキャスティクス%D
    　　　}},
    　　　"atr": ATR
    　}}


    【提供データ】
    {json.dumps(data_converted, ensure_ascii=False)}
    出力形式は下記です。**JSONの形式を厳守**し、その他の内容は回答に含めないでください。:
    【出力形式】
    {{isEntry:**"可能" / "不可"**, reason:**"理由"**, rule:{{entryPrice:**"Entry価格帯"** / "NG", sl:**"SL価格"** / "NG", tp:**"利確目標"** / "NG", period:**"推奨保有期間"** / "NG", riskReward:**"リスクリワード"** / "NG"}}, score:**"0 ~ 100"**}}
    """
        return prompt

    def call_gemini_api(self):
        # Gemini APIを呼び出して予測結果を取得します
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

        try:
            response = requests.post(api_url, json=payload, headers=headers)
            response.raise_for_status()
            json_response = response.json()
            # print("API response:", json_response)
            
            # Gemini APIからのレスポンスを処理します
            # if json_response and 'candidates' in json_response and json_response['candidates']:
            #     content = json_response['candidates'][0]['content']['parts']['text']
            try:
                # usageMetadataからトークン情報をログ出力する
                usage = json_response.get("usageMetadata", {})
                print("入力トークン(promptTokenCount):", usage.get("promptTokenCount", "不明"))
                print("候補トークン(candidatesTokenCount):", usage.get("candidatesTokenCount", "不明"))
                print("合計トークン(totalTokenCount):", usage.get("totalTokenCount", "不明"))
                content = json_response['candidates'][0]['content']['parts'][0]['text']
                # マークダウン記法の ```json ... ``` を削除する
                if isinstance(content, dict):
                    content = json.dumps(content, ensure_ascii=False)
                match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    json_text = match.group(1)
                else:
                    json_text = content
                    
                return json_text
            except Exception as e:
                print("JSON parse error:", e)
                return {"error": "JSON parse error", "raw": json_response['candidates'][0]['content']}
            # else:
            #     return {"error": "No prediction found or invalid API response"}
        except requests.RequestException as e:
            print(f"Gemini API call failed: {e}, request: {e.request}, response: {e.response}")
            return f"Gemini API call failed: {e}"
    
    