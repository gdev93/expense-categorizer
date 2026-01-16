from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_not_required

@login_not_required
def trigger_403(request):
    raise PermissionDenied

@login_not_required
def trigger_500(request):
    raise Exception("Test server error")
