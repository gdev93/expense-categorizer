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
from processors.similarity_matcher import update_merchant_ema

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
        'description',
        'category'
    ]

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

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
        context["is_update"] = True
        return context

    @transaction.atomic
    def form_valid(self, form):
        """
        Customizes form validation to handle new category creation,
        set the modified_by_user flag, and most importantly,
        **return the rendered template instead of a redirect.**
        """
        category_name = self.request.POST.get('category_name', '').strip()
        new_category = None

        if category_name:
            new_category, created = Category.objects.get_or_create(
                name=category_name,
                user=self.request.user,  # Assigns the new category to the current user
                defaults={'is_default': False}
            )

        merchant_name = self.request.POST.get('merchant_name', '').strip()

        if merchant_name:
            merchant_db = Merchant.objects.filter(name=merchant_name, user=self.request.user).first()
            if not merchant_db:
                merchant_db = Merchant.objects.create(name=merchant_name, user=self.request.user)
            form.instance.merchant = merchant_db

        form.instance.category = new_category
        form.instance.modified_by_user = True
        form.instance.status = 'categorized'
        self.object = form.save()

        # Update Merchant EMA if merchant and embedding are available
        if self.object.merchant and self.object.embedding and self.object.upload_file and self.object.upload_file.file_structure_metadata:
            update_merchant_ema(
                merchant=self.object.merchant,
                file_structure_metadata=self.object.upload_file.file_structure_metadata,
                embedding=self.object.embedding
            )

        # Apply to all transactions of the same merchant if requested
        apply_to_all = self.request.POST.get('apply_to_all') in ['on', 'true']
        if apply_to_all and self.object.merchant:
            count = Transaction.objects.filter(
                user=self.request.user,
                merchant=self.object.merchant
            ).update(
                category=new_category,
                status='categorized',
                modified_by_user=True
            )
            
            if count > 1:
                messages.success(self.request, f"Questa spesa e altre {count - 1} transazioni di '{self.object.merchant.name}' sono state aggiornate.")
            else:
                messages.success(self.request, "Spesa aggiornata con successo.")
        else:
            messages.success(self.request, "Spesa aggiornata con successo.")


        # Advance onboarding if at step 4
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.onboarding_step < 5:
            profile.onboarding_step = 5
            profile.save()

        return redirect(reverse('transaction_detail', kwargs={'pk': self.object.pk}))

    def form_invalid(self, form):
        """Handle invalid form submission by adding an error message."""
        messages.error(self.request, "Errore durante l'aggiornamento della spesa. Controlla i dati inseriti.")
        return super().form_invalid(form)

class EditTransactionCategory(View):
    
    @transaction.atomic
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
        expense.status = 'categorized'
        expense.save()  # ⬅️ MUST CALL .save() to write the change to the database

        # Advance onboarding if at step 4
        profile = getattr(request.user, 'profile', None)
        if profile and profile.onboarding_step < 5:
            profile.onboarding_step = 5
            profile.save()

        # 5. Return success response (JSON for AJAX)
        return JsonResponse({
            'success': True,
            'message': 'Categoria aggiornata con successo.',
            'transaction_id': expense.id,
            'new_category_name': new_category.name,  # Return updated data for client-side update
            'new_category_id': new_category.id
        }, status=200)  # Use 200 OK for a successful update
