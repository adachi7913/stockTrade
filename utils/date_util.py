from datetime import date, datetime
import jpholiday
import os
from dotenv import load_dotenv

def get_current_datetime():
    """
    現在の日付と時刻を "yyyy/mm/dd hh:MM:ss" 形式で取得する関数です。
    
    Returns:
        str: 例 "2023/10/12 14:30:25"
    """
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

def is_holiday(today: date = None):
    """
    今日が休日（土日祝）かどうかを判定する関数です。
    debug_modeがonの場合は常にFalse（平日扱い）を返します。
    
    Returns:
        bool: 休日の場合True、平日の場合False
    """
    load_dotenv(override=True)
    debug_mode = os.environ.get("DEBUG_MODE", "off").lower() == "on"
    print(f"debug_mode: {debug_mode}")
    
    if debug_mode:
        return False
        
    if today is None:
        today = datetime.now().date()
    # 土曜日は5、日曜日は6
    is_weekend = today.weekday() >= 5
    is_holiday = jpholiday.is_holiday(today)
    
    print(f"today: {today}, is_weekend: {is_weekend}, is_holiday: {is_holiday}")
    return is_weekend or is_holiday

if __name__ == "__main__":
    print(get_current_datetime())
    print(f"Is holiday: {is_holiday()}")