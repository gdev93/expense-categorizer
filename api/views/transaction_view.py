# views.py (add to your existing views file)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction as db_transaction
from django.db.models import Q  # Import Q for complex lookups
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View
from django.views.generic import ListView
from django.views.generic import UpdateView

from api.models import Transaction, Category, Rule


# views.py

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

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.filter(
            Q(user=self.request.user) | Q(is_default=True)
        ).distinct()
        return context

    def form_valid(self, form):
        """
        Customizes form validation to handle new category creation,
        set the modified_by_user flag, and most importantly,
        **return the rendered template instead of a redirect.**
        """
        new_category_name = self.request.POST.get('new_category_name', '').strip()

        with db_transaction.atomic():
            if new_category_name:
                new_category, created = Category.objects.get_or_create(
                    name=new_category_name,
                    user=self.request.user,  # Assigns the new category to the current user
                    defaults={'is_default': False}
                )
                form.instance.category = new_category

            form.instance.modified_by_user = True

            self.object = form.save()

        return self.render_to_response(self.get_context_data(form=form))



class TransactionListView(LoginRequiredMixin, ListView):
    """Display list of transactions with filtering and pagination"""
    model = Transaction
    template_name = 'transactions/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 50

    def get_queryset(self):
        """Filter transactions based on user and query parameters"""
        queryset = Transaction.objects.filter(
            user=self.request.user,
            merchant_id__isnull=False  # Filtra per escludere i valori NULL
        ).select_related('category', 'merchant').order_by('-transaction_date', '-created_at')
        # Filter by category
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        # Search filter
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(merchant_raw_name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        return queryset

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)

        # Get all categories for filter dropdown
        context['categories'] = list(Category.objects.filter(
            Q(user=self.request.user) | Q(user__isnull=True)
        ).order_by('name').values('id','name'))

        # Get filter values
        context['selected_category'] = self.request.GET.get('category', '')
        context['selected_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('search', '')

        # Calculate summary statistics
        user_transactions = Transaction.objects.filter(user=self.request.user)
        context['total_count'] = user_transactions.count()
        context['total_amount'] = user_transactions.aggregate(
            total=Sum('amount')
        )['total'] or 0
        context['category_count'] = user_transactions.values('category').distinct().count()
        context['user_rule']=Rule.objects.filter(user=self.request.user,is_active=True).order_by('priority').values_list('text_content', flat=True).first()

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
            transaction = get_object_or_404(Transaction, id=transaction_id)
            new_category = get_object_or_404(Category, id=new_category_id)
        except Exception as e:
            # Catch exceptions if IDs are malformed or missing
            return JsonResponse({'success': False, 'error': f'Invalid object ID: {e}'}, status=404)

        # 3. Authorization Check (CRUCIAL for security)
        # Assuming Transaction has a 'user' field
        if transaction.user != request.user:
            # Return 403 Forbidden if the user doesn't own the transaction
            return JsonResponse({'success': False, 'error': 'You do not have permission to edit this transaction.'},
                                status=403)

        # 4. Update and Save
        transaction.category = new_category
        transaction.save()  # ⬅️ MUST CALL .save() to write the change to the database

        # 5. Return success response (JSON for AJAX)
        return JsonResponse({
            'success': True,
            'message': 'Category updated successfully.',
            'transaction_id': transaction.id,
            'new_category_name': new_category.name,  # Return updated data for client-side update
            'new_category_id': new_category.id
        }, status=200)  # Use 200 OK for a successful update