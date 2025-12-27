# views.py (add to your existing views file)
import datetime
import os
from calendar import monthrange
from dataclasses import dataclass, asdict, field
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q, QuerySet, Exists, OuterRef  # Import Q for complex lookups
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, CreateView
from django.views.generic import UpdateView

from api.models import Transaction, Category, Rule, Merchant, CsvUpload, InternalBankTransfer

pre_check_confidence_threshold = os.environ.get('PRE_CHECK_CONFIDENCE_THRESHOLD', 0.8)

class TransactionIncomeCreateView(LoginRequiredMixin, CreateView):
    """
    A view to create a new Transaction instance of type income.
    Simplified form with only date and amount required.
    """
    model = Transaction
    template_name = 'transactions/transaction_income.html'
    fields = [
        'transaction_date',
        'amount',
    ]


    @transaction.atomic
    def form_valid(self, form):
        """
        Set proper transaction defaults for income type.
        Income transactions don't require merchant or category.
        """
        # Set transaction defaults for income
        form.instance.user = self.request.user
        form.instance.transaction_type = 'income'
        form.instance.description = self.request.POST.get('description', 'User input')
        form.instance.modified_by_user = True
        form.instance.status = 'categorized'

        # Income transactions typically don't have a merchant
        form.instance.merchant = None
        form.instance.merchant_raw_name = 'Income'

        # Get the transaction date from the form
        transaction_date = form.cleaned_data.get('transaction_date')

        # Calculate the first and last day of the month
        first_day_of_month = transaction_date.replace(day=1)

        # Get the last day of the month using monthrange
        last_day = monthrange(transaction_date.year, transaction_date.month)[1]
        last_day_of_month = transaction_date.replace(day=last_day)

        # Find CSV upload that has transactions in this date range
        csv_upload_in_date_range = CsvUpload.objects.filter(
            user=self.request.user,
            transactions__transaction_date__gte=first_day_of_month,
            transactions__transaction_date__lte=last_day_of_month
        ).distinct().first()

        # Associate the transaction with the found CSV upload (if any)
        form.instance.csv_upload = csv_upload_in_date_range

        self.object = form.save()

        # Redirect to transaction list after successful creation
        return redirect(self.request.POST.get("redirect_target_url") or 'transaction_list')

    def get_success_url(self):
        """Redirect to transaction list after successful creation"""
        return reverse('transaction_list')

