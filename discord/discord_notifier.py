import requests

from repository.stock_repository import StockRepository
from util.date_util import get_current_datetime

# Discord Webhook URLs
ERROR_URL = "https://discord.com/api/webhooks/1338074017449381918/KjUzGGg7-NF1YtxCuW_kw8uBK50OkOVHP-BMhiVFi-n3JhaBZJnhepn_7Ec0wQcSjomm"
WEBHOOK_URL = "https://discord.com/api/webhooks/1337618282630484018/ftVzKF2Y7wwZ-w09VInBDVD5euszlvS7xLvxuuhKuvc03oW9dfQUI_GQs7HgNSNfOZ7u"

def send_to_discord(url, message):
    """
    指定されたメッセージをDiscordのWebhookに送信する関数

    Parameters:
        message (str): 送信するメッセージ内容
    """
    payload = {
        "content": message
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()  # HTTPエラーの場合は例外を発生させる
    except requests.exceptions.RequestException as e:
        print(f"Discordへの送信に失敗しました: {e}")
    else:
        print("Discordにメッセージを送信しました。")

def create_send_message(response):
    """
    送信するメッセージを生成する関数
    """
    comment = """
    [分析日]：{0}
    [銘柄コード]：{1}
    [終値]：{2}
    [エントリー価格]：{3}
    [損切り価格]：{4}
    [利益確定価格]：{5}
    [想定損益割合]：{6}
    [自己採点スコア]：{7}
    [保有期間]：{6}
    [エントリー可能理由]：{7}
    """.format(response[0], response[1], response[2], response[3],
               response[4], response[5], response[6], response[7])
    return comment

def create_error_message(message):
    """
    送信するエラーメッセージを生成する関数
    """
    comment = """
    [エラー発生日]：{0}
    [エラー内容]：{1}
    """.format(get_current_datetime(), message)
    send_to_discord(ERROR_URL, comment)

if __name__ == "__main__":
    # テスト用サンプル（必要に応じて）
    send_to_discord(WEBHOOK_URL, "テストメッセージ")
