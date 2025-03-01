#!/usr/bin/env python
import os
import sys
import time

# 終了直前に1秒間待機することで、APIシャットダウンの完了を待つ
def main():
    print("auto_sell_stock.pyをテストモードで実行します...")
    os.system("python auto_sell_stock.py --test --debug")
    print("\n処理完了後、1秒間待機しています...")
    time.sleep(1)
    print("終了しました。")

if __name__ == "__main__":
    main() 