class TransactionCreateView(LoginRequiredMixin, CreateView):
    """
    A view to create a new Transaction instance of type expense.
    Handles all transaction data including merchant, category, and amount.
    """
    model = Transaction
    template_name = 'transactions/transaction_expense_create.html'
    fields = [
        'transaction_date',
        'amount',
        'merchant_raw_name',
        'description',
        'category'
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.filter(
            Q(user=self.request.user) | Q(is_default=True)
        ).distinct()
        return context

    @transaction.atomic
    def form_valid(self, form):
        """
        Customizes form validation to handle new category creation,
        merchant assignment, and set proper transaction defaults.
        """
        # Handle new category creation
        new_category_name = self.request.POST.get('new_category_name', '').strip()

        if new_category_name:
            new_category, created = Category.objects.get_or_create(
                name=new_category_name,
                user=self.request.user,
                defaults={'is_default': False}
            )
            form.instance.category = new_category

        # Handle merchant
        merchant_name = self.request.POST.get('merchant_raw_name', '').strip()

        if merchant_name:
            merchant_db = Merchant.get_similar_merchants_by_names(merchant_name, self.request.user, pre_check_confidence_threshold).first()
            if not merchant_db:
                merchant_db = Merchant.objects.create(name=merchant_name, user=self.request.user)
            form.instance.merchant = merchant_db

        # Set transaction defaults
        form.instance.user = self.request.user
        form.instance.transaction_type = 'expense'
        form.instance.modified_by_user = True
        form.instance.status = 'categorized'

        self.object = form.save()

        # Redirect to transaction list after successful creation
        return redirect('transaction_list')

    def get_success_url(self):
        """Redirect to transaction list after successful creation"""
        return reverse('transaction_list')

class TransactionDetailUpdateView(LoginRequiredMixin, UpdateView):
    """
    A view to display and handle updates for a single Transaction instance.
    The view will re-render the detail template upon successful update,
    staying on the current page.
    """
    model = Transaction
    template_name = 'transactions/transaction_detail.html'
    fields = [
        'transaction_date',
        'amount',
        'merchant_raw_name',
        'description',
        'category'
    ]

    def post(self, request, *args, **kwargs):
        """Handle both updates and deletes"""
        if 'delete' in request.POST:
            return self.delete(request, *args, **kwargs)
        return super().post(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """Handle transaction deletion"""
        self.get_object().delete()

        # Check if filters were stored before deletion
        redirect_filters = request.POST.get('redirect_filters', '')

        # Build redirect URL with preserved filters
        redirect_url = reverse('transaction_list')

        if redirect_filters:
            # The filters already include the '?' or are empty
            redirect_url = redirect_url + redirect_filters

        return redirect(redirect_url)

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.filter(
            Q(user=self.request.user)
        ).distinct()
        return context

    @transaction.atomic
    def form_valid(self, form):
        """
        Customizes form validation to handle new category creation,
        set the modified_by_user flag, and most importantly,
        **return the rendered template instead of a redirect.**
        """
        new_category_name = self.request.POST.get('new_category_name', '').strip()

        if new_category_name:
            new_category, created = Category.objects.get_or_create(
                name=new_category_name,
                user=self.request.user,  # Assigns the new category to the current user
                defaults={'is_default': False}
            )

        else:
            new_category = form.instance.category
        merchant_name = self.request.POST.get('merchant_raw_name', '').strip()

        if merchant_name:
            merchant_db = Merchant.get_similar_merchants_by_names(merchant_name, self.request.user, pre_check_confidence_threshold).first()
            if not merchant_db:
                merchant_db = Merchant.objects.create(name=merchant_name, user=self.request.user)
            form.instance.merchant = merchant_db

        form.instance.category = new_category
        form.instance.modified_by_user = True
        form.instance.status = 'categorized'
        self.object = form.save()

        return self.render_to_response(self.get_context_data(form=form))


@dataclass
class TransactionListContextData:
    """Context data for transaction list view"""
    categories: list[dict[str, Any]]
    selected_category: str
    selected_status: str
    search_query: str
    uncategorized_transaction: QuerySet[Transaction, Transaction]  # QuerySet
    total_count: int
    total_amount: float
    category_count: int
    rules: QuerySet[Rule, Rule]  # QuerySet
    selected_months: list[str] = field(default_factory=list)
    def to_context(self) -> dict[str, Any]:
        """Convert dataclass to context dictionary"""
        return asdict(self)


class TransactionListView(LoginRequiredMixin, ListView):
    """Display list of transactions with filtering and pagination"""
    model = Transaction
    template_name = 'transactions/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 50
    default_categories: list[
        str] = "Casa,Spesa,Auto,Carburante,Vita sociale,Pizza,Regali,Vacanze,Sport,Bollette,Scuola,Bambini,Shopping,Abbonamenti,Affitto,Baby-sitter,Trasporti,Spese mediche,Partita Iva, Bonifico".split(
        ',')


    def get_queryset(self):
        """Filter transactions based on user and query parameters"""
        queryset = Transaction.objects.filter(
            user=self.request.user,
            transaction_type='expense',
            category__isnull=False,
            merchant_id__isnull=False  # Filtra per escludere i valori NULL
        ).annotate(is_internal_bank_transfer=Exists(
            InternalBankTransfer.objects.filter(
                expense_transaction_id=OuterRef('pk')
            )
        )).select_related('category', 'merchant').order_by('-transaction_date', '-created_at')

        # Filter by category
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # Filter by amount
        amount = self.request.GET.get('amount')
        amount_operator = self.request.GET.get('amount_operator', 'eq')
        if amount:
            try:
                amount_value = float(amount)
                if amount_operator == 'eq':
                    queryset = queryset.filter(amount=amount_value)
                elif amount_operator == 'gt':
                    queryset = queryset.filter(amount__gt=amount_value)
                elif amount_operator == 'gte':
                    queryset = queryset.filter(amount__gte=amount_value)
                elif amount_operator == 'lt':
                    queryset = queryset.filter(amount__lt=amount_value)
                elif amount_operator == 'lte':
                    queryset = queryset.filter(amount__lte=amount_value)
            except (ValueError, TypeError):
                pass

        # Filter by months
        selected_months = self.request.GET.getlist('months')
        if selected_months:
            # Interpret months as numeric month values for the selected year
            try:
                selected_year_qs = int(self.request.GET.get('year') or datetime.datetime.now().year)
            except (TypeError, ValueError):
                selected_year_qs = datetime.datetime.now().year

            month_queries = Q()
            for month_str in selected_months:
                try:
                    month = int(month_str)
                    month_queries |= Q(
                        transaction_date__year=selected_year_qs,
                        transaction_date__month=month
                    )
                except (ValueError, TypeError):
                    pass
            if month_queries:
                queryset = queryset.filter(month_queries)

        # Search filter
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(merchant_raw_name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        return queryset

    def get_available_months(self):
        """Get list of available months from transactions"""
        transactions = Transaction.objects.filter(
            user=self.request.user,
            transaction_type='expense'
        ).dates('transaction_date', 'month', order='DESC')

        months = []
        for date in transactions:
            months.append({
                'value': date.strftime('%Y-%m'),
                'label': date.strftime('%B %Y'),
                'label_it': self.get_italian_month_name(date)
            })
        return months

    @staticmethod
    def get_italian_month_name(date):
        """Convert date to Italian month name format"""
        italian_months = {
            1: 'Gennaio', 2: 'Febbraio', 3: 'Marzo', 4: 'Aprile',
            5: 'Maggio', 6: 'Giugno', 7: 'Luglio', 8: 'Agosto',
            9: 'Settembre', 10: 'Ottobre', 11: 'Novembre', 12: 'Dicembre'
        }
        return f"{italian_months[date.month]} {date.year}"

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)

        # Get all categories for filter dropdown
        categories = list(Category.objects.filter(
            Q(user=self.request.user) | Q(user__isnull=True)
        ).order_by('name').values('id', 'name'))

        # Base queryset for user transactions
        user_transactions = self.get_queryset()

        # Apply month filter to summary data if months are selected
        # 'months' values are month numbers (1..12); restrict by selected year from GET 'year'
        selected_months = self.request.GET.getlist('months')
        try:
            first_transaction_date = user_transactions.first()
            selected_year = int(self.request.GET.get('year',
                                                     first_transaction_date.transaction_date.year if first_transaction_date else datetime.datetime.now().year))
        except (TypeError, ValueError):
            selected_year = datetime.datetime.now().year

        if selected_months:
            month_queries = Q()
            for month_str in selected_months:
                try:
                    month = int(month_str)
                    month_queries |= Q(
                        transaction_date__year=selected_year,
                        transaction_date__month=month
                    )
                except (ValueError, TypeError):
                    pass
            if month_queries:
                user_transactions = user_transactions.filter(month_queries)
        transaction_list_context = TransactionListContextData(
            categories=categories,
            selected_status=self.request.GET.get('status', ''),
            search_query=self.request.GET.get('search', ''),
            uncategorized_transaction=Transaction.objects.filter(user=self.request.user, status='uncategorized',
                                                                 transaction_type='expense'),
            total_count=user_transactions.count(),
            total_amount=user_transactions.filter(status="categorized").exclude(
                id__in=InternalBankTransfer.objects.filter(user=self.request.user).values_list(
                    'expense_transaction__id', flat=True)).aggregate(
                total=Sum('amount')
            )['total'] or 0,
            category_count=user_transactions.values('category').distinct().count(),
            rules=Rule.objects.filter(user=self.request.user, is_active=True),
            selected_category=self.request.GET.get('category', ''),
            # available_months is now provided by a global context processor
            selected_months=selected_months
        )
        context.update(transaction_list_context.to_context())

        # Add amount filter context
        context['selected_amount'] = self.request.GET.get('amount', '')
        context['selected_amount_operator'] = self.request.GET.get('amount_operator', 'eq')

        return context


class IncomeListView(LoginRequiredMixin, ListView):
    """Display list of income transactions with filtering and pagination"""
    model = Transaction
    template_name = 'transactions/transaction_income_list.html'
    context_object_name = 'transactions'
    paginate_by = 50

    def get_queryset(self):
        queryset = (Transaction.objects
                    .filter(
                        user=self.request.user,
                        transaction_type='income'
        ).exclude(
            id__in=InternalBankTransfer.objects.filter(user=self.request.user).values_list('income_transaction__id',
                                                                                           flat=True))
                    .order_by('-transaction_date', '-created_at'))

        # Filter by amount
        amount = self.request.GET.get('amount')
        amount_operator = self.request.GET.get('amount_operator', 'eq')
        if amount:
            try:
                amount_value = float(amount)
                if amount_operator == 'eq':
                    queryset = queryset.filter(amount=amount_value)
                elif amount_operator == 'gt':
                    queryset = queryset.filter(amount__gt=amount_value)
                elif amount_operator == 'gte':
                    queryset = queryset.filter(amount__gte=amount_value)
                elif amount_operator == 'lt':
                    queryset = queryset.filter(amount__lt=amount_value)
                elif amount_operator == 'lte':
                    queryset = queryset.filter(amount__lte=amount_value)
            except (ValueError, TypeError):
                pass

        # Filter by months (month numbers for selected year)
        selected_months = self.request.GET.getlist('months')
        if selected_months:
            try:
                selected_year_qs = int(self.request.GET.get('year') or datetime.datetime.now().year)
            except (TypeError, ValueError):
                selected_year_qs = datetime.datetime.now().year

            month_queries = Q()
            for month_str in selected_months:
                try:
                    month = int(month_str)
                    month_queries |= Q(
                        transaction_date__year=selected_year_qs,
                        transaction_date__month=month
                    )
                except (ValueError, TypeError):
                    pass
            if month_queries:
                queryset = queryset.filter(month_queries)

        # Search filter (on description only, incomes typically lack merchant)
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(description__icontains=search_query)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Base queryset possibly filtered by months already
        user_transactions = self.get_queryset()

        # Selected months in context
        selected_months = self.request.GET.getlist('months')

        # Totals
        context.update({
            'total_count': user_transactions.count(),
            'total_amount': user_transactions.filter(status="categorized").aggregate(total=Sum('amount'))['total'] or 0,
            'selected_months': selected_months,
            'search_query': self.request.GET.get('search', ''),
        })

        # Amount filter context
        context['selected_amount'] = self.request.GET.get('amount', '')
        context['selected_amount_operator'] = self.request.GET.get('amount_operator', 'eq')

        return context

class EditTransactionCategory(View):

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        # 1. Get and validate data
        transaction_id = request.POST.get('transaction_id', '')
        new_category_id = request.POST.get('category_id', '')

        # Ensure IDs are provided
        if not transaction_id or not new_category_id:
            return JsonResponse({'success': False, 'error': 'Missing transaction or category ID.'}, status=400)

        # 2. Retrieve objects (using get_object_or_404 is good for immediate 404 response)
        try:
            expense = get_object_or_404(Transaction, id=transaction_id)
            new_category = get_object_or_404(Category, id=new_category_id)
        except Exception as e:
            # Catch exceptions if IDs are malformed or missing
            return JsonResponse({'success': False, 'error': f'Invalid object ID: {e}'}, status=404)

        # 3. Authorization Check (CRUCIAL for security)
        # Assuming Transaction has a 'user' field
        if expense.user != request.user:
            # Return 403 Forbidden if the user doesn't own the transaction
            return JsonResponse({'success': False, 'error': 'You do not have permission to edit this transaction.'},
                                status=403)
        # 4. Update and Save
        expense.category = new_category
        expense.modified_by_user = True
        expense.save()  # ⬅️ MUST CALL .save() to write the change to the database

        # 5. Return success response (JSON for AJAX)
        return JsonResponse({
            'success': True,
            'message': 'Category updated successfully.',
            'transaction_id': expense.id,
            'new_category_name': new_category.name,  # Return updated data for client-side update
            'new_category_id': new_category.id
        }, status=200)  # Use 200 OK for a successful update


class TransactionByCsvUploadAndMerchant(View):
    def get(self, request: HttpRequest, **kwargs):
        merchant_id = request.GET.get('merchant_id', None)
        csv_upload_id = request.GET.get('csv_upload_id', None)
        csv_upload = get_object_or_404(CsvUpload, user=request.user, id=csv_upload_id)
        if not merchant_id or merchant_id.lower() == 'none':
            merchant = None
            transactions_qs = Transaction.objects.filter(user=request.user, csv_upload=csv_upload, merchant__isnull=True).order_by('-transaction_date')
        else:
            # Security: Ensure objects belong to the requesting user
            merchant = get_object_or_404(Merchant, user=request.user, id=merchant_id)
            # Filter transactions
            transactions_qs = Transaction.objects.filter(
                merchant=merchant,
                csv_upload=csv_upload,
                user=request.user
            ).order_by('-transaction_date')

        # Get date range for the UI
        first_date = None
        last_date = None
        if transactions_qs.exists():
            first_date = transactions_qs.last().transaction_date
            last_date = transactions_qs.first().transaction_date

        # Convert QuerySet to list of dicts for JSON serialization
        # Add or remove fields here based on what you want to show in the UI
        transactions_data = list(transactions_qs.values(
            'id',
            'transaction_date',
            'amount',
            'description'
        ))

        return JsonResponse(
            data={
                'transactions': transactions_data,
                'first_date': first_date,
                'last_date': last_date,
                'merchant_name': merchant.name if merchant else None
            },
            safe=False
        )