import requests

from stock_dao import StockDAO

# Discord Webhook URL
WEBHOOK_URL = "https://discord.com/api/webhooks/1337618282630484018/ftVzKF2Y7wwZ-w09VInBDVD5euszlvS7xLvxuuhKuvc03oW9dfQUI_GQs7HgNSNfOZ7u"

def send_to_discord(response):
    """
    指定されたメッセージをDiscordのWebhookに送信する関数

    Parameters:
        message (str): 送信するメッセージ内容
    """
    payload = {
        "content": create_send_message(response)
    }
    try:
        response = requests.post(WEBHOOK_URL, json=payload)
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
    [保有期間]：{6}
    [エントリー可能理由]：{7}
        """.format(response[0], response[1], response[2], response[3],
                response[4], response[5], response[6], response[7])
    return comment

if __name__ == "__main__":
    # テスト用のサンプルメッセージを送信
    response_list = StockDAO().fetch_ok_api_response()
    for response in response_list:
        try:
            send_to_discord(response)
        except Exception as e:
            print(f"Discordへの送信に失敗しました: {e}")
            continue
