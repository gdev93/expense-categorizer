from django.views.generic import ListView
from api.models import Category

class CategorySearchView(ListView):
    model = Category
    template_name = 'transactions/components/category_search_results.html'
    context_object_name = 'categories'

    def get_queryset(self):
        search_term = self.request.GET.get('category_name') or ''
        return Category.objects.filter(
            user=self.request.user,
            name__icontains=search_term
        ).order_by('name')
