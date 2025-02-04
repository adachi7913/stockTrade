import requests
import os
import json  # json モジュールをインポート

class ApiHandler:
    def __init__(self, data, indicators):
        self.data = data
        self.indicators = indicators

    def get_prompt(self):
        prompt = (
            "あなたはプロのデイトレーダーです。デイトレーダーとは、値動きや指標、ニュースから買い圧力と売り圧力の力量差を洗い出し、予測をたてます。"
            + "私はローリスクで着実に資産を増やしたいと考えています。"
            + "私は現在注目している株について、アドバイスを求めています。"
            + "私は、ある日本小型株の日足データと指標を持っています。"
            + "あなたには、エントリー可否判定とトレードルール**のみ**を教えてほしいです。"
            + "とある日本小型株の日足データと指標を渡しますので、エントリー可否判定とトレードルール**のみ**を、**下記の出力形式を厳守して**返答してください"
            + "【入力】  "
            + "・OHLCV日足データ  "
            + "・指標：1. 一目均衡表 パラメーター: tenkan=9, kijun=26, senkou=52)"
            +" 2. ADX (Average Directional Index) パラメーター: period=14"
            +" 3.ストキャスティクス パラメーター: %K=14, %D=3, スローイング=3"
            +" 4. ボリンジャーバンド パラメーター: length=20, std=2"
            +" 5. ATR (Average True Range) パラメーター: period=14"
            + "【出力形式】"
            + "  [エントリー可否]**可能/不可**"
            + "  [理由]**ここに理由を出力**"
            + "  [ルール]（可の場合）  "
            + "・Entry価格帯  "
            + "・SL価格  "
            + "・利確目標  "
            + "・推奨保有期間  "
            + "【OHLCV日足データ】"
            + json.dumps(self.data, ensure_ascii=False)  # json.dumps() を使用、ensure_ascii=False で日本語を正しく表示
            + "【指標】"
            + json.dumps(self.indicators, ensure_ascii=False)  # json.dumps() を使用、ensure_ascii=False で日本語を正しく表示
        )
        return prompt

    def call_gemini_api(self):
        # Gemini APIを呼び出して予測結果を取得します
        print("call_gemini_api() started")
        print("Calling Gemini API")
        api_key = os.environ.get("GEMINI_API_KEY")  # 環境変数からAPIキーを取得
        if not api_key:
            print("Error: GEMINI_API_KEY environment variable not set.")
            return "API key not set"  # APIキーがない場合はエラーメッセージを返す

        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-thinking-exp:generateContent?key={api_key}"
        prompt = self.getPrompt() # getPrompt関数でプロンプトを生成
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
            # Gemini APIからのレスポンスを処理します
            if json_response and 'candidates' in json_response and json_response['candidates']:
                return json_response['candidates'][0].get('content', "No content found")
            else:
                return "No prediction found or invalid API response" # レスポンスが不正な場合のエラーメッセージを追加
        except requests.RequestException as e:
            print(f"Gemini API call failed: {e}, request: {e.request}, response: {e.response}")
            return f"Gemini API call failed: {e}"