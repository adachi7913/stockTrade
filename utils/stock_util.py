from dao.stock_dao import StockDAO


class StockUtil:
    def get_company_info(self, code):
        dao = StockDAO()
        return dao.get_company_info(code)

