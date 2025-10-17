# views.py (add to your existing views file)
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum

from api.models import Transaction, Category


class TransactionListView(LoginRequiredMixin, ListView):
    """Display list of transactions with filtering and pagination"""
    model = Transaction
    template_name = 'transactions/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 50

    def get_queryset(self):
        """Filter transactions based on user and query parameters"""
        queryset = Transaction.objects.filter(
            user=self.request.user
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
        context['categories'] = Category.objects.filter(
            Q(user=self.request.user) | Q(user__isnull=True)
        ).order_by('name')

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

        return context