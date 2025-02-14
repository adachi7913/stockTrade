from gradio_client import Client

# Gradio サーバーのエンドポイント URL を指定して Client を生成
client = Client("http://localhost:7788/")

# /run_with_stream API を呼び出すためのパラメータを設定して実行
result = client.predict(
    agent_type="custom",                        # エージェントタイプ。'custom' 又は 'org'
    llm_provider="openai",                        # LLM プロバイダー。例: "openai"
    llm_model_name="gpt-4o",                      # 使用するモデル名。例: "gpt-4o"
    llm_temperature=1,                            # 温度パラメータ
    llm_base_url="",                              # ベース URL（必要に応じて）
    llm_api_key="",                               # API キー（必要に応じて）
    use_own_browser=False,                        # ブラウザ利用オプション
    keep_browser_open=True,                       # ブラウザを開いたままにするかどうか
    headless=False,                               # ヘッドレスモードかどうか
    disable_security=True,                        # セキュリティ機能の無効化
    window_w=1280,                                # ブラウザウィンドウの幅
    window_h=1100,                                # ブラウザウィンドウの高さ
    save_recording_path="./tmp/record_videos",    # 録画ファイルの保存パス
    save_agent_history_path="./tmp/agent_history",# エージェント履歴の保存パス
    save_trace_path="./tmp/traces",               # トレースファイルの保存パス
    enable_recording=True,                        # 録画を有効にするかどうか
    task="go to google.com and type 'OpenAI' click search and give me the first url",  # 実行タスクの内容
    add_infos="Hello!!",                          # 補足情報。必須項目です
    max_steps=100,                                # 最大実行ステップ数
    use_vision=True,                              # ビジョン機能の使用有無
    max_actions_per_step=10,                      # 1ステップあたりの最大アクション数
    tool_call_in_content=True,                    # ツールコールをコンテンツ内で使用するかどうか
    api_name="/run_with_stream"                   # 実行する API エンドポイント
)

# API の結果を出力
print(result)