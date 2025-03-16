import json
from decimal import Decimal
from datetime import date, datetime

class CustomJSONEncoder(json.JSONEncoder):
    """
    カスタムJSONエンコーダー
    
    以下の型をJSON形式に変換可能:
    - Decimal: float型に変換
    - date/datetime: ISO形式の文字列に変換
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)

def dumps(obj, **kwargs):
    """
    オブジェクトをJSON文字列に変換する便利関数
    
    Args:
        obj: 変換対象のオブジェクト
        **kwargs: json.dumpsに渡す追加のキーワード引数
        
    Returns:
        str: JSON文字列
    """
    return json.dumps(obj, cls=CustomJSONEncoder, **kwargs) 