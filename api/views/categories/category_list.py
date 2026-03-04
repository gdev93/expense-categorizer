from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Any

from django.db.models import QuerySet
from django.views.generic import ListView

from api.forms import CategoryForm
from api.models import Category
from .mixins import CategoryEnrichedMixin

@dataclass
class CategoryListContextData:
    """Context data for category list view"""
    form: CategoryForm
    categories: list[Category]
    all_categories: QuerySet[Category]
    total: Decimal
    selected_categories: list[str]
    search_query: str
    year: int
    selected_months: list[str]

    def to_context(self) -> dict:
        return asdict(self)

class CategoryListView(CategoryEnrichedMixin, ListView):
    model = Category
    template_name = 'categories/categories.html'
    context_object_name = 'categories'

    def get_template_names(self):
        if self.request.headers.get('HX-Request') and self.request.headers.get('HX-Target') != 'main-content':
            return ['categories/categories_htmx.html']
        return [self.template_name]

    def get_queryset(self):
        """
        Returns categories belonging to the logged-in user, annotated with:
        1. The count of associated transactions (transaction_count).
        2. The total amount of associated transactions (transaction_amount).
        """
        base_queryset = Category.objects.filter(user=self.request.user)
        filters = self.get_category_filters()

        if filters['search']:
            base_queryset = base_queryset.filter(name__icontains=filters['search'])
        if filters['selected_category_ids']:
            base_queryset = base_queryset.filter(id__in=filters['selected_category_ids'])

        return self.get_enriched_category_queryset(base_queryset)

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        categories_list = context['categories']
        total = sum((c.transaction_amount for c in categories_list), Decimal('0'))
        
        filters = self.get_category_filters()
        all_categories = Category.objects.filter(user=self.request.user).order_by('name')

        list_context = CategoryListContextData(
            form=CategoryForm(),
            categories=categories_list,
            all_categories=all_categories,
            total=total,
            selected_categories=filters['selected_category_ids'],
            search_query=filters['search'],
            year=filters['year'],
            selected_months=[str(m) for m in filters['months']]
        )
        context.update(list_context.to_context())
        return context
