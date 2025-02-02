import psycopg
from dotenv import load_dotenv
import os
import sys

# コンソール出力のエンコーディングを設定
sys.stdout.reconfigure(encoding='utf-8')

# .envファイルを読み込み
load_dotenv()

# 接続情報を設定
host = os.environ.get("DB_HOST")
database = os.environ.get("DB_NAME")
user = os.environ.get("DB_USER")
password = os.environ.get("DB_PASSWORD")

try:
    # PostgreSQLに接続（client_encodingを指定）
    conn = psycopg.connect(
        host=host,
        user=user,
        password=password,
        dbname=database,
        client_encoding='utf8'
    )
    cur = conn.cursor()

    # SQLクエリを実行 (例: テーブルを作成)
    cur.execute("CREATE TABLE IF NOT EXISTS my_table (id SERIAL PRIMARY KEY, name VARCHAR(255))")

    # SQLクエリを実行 (例: データを挿入)
    cur.execute("INSERT INTO my_table (name) VALUES ('John Doe')")

    # 変更をコミット
    conn.commit()

    # SQLクエリを実行 (例: データを取得)
    cur.execute("SELECT * FROM my_table")
    rows = cur.fetchall()

    # 結果を表示
    for row in rows:
        print(row)

    # カーソルと接続を閉じる
    cur.close()
    conn.close()

except psycopg.Error as e:
    print("PostgreSQL error:", e)