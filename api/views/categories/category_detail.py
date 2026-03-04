from dataclasses import dataclass, asdict
from typing import Any

from django.views.generic import DetailView

from api.models import Category
from api.views.transactions.transaction_mixins import TransactionFilterMixin
from .mixins import CategoryEnrichedMixin

@dataclass
class CategoryDetailContextData:
    """Context data for category detail view"""
    category: Category
    category_summary: Category
    transactions: Any
    search_query: str
    year: int
    selected_year: int
    selected_months: list[str]
    paginate_by: int

    def to_context(self) -> dict:
        return asdict(self)

class CategoryDetailView(DetailView, CategoryEnrichedMixin, TransactionFilterMixin):
    model = Category
    template_name = 'categories/category_detail.html'
    context_object_name = 'category'

    def get_template_names(self):
        if self.request.headers.get('HX-Request') and self.request.headers.get('HX-Target') != 'main-content':
            return ['categories/category_detail_htmx.html']
        return [self.template_name]

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        category = self.object

        # Use our mixin logic to enrich just this one category
        category_summary = self.get_enriched_category_queryset(
            Category.objects.filter(id=category.id)
        )[0]

        category_filters = self.get_category_filters()
        tx_filters = self.get_transaction_filters()
        transactions = self.get_transaction_filter_query().filter(category=category)

        # Pagination for transactions
        paginate_by = tx_filters.paginate_by
        page = self.request.GET.get('page', 1)
        from django.core.paginator import Paginator
        paginator = Paginator(transactions, paginate_by)
        transactions_page = paginator.get_page(page)

        detail_context = CategoryDetailContextData(
            category=category,
            category_summary=category_summary,
            transactions=transactions_page,
            search_query=category_filters['search'],
            year=category_filters['year'],
            selected_year=category_filters['year'],
            selected_months=[str(m) for m in category_filters['months']],
            paginate_by=paginate_by
        )
        context.update(detail_context.to_context())
        return context
