import requests
import os
import json  # json モジュールをインポート
import re
from decimal import Decimal

class ApiHandler:
    def __init__(self, data):
        self.data = data

    def get_prompt(self):
        # Convert Decimal values in self.data to float
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
        [Premise] Think in English and answer in Japanese.
        [Content]
        You are a skilled individual investor with expertise in short-term swing trading.
        Based on market trends, various indicators, and stock price movements, please decide whether to enter a position and devise an optimal trading strategy.
        My investment strategy focuses on steadily increasing assets with low risk.
            
        In this case, I will provide the stock price data from the past year along with various indicators (the data structure is as follows).
        Each record is structured as:

        {{
            "code": Stock code,
            "date": "Date in YYYYMMDD format",
            "open": Opening price,
            "high": High price,
            "low": Low price,
            "close": Closing price,
            "volume": Volume,
            "ichimoku": {{
                "tenkan": Tenkan-sen,
                "kijun": Kijun-sen,
                "senkou_a": Senkou Span A,
                "senkou_b": Senkou Span B
            }},
            "adx": ADX,
            "bb": {{
                "lower": Bollinger Band Lower,
                "middle": Bollinger Band Middle,
                "upper": Bollinger Band Upper
            }},
            "stoch": {{
                "stoch_k": Stochastic %K,
                "stoch_d": Stochastic %D
            }},
            "atr": ATR
        }}

        [Provided Data]
        {json.dumps(data_converted, ensure_ascii=False)}
        The output format is as follows. Please adhere strictly to a Python dictionary format and include nothing else in your answer:
        [Output Format]
        {{isEntry:**OK/Not Possible**, reason:**Reason**, rule:{{entryPrice:**Entry Price Range**, sl:**Stop Loss Price**, tp:**Take Profit Target**, period:**Recommended Holding Period**}}}}
        
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
            print("API response:", json_response)
            
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