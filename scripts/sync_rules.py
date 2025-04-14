import os
import sys
import glob
import re

def natural_sort_key(s):
    """自然順ソート用のキーを生成する"""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', s)]

def sync_rule(rule_subdir_name):
    """指定されたルールサブディレクトリのmdファイルをmdcファイルに同期する"""
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    temp_rules_dir = os.path.join(workspace_root, 'temp_rules')
    rules_dir = os.path.join(workspace_root, '.cursor', 'rules')

    source_subdir = os.path.join(temp_rules_dir, rule_subdir_name)
    target_mdc_file = os.path.join(rules_dir, f"{rule_subdir_name}.mdc")

    if not os.path.isdir(source_subdir):
        print(f"Error: Source subdirectory '{source_subdir}' not found.")
        sys.exit(1)

    metadata_file = os.path.join(source_subdir, '_metadata.md')
    md_files = glob.glob(os.path.join(source_subdir, '[0-9]*.md')) # 数字始まりのmdファイルのみ対象
    md_files.sort(key=natural_sort_key) # ファイル名を自然順でソート

    combined_content = ""

    # 1. メタデータを読み込む
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                combined_content += f.read() + "\n\n" # メタデータの後に空行を追加
        except Exception as e:
            print(f"Error reading metadata file '{metadata_file}': {e}")
            sys.exit(1)
    else:
        print(f"Warning: Metadata file '_metadata.md' not found in '{source_subdir}'.")
        # メタデータがなくても処理は続行する

    # 2. 他のmdファイルを読み込んで結合する
    if not md_files:
        print(f"Warning: No numbered markdown files found in '{source_subdir}'.")
        # 番号付きmdファイルがなくてもメタデータだけでmdcを作る場合もあるので続行

    for md_file in md_files:
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                combined_content += f.read() + "\n\n" # 各ファイルの後に空行を追加
        except Exception as e:
            print(f"Error reading markdown file '{md_file}': {e}")
            # エラーが発生しても、処理を中断せずに次のファイルへ進むか、中断するか？
            # ここでは中断する方が安全かもしれない
            sys.exit(1)

    # 末尾の余分な改行を削除
    combined_content = combined_content.strip()

    # 3. mdcファイルに書き込む
    try:
        with open(target_mdc_file, 'w', encoding='utf-8') as f:
            f.write(combined_content)
        print(f"Successfully synced '{rule_subdir_name}' to '{target_mdc_file}'")
    except Exception as e:
        print(f"Error writing to target file '{target_mdc_file}': {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python sync_rules.py <rule_subdirectory_name>")
        print("Example: python sync_rules.py 01_project_overview")
        sys.exit(1)

    rule_name = sys.argv[1]
    sync_rule(rule_name) 