## SpecStory

## Logging Configuration for File and Console Output (2025/2/13 21:31:10)

_**User**_

添付の２ファイルのLoggingの設定について、ファイル出力と同時にコンソールにも出力できる？

---

_**Assistant**_

はい、可能です。現在の実装ではファイル出力用のFileHandlerのみを追加していますが、同時にコンソール（標準出力）にもログを出力するには、StreamHandlerを追加すれば実現できます。

例えば、以下のようにsetup_logging関数内で、FileHandlerの設定後にStreamHandlerの設定を追加する方法が考えられます：

--------------------------------------------------
def setup_logging(log_type):
    today = datetime.datetime.now()
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.strftime("%d")
    log_dir = os.path.join("log", year, month)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    # ログファイル名の設定
    log_file = os.path.join(log_dir, f"{day}_stockPrice.log")  # またはエントリルールの場合は f"{day}_entryRule.log"
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # FileHandler作成
    fh = logging.FileHandler(log_file, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    # ここでStreamHandlerを追加してコンソールにも出力する
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    return logger
--------------------------------------------------

上記の例では、ログの出力はファイルおよびコンソール（標準出力）に同時に行われるようになります。必要な箇所それぞれに同様の変更を加えれば対応可能です。

---

_**User**_

実装して

---

_**Assistant**_

```diff
      fh.setFormatter(formatter)
      logger.addHandler(fh)
+     ch = logging.StreamHandler()
+     ch.setFormatter(formatter)
+     logger.addHandler(ch)
      return logger
  
```

---

_****_

```diff
          fh.setFormatter(formatter)
          logger.addHandler(fh)
+         ch = logging.StreamHandler()
+         ch.setFormatter(formatter)
+         logger.addHandler(ch)
          return logger
  
```

---

_****_

両方のファイル（confirmOfStockPrice.py と ai_entry_rule_generator.py）のsetup_logging関数に、FileHandlerの後にStreamHandlerを追加する実装を行いました。これによりログがファイルとコンソールの両方に出力されるようになります。

---

_**User**_

このエラーが出てそうな個所の特定と原因の説明
および修正の実装をして

---

_**Assistant**_

<details>
            <summary>Searched codebase "def run_stock_service(" • **10** results</summary>
        
| File | Lines |
|------|-------|
| `service/stock_service.py` | L117-120 |
| `service/stock_service.py` | L101-117 |
| `service/stock_service.py` | L32-74 |
| `service/stock_service.py` | L74-101 |
| `service/stock_service.py` | L1-32 |
| `service/ai_rule_service.py` | L26-66 |
| `service/ai_rule_service.py` | L66-102 |
| `service/ai_rule_service.py` | L1-26 |
| `service/ai_rule_service.py` | L108-112 |
| `service/ai_rule_service.py` | L102-108 |

</details>

---

_****_

<details>
            <summary>Searched codebase "def insert_stock_price_data" • **15** results</summary>
        
| File | Lines |
|------|-------|
| `dao/stock_dao.py` | L60-103 |
| `dao/stock_dao.py` | L186-219 |
| `dao/stock_dao.py` | L383-413 |
| `dao/stock_dao.py` | L123-153 |
| `dao/stock_dao.py` | L103-123 |
| `dao/stock_dao.py` | L30-60 |
| `dao/stock_dao.py` | L153-186 |
| `dao/stock_dao.py` | L256-297 |
| `dao/stock_dao.py` | L352-383 |
| `dao/stock_dao.py` | L297-352 |
| `dao/stock_dao.py` | L413-460 |
| `dao/stock_dao.py` | L219-256 |
| `dao/stock_dao.py` | L1-30 |
| `dao/stock_dao.py` | L460-481 |
| `dao/__init__.py` | L1-1 |

</details>

---

_****_

```diff
  import os
  import threading
+ import math
  
  from lib.accsess_yFinance_for_stockPrice import StockPriceAPI
```

---

_****_

```diff
              :param table_name: 挿入先のインジケーター・テーブル名（例: "retail_indicator"）
              """
-             # スキーマ変更用DDLは実行せず、テーブル {table_name} に
-             # rsi および macd カラムが既に存在する前提で処理を続行します。
+             # 安全に丸めるヘルパー関数を定義
+             def safe_round(value, ndigits):
+                 try:
+                     r = round(value, ndigits)
+                     return r if (isinstance(r, float) and __import__('math').isfinite(r)) else (r if not isinstance(r, float) else 0)
+                 except Exception:
+                     return 0
              
              query = f"""
                      "code": stock_code,
                      "date": formatted_date,
-                     "tenkan": round(record.get("ichimoku_tenkan", 0), 2),
-                     "kijun": round(record.get("ichimoku_kijun", 0), 2),
-                     "senkou_a": round(record.get("ichimoku_senkou_a", 0), 2),
-                     "senkou_b": round(record.get("ichimoku_senkou_b", 0), 2),
-                     "adx": round(record.get("adx", 0), 2),
-                     "bb_lower": round(record.get("bb_lower", 0), 2),
-                     "bb_middle": round(record.get("bb_middle", 0), 2),
-                     "bb_upper": round(record.get("bb_upper", 0), 2),
-                     "stoch_k": round(record.get("stoch_k", 0), 2),
-                     "stoch_d": round(record.get("stoch_d", 0), 2),
-                     "atr": round(record.get("atr", 0), 2),
-                     "rsi": round(record.get("rsi", 0), 2),
-                     "macd": round(record.get("macd", 0), 2),
+                     "tenkan": safe_round(record.get("ichimoku_tenkan", 0), 2),
+                     "kijun": safe_round(record.get("ichimoku_kijun", 0), 2),
+                     "senkou_a": safe_round(record.get("ichimoku_senkou_a", 0), 2),
+                     "senkou_b": safe_round(record.get("ichimoku_senkou_b", 0), 2),
+                     "adx": safe_round(record.get("adx", 0), 2),
+                     "bb_lower": safe_round(record.get("bb_lower", 0), 2),
+                     "bb_middle": safe_round(record.get("bb_middle", 0), 2),
+                     "bb_upper": safe_round(record.get("bb_upper", 0), 2),
+                     "stoch_k": safe_round(record.get("stoch_k", 0), 2),
+                     "stoch_d": safe_round(record.get("stoch_d", 0), 2),
+                     "atr": safe_round(record.get("atr", 0), 2),
+                     "rsi": safe_round(record.get("rsi", 0), 2),
+                     "macd": safe_round(record.get("macd", 0), 2),
                      "dynamic_threshold": record.get("dynamic_threshold", 0),
                      "weekly_trend": record.get("weekly_trend", "UNKNOWN"),
-                     "pca_signal": round(record.get("pca_signal", 0), 2)
+                     "pca_signal": safe_round(record.get("pca_signal", 0), 2)
                  }
  
```

---

_****_

今回のエラーは、DBに挿入する数値データ（特にインジケーターの値）のうち、無限大（infinite）の値が発生していることが原因と考えられます。  
  
【原因の詳細】  
・DBの対象カラムは numeric(10,2) の形式になっており、有限な値でなければ（または閾値を超える大きさの値でなければ）格納できません。  
・株価データの挿入時（insert_stock_price_data 関数）では、異常な値（絶対値が 10^8 以上）のチェックが行われていますが、インジケーターの挿入時（insert_indicator_data 関数）では、単純に round() を使って数値を丸めているため、何らかの理由で無限大（float('inf')）が発生すると、その値を DB に挿入しようとしてオーバーフローエラーとなります。  
  
【修正内容】  
・insert_indicator_data 関数内部に、数値を「安全に丸める」ためのヘルパー関数 safe_round を追加しました。  
・safe_round 関数では、round() の結果が有限かどうか（math.isfinite を用いて）をチェックし、もし無限大などの非有限な値であれば 0 を返すようにしています。これにより、無限大の値が DB に挿入されるのを防ぎます。  
  
上記のコード変更により、インジケーター計算結果に無限大や異常値が出た場合でも、DBの numeric(10,2) カラムに安全な値（ここでは 0）を格納するようになり、numericフィールドのオーバーフローエラーを回避できます。  

すでに dao/stock_dao.py の insert_indicator_data 内に safe_round を実装し、round() の各呼び出しを safe_round に置き換える形で修正を実施済みです。

---

_**User**_

添付ファイルのロギング部分にある問題を特定して
説明と実装をお願い

---

_**Assistant**_

```diff
                      # usageMetadataからトークン情報をログ出力する
                      usage = json_response.get("usageMetadata", {})
-                     logging.info("入力トークン(promptTokenCount):", usage.get("promptTokenCount", "不明"))
-                     logging.info("候補トークン(candidatesTokenCount):", usage.get("candidatesTokenCount", "不明"))
-                     logging.info("合計トークン(totalTokenCount):", usage.get("totalTokenCount", "不明"))
+                     logging.info("入力トークン(promptTokenCount): %s", usage.get("promptTokenCount", "不明"))
+                     logging.info("候補トークン(candidatesTokenCount): %s", usage.get("candidatesTokenCount", "不明"))
+                     logging.info("合計トークン(totalTokenCount): %s", usage.get("totalTokenCount", "不明"))
                      content = json_response['candidates'][0]['content']['parts'][0]['text']
                      json_text = self._extract_json(content)
```

---

_****_

Gemini/api_handler.py のログ出力部分に、以下のような問題があります。

【問題点の説明】  
logging.info() を呼び出すときに、メッセージ文字列と値を別々の引数として渡しています。  
たとえば、  
  logging.info("入力トークン(promptTokenCount):", usage.get("promptTokenCount", "不明"))  
とすると、logging モジュールは「入力トークン(promptTokenCount):」という固定の文字列しか出力せず、後続の値は自動でフォーマットされません。  
正しくは、メッセージ内にプレースホルダ（例えば %s）を埋め込み、対応する値を渡すか、あるいはひとつの文字列に結合して渡す必要があります。

【実装内容】  
以下のように、メッセージ文字列に '%s' プレースホルダを追加して値を渡す形式に修正しました。

  logging.info("入力トークン(promptTokenCount): %s", usage.get("promptTokenCount", "不明"))  
  logging.info("候補トークン(candidatesTokenCount): %s", usage.get("candidatesTokenCount", "不明"))  
  logging.info("合計トークン(totalTokenCount): %s", usage.get("totalTokenCount", "不明"))

これにより、ログ出力時に各値が正しく表示されるようになります。

---



---

