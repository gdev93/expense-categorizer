import datetime
import logging

import pandas as pd
from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import Paginator
from django.db.models import Count, Sum, DecimalField, Q, QuerySet
from django.db.models.functions import Coalesce, ExtractMonth, ExtractYear
from django.http import HttpResponse
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from api.constants import ITALIAN_MONTHS
from api.models import Category, Transaction, Rule
from api.views.mixins import MonthYearFilterMixin
from api.views.transactions.transaction_mixins import TransactionFilterMixin

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


class CategoryEnrichedMixin(MonthYearFilterMixin):
    def get_enriched_category_queryset(self, base_category_queryset:QuerySet[Category,Category]):
        selected_year, selected_months = self.get_year_and_months()
        filter_q = Q(transactions__transaction_date__year=selected_year)
        if selected_months:
            filter_q &= Q(transactions__transaction_date__month__in=selected_months)

        enriched_categories = base_category_queryset.annotate(
            transaction_count=Count(
                'transactions',
                filter=filter_q
            ),
            transaction_amount=Coalesce(
                Sum(
                    'transactions__amount',
                    filter=filter_q
                ),
                0.0,
                output_field=DecimalField()
            )
        ).order_by('name')

        return enriched_categories
# 1. VISUALIZATION VIEW (The List)
class CategoryListView(LoginRequiredMixin, CategoryEnrichedMixin, ListView):
    model = Category
    template_name = 'categories/categories.html'
    context_object_name = 'categories'

    def get_template_names(self):
        if self.request.headers.get('HX-Request'):
            return ['categories/categories_htmx.html']
        return [self.template_name]

    def get_queryset(self):
        """
        Returns categories belonging to the logged-in user, annotated with:
        1. The count of associated transactions (transaction_count).
        2. The total amount of associated transactions (transaction_amount).
        """

        # 1. Filter: Start with categories belonging to the current user
        user_categories = self.model.objects.filter(user=self.request.user)

        search_query = self.request.GET.get('search')
        if search_query:
            user_categories = user_categories.filter(name__icontains=search_query)

        selected_category_ids = self.request.GET.getlist('categories')
        if any(selected_category_ids):
            user_categories = user_categories.filter(id__in=selected_category_ids)

        return self.get_enriched_category_queryset(user_categories)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass the form to the template so it can be rendered in the "New Category" card
        context['form'] = CategoryForm()

        # --- LOGIC FOR SUMMARY CARD ---
        # Get the queryset used by the list
        categories = context['categories']

        context['total'] = sum([category.transaction_amount for category in categories]) if categories else 0
        selected_year, selected_months = self.get_year_and_months()
        context['all_categories'] = Category.objects.filter(user=self.request.user).order_by('name')
        context['selected_categories'] = self.request.GET.getlist('categories')
        context['search_query'] = self.request.GET.get('search', '')
        context['year'] = selected_year
        context['selected_months'] = [str(m) for m in selected_months]
        return context


class CategoryExportView(LoginRequiredMixin, CategoryEnrichedMixin, View):
    def get(self, request, *args, **kwargs):
        selected_year, selected_months = self.get_year_and_months()
        selected_category_ids = request.GET.getlist('categories')
        base_query = Category.objects.filter(user=request.user)
        if any(selected_category_ids):
            base_query = base_query.filter(id__in=selected_category_ids)

        queryset = self.get_enriched_category_queryset(base_query)
        queryset = queryset.annotate(
            month=ExtractMonth('transactions__transaction_date'),
            year=ExtractYear('transactions__transaction_date'),
        ).filter(transaction_amount__gt=0)
        data = list(queryset.values('name', 'transaction_amount', 'month'))

        df = pd.DataFrame(data)
        if not df.empty:
            # Add Anno column and sort by year, month (numeric), and name
            df['Anno'] = selected_year
            df = df.sort_values(by=['Anno', 'month', 'name'])

            # Map numeric month to Italian name
            df['Mese'] = df['month'].map(ITALIAN_MONTHS)

            df = df.rename(columns={
                'name': 'Categoria',
                'transaction_amount': 'Importo',
            })

            # Ensure columns order as requested: month, year, category, total
            df = df[['Mese', 'Anno', 'Categoria', 'Importo']]
            df['Importo'] = df['Importo'].apply(float).astype(str).str.replace(".", ",", regex=False)
        else:
            df = pd.DataFrame(columns=['Mese', 'Anno', 'Categoria', 'Importo'])

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        response['Content-Disposition'] = f'attachment; filename="export_categorie_{selected_year}_{timestamp}.xlsx"'

        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Categorie')

        return response



