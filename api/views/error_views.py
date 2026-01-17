from django.shortcuts import render
from django.contrib.auth.decorators import login_not_required
from django.urls import reverse

@login_not_required
def error_400(request, exception):
    context = {
        'error_code': 400,
        'error_title': 'Richiesta errata',
        'error_message': 'La richiesta non può essere soddisfatta a causa di errori di sintassi.'
    }
    return render(request, 'errors/error.html', context, status=400)

@login_not_required
def error_401(request, exception=None):
    context = {
        'error_code': 401,
        'error_title': 'Non autorizzato',
        'error_message': 'La tua sessione potrebbe essere scaduta o non hai effettuato l\'accesso.',
        'button_text': 'Vai al Login',
        'button_url': reverse('login_form')
    }
    return render(request, 'errors/error.html', context, status=401)

@login_not_required
def error_403(request, exception):
    if str(exception) == "401 Unauthorized":
        return error_401(request)
    context = {
        'error_code': 403,
        'error_title': 'Accesso negato',
        'error_message': 'Non hai i permessi necessari per visualizzare questa pagina.'
    }
    return render(request, 'errors/error.html', context, status=403)

@login_not_required
def error_404(request, exception):
    context = {
        'error_code': 404,
        'error_title': 'Pagina non trovata',
        'error_message': 'Spiacenti, la pagina che stai cercando non esiste o è stata spostata.'
    }
    return render(request, 'errors/error.html', context, status=404)

@login_not_required
def error_500(request):
    context = {
        'error_code': 500,
        'error_title': 'Errore interno del server',
        'error_message': 'Si è verificato un errore imprevisto. I nostri tecnici sono stati informati e stanno lavorando per risolvere il problema.'
    }
    return render(request, 'errors/error.html', context, status=500)

@login_not_required
def csrf_failure(request, reason=""):
    context = {
        'error_code': 403,
        'error_title': 'Verifica di sicurezza fallita',
        'error_message': 'La verifica del token CSRF è fallita. La tua sessione potrebbe essere scaduta o la richiesta potrebbe essere sospetta. Per favore, prova a ricaricare la pagina e riprova.'
    }
    return render(request, 'errors/error.html', context, status=403)

# Test views for real error testing
@login_not_required
def trigger_403(request):
    from django.core.exceptions import PermissionDenied
    raise PermissionDenied

@login_not_required
def trigger_500(request):
    raise Exception("Test 500 error")
