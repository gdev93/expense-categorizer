import logging

from django import forms
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from api.models import Category

logger = logging.getLogger(__name__)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'es. Alimentari'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'es. Spese fatte al supermercato...'
            }),
        }
        labels = {
            'name': 'Nome Categoria',
            'description': 'Descrizione (Opzionale)'
        }


# 1. VISUALIZATION VIEW (The List)
class CategoryListView(ListView):
    model = Category
    template_name = 'categories/categories.html'
    context_object_name = 'categories'

    def get_queryset(self):
        # Only fetch categories belonging to the logged-in user
        return Category.objects.filter(user=self.request.user).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass the form to the template so it can be rendered in the "New Category" card
        context['form'] = CategoryForm()
        return context


# 2. CREATION VIEW
class CategoryCreateView(CreateView):
    model = Category
    form_class = CategoryForm
    # We don't need a specific template because this view handles the POST request
    # from the form on the List page. If it fails validation, it re-renders the list.
    template_name = 'categories/categories.html'
    success_url = reverse_lazy('category_list')

    def form_valid(self, form):
        # Automatically assign the current user to the category
        form.instance.user = self.request.user
        messages.success(self.request, "✅ Categoria creata con successo!")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "⚠️ Errore durante la creazione. Controlla i dati.")
        # If invalid, we must re-render the list context so the page doesn't break
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs):
        # Re-populate the category list if the form submission fails
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.filter(user=self.request.user).order_by('name')
        return context


# 3. UPDATE VIEW
class CategoryUpdateView(UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'categories/category_update.html'  # Requires a small separate template
    success_url = reverse_lazy('category_list')

    def get_queryset(self):
        # Security: Prevent editing other users' categories
        return Category.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "📝 Categoria aggiornata correttamente.")
        return super().form_valid(form)
