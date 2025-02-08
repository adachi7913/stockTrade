import requests

# Discord Webhook URL
WEBHOOK_URL = "https://discord.com/api/webhooks/1337618282630484018/ftVzKF2Y7wwZ-w09VInBDVD5euszlvS7xLvxuuhKuvc03oW9dfQUI_GQs7HgNSNfOZ7u"

def send_to_discord(message):
    """
    指定されたメッセージをDiscordのWebhookに送信する関数

    Parameters:
        message (str): 送信するメッセージ内容
    """
    payload = {
        "content": message
    }
    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        response.raise_for_status()  # HTTPエラーの場合は例外を発生させる
    except requests.exceptions.RequestException as e:
        print(f"Discordへの送信に失敗しました: {e}")
    else:
        print("Discordにメッセージを送信しました。")

if __name__ == "__main__":
    # テスト用のサンプルメッセージを送信
    test_message = "これはDiscordへのテストメッセージです。"
    send_to_discord(test_message)