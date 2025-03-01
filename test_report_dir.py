#!/usr/bin/env python3
import os
import datetime

def save_test_report():
    # レポート保存ディレクトリの設定とチェック
    report_dir = "report"
    if not os.path.exists(report_dir):
        print(f"レポートディレクトリ '{report_dir}' が存在しないため作成します")
        os.makedirs(report_dir)
        
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(report_dir, f"test_report_{timestamp}.txt")
        
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("===== テストレポート =====\n")
            f.write(f"実行日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("===== レポート終了 =====\n")
            
        print(f"テストレポートを {output_file} に保存しました")
        
    except Exception as e:
        print(f"テストレポート保存中にエラー: {e}")

if __name__ == "__main__":
    save_test_report() 