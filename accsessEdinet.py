import os
import requests


class EdinetHandler:
    def getEdinetData():
        api_key = os.environ.get("EDINET_API_KEY")  # 環境変数からAPIキーを取得
        # EDINET API URL
        api_url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"

        params = {
            "date": "2025-01-20",  # 2021年9月1日のデータを取得
            "type": 2,  # 定時報告書など
            "Subscription-Key": api_key,
        }

        response = requests.get(api_url, params=params)

        data = response.text
        print(data)
