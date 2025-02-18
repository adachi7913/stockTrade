def validate_stock_code(code: str) -> str:
    """
    銘柄コードのバリデーションを行い、適切な形式に変換します。
    5桁かつ末尾が0の場合は末尾の0を削除します。
    それ以外の場合は元のコードをそのまま返します。

    Args:
        code (str): 変換前の銘柄コード

    Returns:
        str: 変換後の銘柄コード
    """
    if len(code) == 5 and code.endswith('0'):
        return code[:-1]
    return code 