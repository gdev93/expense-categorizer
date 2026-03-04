from dataclasses import dataclass, asdict
from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views import View
from django.http import HttpRequest, HttpResponse
from api.tasks import delete_user_data

@dataclass
class UserDeleteContextData:
    """Context data for user delete confirmation view"""
    user_email: str

    def to_context(self) -> dict:
        return asdict(self)

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
