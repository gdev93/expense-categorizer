import logging
from dataclasses import dataclass

from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Sum, DecimalField
from django.db.models.functions import Coalesce
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from api.models import Category, Transaction

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
        """
        Returns categories belonging to the logged-in user, annotated with:
        1. The count of associated transactions (transaction_count).
        2. The total amount of associated transactions (transaction_amount).
        """

        # 1. Filter: Start with categories belonging to the current user
        user_categories = self.model.objects.filter(user=self.request.user)

        # 2. Annotate: Add the aggregated fields
        #    - Count('transactions'): Counts all related Transaction objects.
        #    - Sum('transactions__amount'): Sums the 'amount' field of related transactions.
        #    - Coalesce: Ensures the result is 0 instead of None if no transactions exist.
        enriched_categories = user_categories.annotate(
            transaction_count=Count('transactions'),
            transaction_amount=Coalesce(
                Sum('transactions__amount'),
                0.0,
                output_field=DecimalField()
            )
        ).order_by('name')

        return enriched_categories

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass the form to the template so it can be rendered in the "New Category" card
        context['form'] = CategoryForm()

        # --- LOGIC FOR SUMMARY CARD ---
        # Get the queryset used by the list
        categories = context['categories']

        default_category = max(categories, key=lambda cat: cat.transaction_count)
        context['default_category'] = default_category
        context['available_years'] =  list(
            Transaction.objects.filter(
                user=self.request.user,
                status="categorized",
                transaction_date__isnull=False,
            )
            .values_list("transaction_date__year", flat=True)
            .distinct()
            .order_by("-transaction_date__year")
        )


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




class CategoryDetailView(UpdateView):
    """
    A view to display the details of a specific Category, allow updates,
    and list all associated transactions with pagination.
    """
    model = Category
    form_class = CategoryForm
    template_name = 'categories/category-detail.html'  # New template
    success_url = reverse_lazy('category_list')

    def get_queryset(self):
        # Security: Only allow the user to view/edit their own categories
        return Category.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        category = self.object

        # 1. Fetch Aggregated Summary Data for the Summary Card
        # This re-calculates the enrichment for the single category object
        summary = Category.objects.filter(pk=category.pk).annotate(
            transaction_count=Count('transactions'),
            transaction_amount=Coalesce(
                Sum('transactions__amount'),
                0.00,
                output_field=DecimalField()
            )
        ).first()

        context['category_summary'] = summary

        # 2. Fetch and Paginate Associated Transactions
        transaction_list = Transaction.objects.filter(
            user=self.request.user,
            category=category
        ).order_by('-transaction_date', '-created_at')  # Ordering defined in models.py

        # Pagination logic
        paginator = Paginator(transaction_list, 20)  # Show 20 transactions per page
        page_number = self.request.GET.get('page') or 1

        transactions = paginator.page(page_number)

        context['transactions'] = transactions

        return context

    def form_valid(self, form):
        # The form_valid method handles the update. The success message is shown
        # after the redirect to the success_url (or in this case, the same page).
        messages.success(self.request, "📝 Categoria aggiornata correttamente.")
        return super().form_valid(form)

class CategoryDeleteView(DeleteView):
    """
    A view to securely delete a user's category.
    """
    model = Category
    # Django's DeleteView expects a template named *_confirm_delete.html by default
    template_name = 'categories/category_confirm_delete.html'
    success_url = reverse_lazy('category_list')

    def get_queryset(self):
        # Security: Only allow the user to delete their own categories that are NOT default/system categories
        return Category.objects.filter(user=self.request.user, is_default=False)

    def form_valid(self, form):
        # Add a success message after deletion
        messages.success(self.request, f"🗑️ Categoria '{self.object.name}' eliminata con successo.")
        # Important: The model's Foreign Key (Category to Transaction) configuration
        # (e.g., CASCADE, SET_NULL, PROTECT) will determine what happens to related transactions.
        return super().form_valid(form)