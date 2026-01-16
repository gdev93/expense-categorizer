from django.shortcuts import render
from django.contrib.auth.decorators import login_not_required

def error_400(request, exception):
    return render(request, 'errors/400.html', status=400)

def error_403(request, exception):
    return render(request, 'errors/403.html', status=403)

def error_404(request, exception):
    return render(request, 'errors/404.html', status=404)

def error_500(request):
    return render(request, 'errors/500.html', status=500)

def csrf_failure(request, reason=""):
    return render(request, 'errors/csrf_failure.html', status=403)
