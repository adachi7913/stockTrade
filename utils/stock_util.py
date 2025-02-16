from repository.stock_repository import StockRepository


class StockUtil:
    def get_company_info(self, code):
        dao = StockRepository()
        return dao.get_company_info(code)