# 2. CREATION VIEW
class CategoryCreateView(SuccessMessageMixin, CreateView):
    model = Category
    form_class = CategoryForm
    # We don't need a specific template because this view handles the POST request
    # from the form on the List page. If it fails validation, it re-renders the list.
    template_name = 'categories/category-creation.html'
    success_url = reverse_lazy('category_list')
    success_message = "Categoria creata con successo."

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        
        # Advance onboarding if at step 1 or before
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.onboarding_step < 2:
            profile.onboarding_step = 2
            profile.save()
            
        return response

    def form_invalid(self, form):
        # If invalid, we must re-render the list context so the page doesn't break
        return self.render_to_response(self.get_context_data(form=form))


class CategoryDetailView(DetailView, CategoryEnrichedMixin, TransactionFilterMixin):
    """
    A view to display the details of a specific Category,
    and list all associated transactions with pagination.
    """
    model = Category
    template_name = 'categories/category-detail.html'

    def get_template_names(self):
        if self.request.headers.get('HX-Request'):
            return ['categories/category-details-htmx.html']
        return [self.template_name]

    def get_queryset(self):
        # Security: Only allow the user to view their own categories
        return Category.objects.filter(user=self.request.user)

    def _get_filters(self):
        search_query = self.request.GET.get('search', '')
        selected_year, processed_months = self.get_year_and_months()
        return search_query, selected_year, processed_months

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        category = self.object
        search_query, selected_year, selected_months = self._get_filters()
        base_query = Category.objects.filter(id=category.pk, user=self.request.user)
        # 2. Fetch Aggregated Summary Data for the Summary Card
        summary = self.get_enriched_category_queryset(base_query).first()

        context['category_summary'] = summary

        transaction_list = self.get_transaction_filter_query().filter(category=category)

        # Pagination logic
        paginator = Paginator(transaction_list, 20)  # Show 20 transactions per page
        page_number = self.request.GET.get('page') or 1

        transactions = paginator.page(page_number)

        context['transactions'] = transactions
        context['search_query'] = search_query
        context['selected_year'] = selected_year
        context['selected_months'] = [str(m) for m in selected_months]

        return context


class CategoryUpdateView(SuccessMessageMixin, UpdateView):
    """
    A view to allow updating an existing Category.
    """
    model = Category
    form_class = CategoryForm
    template_name = 'categories/category-edit.html'
    success_message = "Categoria aggiornata con successo."

    def get_queryset(self):
        # Security: Only allow the user to edit their own categories
        return Category.objects.filter(user=self.request.user)

    def get_success_url(self):
        return reverse('category_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        return super().form_valid(form)

class CategoryDeleteView(DeleteView):
    """
    A view to securely delete a user's category and reassign its transactions/rules.
    """
    model = Category
    template_name = 'categories/category_confirm_delete.html'
    success_url = reverse_lazy('category_list')

    def get_queryset(self):
        # Security: Only allow the user to delete their own categories
        return Category.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Provide other categories for reassignment
        context['other_categories'] = Category.objects.filter(
            user=self.request.user
        ).exclude(pk=self.object.pk)
        return context

    def form_valid(self, form):
        category_to_delete = self.get_object()
        replacement_category_id = self.request.POST.get('replacement_category')
        new_category_name = self.request.POST.get('new_category_name')

        if new_category_name:
            # Create a new category or get existing if it has the same name
            replacement_category, created = Category.objects.get_or_create(
                name=new_category_name,
                user=self.request.user
            )
        elif replacement_category_id:
            try:
                replacement_category = Category.objects.get(
                    pk=replacement_category_id,
                    user=self.request.user
                )
            except Category.DoesNotExist:
                messages.error(self.request, "La categoria di sostituzione selezionata non è valida.")
                return self.render_to_response(self.get_context_data(form=form))
        else:
            messages.error(self.request, "Devi selezionare una categoria di sostituzione o crearne una nuova.")
            return self.render_to_response(self.get_context_data(form=form))

        # Reassign transactions
        Transaction.objects.filter(category=category_to_delete).update(category=replacement_category)
        Rule.objects.filter(category=category_to_delete).update(category=replacement_category)

        messages.success(self.request, f"Categoria '{category_to_delete.name}' eliminata. Tutte le transazioni sono state spostate in '{replacement_category.name}'.")
        return super().form_valid(form)