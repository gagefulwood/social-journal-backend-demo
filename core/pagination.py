from rest_framework.pagination import PageNumberPagination

class StandardResultsPagination(PageNumberPagination):
    '''
    Default pagination for all list endpoints.
    Returns 20 results on each page.
    Response includes the count, next, previous, and results keys.
    '''
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class DashboardPagination(PageNumberPagination):
    '''
    Pagination for dashboard widgets. 5 results per page.
    '''
    page_size = 5