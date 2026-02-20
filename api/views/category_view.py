import datetime
import logging
from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Any, Optional

import pandas as pd
from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import Paginator
from django.db.models import Count, Sum, DecimalField, Q, QuerySet
from django.db.models.functions import Coalesce, ExtractMonth, ExtractYear
from django.http import HttpResponse, HttpRequest
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from api.constants import ITALIAN_MONTHS
from api.models import Category, Transaction, Rule, Merchant
from api.privacy_utils import decrypt_value
from api.services import TransactionAggregationService
from api.views.mixins import MonthYearFilterMixin
from api.views.transactions.transaction_mixins import TransactionFilterMixin
from processors.similarity_matcher import SimilarityMatcher

logger = logging.getLogger(__name__)


class CategorySearchView(LoginRequiredMixin, ListView):
    model = Category
    template_name = 'transactions/components/category_search_results.html'
    context_object_name = 'categories'

    def get_queryset(self):
        search_term = self.request.GET.get('category_name') or ''
        return Category.objects.filter(
            user=self.request.user,
            name__icontains=search_term
        ).order_by('name')

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Food'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'e.g. Supermarket expenses...'
            }),
        }
        labels = {
            'name': 'Category Name',
            'description': 'Description (Optional)'
        }


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


class CategoryEnrichedMixin(MonthYearFilterMixin):
    def get_category_filters(self):
        # Check if a reset was requested
        year, months = self.get_year_and_months()
        if self.request.GET.get('reset') == '1':
            self.request.session.pop('filter_category_search', None)
            self.request.session.pop('filter_category_selected', None)
            # If your Mixin stores months/years in session, clear them here too
            return {'search': '', 'selected_category_ids': [], 'year': year, 'months': months}

        filters = {}

        # Search Filter
        if 'search' in self.request.GET:
            filters['search'] = self.request.GET.get('search')
            self.request.session['filter_category_search'] = filters['search']
        else:
            filters['search'] = self.request.session.get('filter_category_search', '')

        # Categories Filter
        if 'categories' in self.request.GET:
            filters['selected_category_ids'] = self.request.GET.getlist('categories')
            self.request.session['filter_category_selected'] = filters['selected_category_ids']
        else:
            filters['selected_category_ids'] = self.request.session.get('filter_category_selected', [])

        filters['year']=year
        filters['months']=months
        return filters

    def get_enriched_category_queryset(self, base_category_queryset:QuerySet[Category,Category]):
        filters = self.get_category_filters()
        filter_q = Q(transactions__transaction_date__year=filters['year'])
        if filters['months']:
            filter_q &= Q(transactions__transaction_date__month__in=filters['months'])

        # Group and Count in DB, Sum in Python
        categories = base_category_queryset.annotate(
            transaction_count=Count(
                'transactions',
                filter=filter_q
            )
        ).order_by('name')
        
        # Adding transaction_amount in Python
        categories_list = list(categories)
        category_ids = [c.id for c in categories_list]
        
        tx_filter = Q(category_id__in=category_ids, transaction_date__year=filters['year'])
        if filters['months']:
            tx_filter &= Q(transaction_date__month__in=filters['months'])
            
        # Optimization: Fetch only necessary fields
        transactions_queryset = Transaction.objects.filter(tx_filter)
        sums = TransactionAggregationService.calculate_category_sums(transactions_queryset, category_ids)
        
        for c in categories_list:
            c.transaction_amount = sums.get(c.id, Decimal('0'))

        return categories_list
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

        filters = self.get_category_filters()
        if filters['search']:
            user_categories = user_categories.filter(name__icontains=filters['search'])

        if any(filters['selected_category_ids']):
            user_categories = user_categories.filter(id__in=filters['selected_category_ids'])

        return self.get_enriched_category_queryset(user_categories)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass the form to the template so it can be rendered in the "New Category" card
        form = CategoryForm()

        # --- LOGIC FOR SUMMARY CARD ---
        # Get the queryset used by the list
        categories = context['categories']

        total = sum([category.transaction_amount for category in categories]) if categories else Decimal('0')
        filters = self.get_category_filters()
        all_categories = Category.objects.filter(user=self.request.user).order_by('name')
        
        category_list_context = CategoryListContextData(
            form=form,
            categories=categories,
            all_categories=all_categories,
            total=total,
            selected_categories=filters['selected_category_ids'],
            search_query=filters['search'],
            year=filters['year'],
            selected_months=[str(m) for m in filters['months']]
        )
        
        context.update(category_list_context.to_context())
        return context


