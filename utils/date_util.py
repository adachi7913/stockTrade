from datetime import datetime

def get_current_datetime():
    """
    現在の日付と時刻を "yyyy/mm/dd hh:MM:ss" 形式で取得する関数です。
    
    Returns:
        str: 例 "2023/10/12 14:30:25"
    """
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

if __name__ == "__main__":
    print(get_current_datetime())