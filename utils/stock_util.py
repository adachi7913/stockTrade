from repository.stock_repository import StockRepository


class StockUtil:
    def get_company_info(self, code):
        repository = StockRepository()
        return repository.fetch_company_info(code)

