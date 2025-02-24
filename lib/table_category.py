"""
このファイルは、enumを用いて日本語のカテゴリー名と英語のテーブル接頭辞を対応させる機能を提供します。
引数で日本語のカテゴリー名を渡すと、対応する英語のテーブル接頭辞を返します。
"""

from enum import Enum

class TableCategory(Enum):
    RETAIL = ("小売", "retail")
    TRADING_WHOLESALE = ("商社・卸売", "trading_wholesale")
    ENERGY_RESOURCES = ("エネルギー資源", "energy_resources")
    NONBANK_FINANCE = ("金融（除く銀行）", "nonbank_finance")
    ELECTRONICS_PRECISION = ("電機・精密", "electronics_precision")
    MATERIAL_CHEMICAL = ("素材・化学", "material_chemical")
    TRANSPORTATION_LOGISTICS = ("運輸・物流", "transportation_logistics")
    ELECTRIC_GAS = ("電気・ガス", "electric_gas")
    REAL_ESTATE = ("不動産", "real_estate")
    BANK = ("銀行", "bank")
    INFORMATION_COMMUNICATION_SERVICES = ("情報通信・サービスその他", "information_communication_services")
    STEEL_NONSTEEL = ("鉄鋼・非鉄", "steel_nonsteel")
    MACHINERY = ("機械", "machinery")
    PHARMACEUTICALS = ("医薬品", "pharmaceuticals")
    OTHERS = ("その他", "others")
    AUTOMOTIVE_TRANSPORTATION = ("自動車・輸送機", "automotive_transportation")
    CONSTRUCTION_MATERIALS = ("建設・資材", "construction_materials")
    FOOD = ("食品", "food")
    
    def __init__(self, japanese: str, english: str):
        self.japanese = japanese
        self.english = english

    @classmethod
    def get_table_prefix(cls, japanese_value: str) -> str:
        """
        指定された日本語のカテゴリー名に対応する英語のテーブル接頭辞を返す
        """
        japanese_value = japanese_value.strip()
        # print(f"変換対象の業種名: '{japanese_value}'")  # デバッグ用
        
        # 全カテゴリーとの比較を表示
        for category in cls:
            # print(f"比較: '{category.japanese}' == '{japanese_value}' -> {category.japanese == japanese_value}")
            if category.japanese == japanese_value:
                return category.english
        
        # マッチしなかった場合、全カテゴリーを表示
        available_categories = [f"'{c.japanese}'" for c in cls]
        raise ValueError(f"未知のカテゴリー: '{japanese_value}'\n利用可能なカテゴリー: {available_categories}")

if __name__ == "__main__":
    # テスト用の日本語カテゴリー一覧
    test_categories = [
        "小売",
        "商社・卸売",
        "エネルギー資源",
        "金融（除く銀行）",
        "電機・精密",
        "素材・化学",
        "運輸・物流",
        "電気・ガス",
        "不動産",
        "銀行",
        "情報通信・サービスその他",
        "鉄鋼・非鉄",
        "機械",
        "医薬品",
        "その他",
        "自動車・輸送機",
        "建設・資材",
        "食品"
    ]
    
    for cat in test_categories:
        try:
            prefix = TableCategory.get_table_prefix(cat)
            print(f"{cat} -> {prefix}")
        except ValueError as e:
            print(e)