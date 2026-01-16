import datetime
import logging

from django import forms
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import BadRequest
from django.core.paginator import Paginator
from django.db.models import Count, Sum, DecimalField, Q
from django.db.models.functions import Coalesce
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from api.models import Category, Transaction, Rule

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

    def _get_year_and_months(self):
        try:
            get_year = self.request.GET.get('year')
            if get_year:
                selected_year = int(get_year)
            else:
                # Fallback logic consistent with other views
                last_t = Transaction.objects.filter(user=self.request.user, status='categorized').order_by('-transaction_date').first()
                selected_year = last_t.transaction_date.year if last_t else datetime.datetime.now().year
        except (TypeError, ValueError, AttributeError):
            if self.request.GET.get('year'):
                raise BadRequest("Invalid year format.")
            selected_year = datetime.datetime.now().year

        selected_months = self.request.GET.getlist('months')
        # Also support single 'month' parameter for backward compatibility or simple links
        single_month = self.request.GET.get('month')
        if single_month and single_month not in selected_months:
            selected_months.append(single_month)

        processed_months = []
        for m in selected_months:
            try:
                processed_months.append(int(m))
            except (TypeError, ValueError):
                raise BadRequest(f"Invalid month format: {m}")

        return selected_year, processed_months

    def get_queryset(self):
        """
        Returns categories belonging to the logged-in user, annotated with:
        1. The count of associated transactions (transaction_count).
        2. The total amount of associated transactions (transaction_amount).
        """

        # 1. Filter: Start with categories belonging to the current user
        user_categories = self.model.objects.filter(user=self.request.user)
        selected_category_ids = self.request.GET.getlist('categories')
        if any(selected_category_ids):
            user_categories = user_categories.filter(id__in=selected_category_ids)

        selected_year, selected_months = self._get_year_and_months()

        filter_q = Q(transactions__transaction_date__year=selected_year)
        if selected_months:
            filter_q &= Q(transactions__transaction_date__month__in=selected_months)

        enriched_categories = user_categories.annotate(
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass the form to the template so it can be rendered in the "New Category" card
        context['form'] = CategoryForm()

        # --- LOGIC FOR SUMMARY CARD ---
        # Get the queryset used by the list
        categories = context['categories']

        context['total'] = sum([category.transaction_amount for category in categories]) if categories else 0
        selected_year, selected_months = self._get_year_and_months()
        context['all_categories'] = Category.objects.filter(user=self.request.user).order_by('name')
        context['selected_categories'] = self.request.GET.getlist('categories')
        context['year'] = selected_year
        context['selected_months'] = [str(m) for m in selected_months]
        return context



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
        # Automatically assign the current user to the category
        form.instance.user = self.request.user
        return super().form_valid(form)

    def form_invalid(self, form):
        # If invalid, we must re-render the list context so the page doesn't break
        return self.render_to_response(self.get_context_data(form=form))




class CategoryDetailView(DetailView):
    """
    A view to display the details of a specific Category,
    and list all associated transactions with pagination.
    """
    model = Category
    template_name = 'categories/category-detail.html'

    def get_queryset(self):
        # Security: Only allow the user to view their own categories
        return Category.objects.filter(user=self.request.user)

    def _get_filters(self):
        search_query = self.request.GET.get('search', '')

        try:
            get_year = self.request.GET.get('year')
            if get_year:
                selected_year = int(get_year)
            else:
                # Fallback logic consistent with other views
                last_t = Transaction.objects.filter(user=self.request.user, status='categorized').order_by('-transaction_date').first()
                selected_year = last_t.transaction_date.year if last_t else datetime.datetime.now().year
        except (TypeError, ValueError, AttributeError):
            if self.request.GET.get('year'):
                raise BadRequest("Invalid year format.")
            selected_year = datetime.datetime.now().year

        selected_months = self.request.GET.getlist('months')
        # Also support single 'month' parameter
        single_month = self.request.GET.get('month')
        if single_month and single_month not in selected_months:
            selected_months.append(single_month)

        processed_months = []
        for m in selected_months:
            try:
                processed_months.append(int(m))
            except (TypeError, ValueError):
                raise BadRequest(f"Invalid month format: {m}")

        return search_query, selected_year, processed_months

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        category = self.object
        search_query, selected_year, selected_months = self._get_filters()

        # 1. Build filters for SUMMARY (matching categories.html logic)
        summary_filter_q = Q(transactions__transaction_date__year=selected_year)
        if selected_months:
            summary_filter_q &= Q(transactions__transaction_date__month__in=selected_months)

        # 2. Fetch Aggregated Summary Data for the Summary Card
        summary = Category.objects.filter(id=category.pk).annotate(
            transaction_count=Count('transactions', filter=summary_filter_q),
            transaction_amount=Coalesce(
                Sum('transactions__amount', filter=summary_filter_q),
                0.0,
                output_field=DecimalField()
            )
        ).first()

        context['category_summary'] = summary

        # 3. Fetch and Paginate Associated Transactions (with search)
        t_filter_q = Q(user=self.request.user, category=category)
        if selected_year:
            t_filter_q &= Q(transaction_date__year=selected_year)
        if selected_months:
            t_filter_q &= Q(transaction_date__month__in=selected_months)
        if search_query:
            t_filter_q &= (
                Q(merchant__name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        transaction_list = Transaction.objects.filter(t_filter_q).order_by('-transaction_date', '-created_at')

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