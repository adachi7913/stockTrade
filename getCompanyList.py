from dotenv import load_dotenv
import os
import requests

# .envファイルを読み込み
load_dotenv()

# 環境変数を取得
url = os.environ.get("GAS_ENDPOINT")
print(f"URL: {url}")
funcURL = url + "?func=getJQuantsList"
print("funcURL:", funcURL)
response = requests.get(funcURL)
print("response:", response.text)
stockList = response.json()
print("stockList:", stockList)