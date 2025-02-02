import os
import requests
from dotenv import load_dotenv
import json
from dbAccsessTest import create_companies_table, insert_company_data
import psycopg

class JQuantsAPI:
    def __init__(self):
        load_dotenv()
        self.email = os.environ.get("EMAIL")
        self.password = os.environ.get("PASSWORD")
        self.base_url = "https://api.jquants.com/v1"
        self.refresh_token = None
        self.id_token = None

    def get_refresh_token(self):
        """リフレッシュトークンを取得"""
        url = f"{self.base_url}/token/auth_user"
        payload = {
            "mailaddress": self.email,
            "password": self.password
        }
        
        try:
            response = requests.post(
                url, 
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            print(f"auth_user ステータスコード: {response.status_code}")
            
            if response.status_code != 200:
                print(f"auth_user 取得失敗: {response.status_code} - {response.text}")
                return None

            auth_json = response.json()
            self.refresh_token = auth_json.get("refreshToken")
            # トークンを環境変数に保存
            os.environ["REFRESH_TOKEN"] = self.refresh_token
            return self.refresh_token

        except requests.exceptions.RequestException as e:
            print(f"auth_user エラー: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"auth_user JSONパースエラー: {e}")
            return None

    def get_id_token(self):
        """IDトークンを取得"""
        if not self.refresh_token:
            self.refresh_token = os.environ.get("REFRESH_TOKEN")
            if not self.refresh_token:
                self.refresh_token = self.get_refresh_token()

        if not self.refresh_token:
            print("リフレッシュトークンの取得に失敗しました")
            return None

        # クエリパラメータとしてリフレッシュトークンを追加
        url = f"{self.base_url}/token/auth_refresh?refreshtoken={self.refresh_token}"
        
        try:
            response = requests.post(url)
            print(f"auth_refresh ステータスコード: {response.status_code}")

            if response.status_code != 200:
                print(f"auth_refresh 取得失敗: {response.status_code} - {response.text}")
                # リフレッシュトークンが無効な場合は再取得
                if response.status_code == 400:
                    self.refresh_token = self.get_refresh_token()
                    if self.refresh_token:
                        return self.get_id_token()  # 再帰的に呼び出し
                return None

            refresh_json = response.json()
            self.id_token = refresh_json.get("idToken")
            os.environ["ID_TOKEN"] = self.id_token
            return self.id_token

        except requests.exceptions.RequestException as e:
            print(f"auth_refresh エラー: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"auth_refresh JSONパースエラー: {e}")
            return None

    def get_listed_info(self):
        """上場企業情報を取得"""
        if not self.id_token:
            self.id_token = self.get_id_token()
            
        if not self.id_token:
            return None
            
        url = f"{self.base_url}/listed/info"
        headers = {"Authorization": f"Bearer {self.id_token}"}
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Listed info error: {e}")
            return None

def get_company_list():
    try:
        # DB接続情報
        load_dotenv()
        host = os.environ.get("DB_HOST")
        database = os.environ.get("DB_NAME")
        user = os.environ.get("DB_USER")
        password = os.environ.get("DB_PASSWORD")

        # J-Quants APIからデータ取得
        api = JQuantsAPI()
        company_list = api.get_listed_info()
        
        if not company_list:
            print("企業データの取得に失敗しました")
            return None

        # DB接続とデータ挿入
        with psycopg.connect(
            host=host,
            dbname=database,
            user=user,
            password=password
        ) as conn:
            with conn.cursor() as cur:
                # テーブル作成
                create_companies_table(cur)
                
                # データ挿入
                for company in company_list.get('info', []):
                    insert_company_data(cur, company)
                
                conn.commit()
                print("データベースへの挿入が完了しました")

        return company_list

    except Exception as e:
        print(f"エラー発生: {e}")
        return None

if __name__ == "__main__":
    result = get_company_list()
    if result:
        print("処理が正常に完了しました")