class CategoryExportView(LoginRequiredMixin, CategoryEnrichedMixin, View):
    def get(self, request, *args, **kwargs):
        filters = self.get_category_filters()
        selected_year = filters['year']
        selected_category_ids = filters['selected_category_ids']
        
        # Get all transactions for these categories in the selected year
        tx_filter = Q(user=request.user, transaction_date__year=selected_year, category__isnull=False)
        if any(selected_category_ids):
            tx_filter &= Q(category_id__in=selected_category_ids)
        
        if filters['months']:
            tx_filter &= Q(transaction_date__month__in=filters['months'])

        # Group by category name and month in Python
        grouped_data = TransactionAggregationService.calculate_category_monthly_sums(Transaction.objects.filter(tx_filter))
        
        # Convert to list of dicts for DataFrame
        data = []
        for (name, month), amount in grouped_data.items():
            if amount > 0:
                data.append({
                    'name': name,
                    'transaction_amount': float(amount),
                    'month': month
                })

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
    success_message = "Category created successfully."

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        category = self.object
        filters = self.get_transaction_filters()
        base_query = Category.objects.filter(id=category.pk, user=self.request.user)
        # 2. Fetch Aggregated Summary Data for the Summary Card
        summary = self.get_enriched_category_queryset(base_query)[0]

        transaction_list = self.get_transaction_filter_query().filter(category=category)

        # Pagination logic
        paginator = Paginator(transaction_list, filters.paginate_by)
        page_number = self.request.GET.get('page') or 1

        transactions = paginator.page(page_number)

        category_detail_context = CategoryDetailContextData(
            category=category,
            category_summary=summary,
            transactions=transactions,
            search_query=filters.search,
            year=filters.year,
            selected_year=filters.year,
            selected_months=[str(m) for m in filters.months],
            paginate_by=filters.paginate_by
        )

        context.update(category_detail_context.to_context())
        return context


class CategoryUpdateView(SuccessMessageMixin, UpdateView):
    """
    A view to allow updating an existing Category.
    """
    model = Category
    form_class = CategoryForm
    template_name = 'categories/category-edit.html'
    success_message = "Category updated successfully."

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
                messages.error(self.request, "The selected replacement category is invalid.")
                return self.render_to_response(self.get_context_data(form=form))
        else:
            messages.error(self.request, "You must select a replacement category or create a new one.")
            return self.render_to_response(self.get_context_data(form=form))

        # Reassign transactions
        Transaction.objects.filter(category=category_to_delete).update(category=replacement_category)
        Rule.objects.filter(category=category_to_delete).update(category=replacement_category)

        messages.success(self.request, f"Category '{category_to_delete.name}' deleted. All transactions have been moved to '{replacement_category.name}'.")
        return super().form_valid(form)

class CategoryFromMerchant(LoginRequiredMixin, View, SimilarityMatcher):

    def get(self, request:HttpRequest, *args, **kwargs):
        merchant_id = request.GET.get('merchant_id')
        if not merchant_id:
            return HttpResponse("", status=400)
            
        try:
            merchant = Merchant.objects.get(pk=merchant_id, user=request.user)
            # SimilarityMatcher needs user
            self.user = request.user
            
            transaction = self.find_most_frequent_transaction_for_merchant(merchant)
            if transaction and transaction.category:
                return HttpResponse(transaction.category.name)
        except Merchant.DoesNotExist:
            return HttpResponse("", status=404)
        except Exception as e:
            return HttpResponse("", status=500)
            
        return HttpResponse("", status=204)
