from django.contrib import messages
from django.db.models import Min
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import DeleteView

from api.models import Category, Transaction, Rule
from api.services.data_refresh.data_refresh_service import DataRefreshService

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
        affected_transactions = Transaction.objects.filter(category=category_to_delete)
        aggregation = affected_transactions.aggregate(Min('transaction_date'))
        start_date = aggregation['transaction_date__min']

        affected_transactions.update(category=replacement_category)
        Rule.objects.filter(category=category_to_delete).update(category=replacement_category)

        if start_date:
            DataRefreshService.trigger_recomputation(self.request.user, start_date)

        messages.success(self.request,
                         f"Category '{category_to_delete.name}' deleted. All transactions have been moved to '{replacement_category.name}'.")
        return super().form_valid(form)
