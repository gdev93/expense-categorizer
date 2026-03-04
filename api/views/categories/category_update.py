from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from api.forms import CategoryForm
from api.models import Category

class CategoryUpdateView(SuccessMessageMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'categories/category_form.html'
    success_message = "Categoria aggiornata con successo!"

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def get_success_url(self):
        return reverse_lazy('category_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        return super().form_valid(form)
