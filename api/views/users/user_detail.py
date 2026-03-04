from dataclasses import dataclass, asdict
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.views import View

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
