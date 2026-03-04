from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView

from api.forms import CategoryForm
from api.models import Category

class CategoryCreateView(SuccessMessageMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'categories/category_form.html'
    success_url = reverse_lazy('category_list')
    success_message = "Categoria creata con successo!"

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.is_default = False
        return super().form_valid(form)

    def form_invalid(self, form):
        return super().form_invalid(form)
