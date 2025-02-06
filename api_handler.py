import requests
import os
import json  # json モジュールをインポート

class ApiHandler:
    def __init__(self, full_data):
        self.full_data = full_data

    def get_prompt(self):
        prompt = f"""
    あなたは優秀な個人投資家であり、短期スウィングトレードに精通しています。
    市場動向、各種インジケーター、そして株価の推移をもとに、エントリーの可否と最適なトレード戦略を構築してください。
    私は低リスクで着実に資産を増やす投資戦略を志向しています。

    今回は、DBから取得した過去1年間分の株価データと各インジケーターを統合した情報を提供します。
    各レコードは、以下の構成になっています：

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
    {json.dumps(self.full_data, ensure_ascii=False)}

    【出力形式】
    [エントリー可否] **可能/不可**
    [理由] **ここに理由を記述**
    [ルール] （エントリー可能な場合）
    　・Entry価格帯
    　・SL価格
    　・利確目標
    　・推奨保有期間
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