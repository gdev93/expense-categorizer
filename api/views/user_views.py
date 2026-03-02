from dataclasses import dataclass, asdict, field
import json
from datetime import datetime
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views import View
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.db.models import Count
from typing import List
from asgiref.sync import sync_to_async
from api.tasks import delete_user_data
from api.models import Transaction, Category, Rule, UploadFile
from api.views.transactions.export_views import generate_csv_sync

@dataclass
class UserDeleteContextData:
    """Context data for user delete confirmation view"""
    user_email: str

    def to_context(self) -> dict:
        return asdict(self)

@dataclass
class UserDetailContextData:
    """Context data for user profile detail view"""
    username: str
    email: str
    date_joined: str
    subscription_type: str

    def to_context(self) -> dict:
        return asdict(self)

class UserDetailView(View):
    """View to show user profile and data summary"""
    template_name = 'api/user/detail.html'

    def get(self, request: HttpRequest) -> HttpResponse:
        user = request.user
        
        # Get profile info
        profile = getattr(user, 'profile', None)
        subscription_type = profile.subscription_type if profile else 'N/A'
        
        context = UserDetailContextData(
            username=user.username,
            email=user.email,
            date_joined=user.date_joined.strftime("%d/%m/%Y"),
            subscription_type=subscription_type
        )
        return render(request, self.template_name, context.to_context())

class UserDataExportView(View):
    """View to export all user data in CSV format"""

    def get(self, request: HttpRequest) -> HttpResponse:
        user = request.user

        # Collect transactions for all time
        queryset = Transaction.objects.filter(user=user).select_related("category", "upload_file", "merchant").order_by("-transaction_date")

        # Exporter Layer: Use the sync generator to stream the response
        response = StreamingHttpResponse(
            generate_csv_sync(queryset.iterator()),
            content_type='text/csv'
        )

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"pecuniam_export_{user.username}_{timestamp}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response

class UserDeleteView(View):
    """View to handle user data deletion request"""
    template_name = 'api/user/delete_confirm.html'
    success_url = reverse_lazy('entry_point')

    def get(self, request: HttpRequest) -> HttpResponse:
        context = UserDeleteContextData(
            user_email=request.user.email
        )
        return render(request, self.template_name, context.to_context())

    def post(self, request: HttpRequest) -> HttpResponse:
        user_id = request.user.id
        # Trigger the celery task
        delete_user_data.delay(user_id)
        
        # Log the user out since the user object will be deleted
        logout(request)
        
        messages.success(
            request, 
            "I tuoi dati verranno cancellati con successo."
        )
        return redirect(self.success_url)
