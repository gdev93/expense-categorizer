import os
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import UpdateView

from api.models import Transaction, Category, Merchant

pre_check_confidence_threshold = os.environ.get('PRE_CHECK_CONFIDENCE_THRESHOLD', 0.8)

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
        messages.success(request, "Spesa eliminata con successo.")

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

        if self.request.POST.get('apply_to_all') == 'true' and self.object.merchant:
            # Update previous transactions with the same merchant and same user
            updated_count = Transaction.objects.filter(
                user=self.request.user,
                merchant=self.object.merchant,
            ).exclude(
                pk=self.object.pk
            ).update(
                category=self.object.category,
                modified_by_user=True,
                status='categorized'
            )
            if updated_count > 0:
                messages.info(self.request, f"Aggiornate questa e altre {updated_count} transazioni precedenti per questo esercente.")
        else:
            messages.success(self.request, "Spesa aggiornata con successo.")

        # Advance onboarding if at step 4
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.onboarding_step < 5:
            profile.onboarding_step = 5
            profile.save()

        return redirect(reverse('transaction_detail', kwargs={'pk': self.object.pk}))

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

        # Advance onboarding if at step 4
        profile = getattr(request.user, 'profile', None)
        if profile and profile.onboarding_step < 5:
            profile.onboarding_step = 5
            profile.save()

        # 5. Return success response (JSON for AJAX)
        return JsonResponse({
            'success': True,
            'message': 'Category updated successfully.',
            'transaction_id': expense.id,
            'new_category_name': new_category.name,  # Return updated data for client-side update
            'new_category_id': new_category.id
        }, status=200)  # Use 200 OK for a successful update
