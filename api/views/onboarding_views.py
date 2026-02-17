from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from api.models import Profile

class OnboardingStepView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        step = request.GET.get('step')
        if not step:
            # Get current step from profile
            profile = getattr(request.user, 'profile', None)
            step = profile.onboarding_step if profile else 1
        
        try:
            step = int(step)
        except (ValueError, TypeError):
            step = 1

        context = {
            'step': step,
            'total_steps': 4,
        }
        
        # Define step specific data
        steps_data = {
            1: {
                'title': 'Crea le tue Categorie',
                'description': 'Il primo passo è creare le categorie di spesa (es. Spesa, Affitto, Trasporti) con una breve descrizione.',
                'mock_type': 'categories'
            },
            2: {
                'title': 'Carica i tuoi Dati',
                'description': 'Ora carica il file CSV delle tue transazioni bancarie per iniziare a categorizzarle.',
                'mock_type': 'upload'
            },
            3: {
                'title': 'Usa i Filtri',
                'description': 'Ottimo! Ora puoi usare i filtri per analizzare le tue spese per periodo, categoria o esercente.',
                'mock_type': 'filters'
            },
            4: {
                'title': 'Personalizza le tue Spese',
                'description': 'Puoi cambiare la categoria di una spesa cliccando sulla "pillola" colorata, oppure cliccare sulla riga per vedere i dettagli.',
                'mock_type': 'modify'
            }
        }
        
        if step in steps_data:
            context.update(steps_data[step])
            
        return render(request, 'components/onboarding_step.html', context)

    def post(self, request, *args, **kwargs):
        step = request.POST.get('step')
        if step:
            try:
                step_int = int(step)
                profile = getattr(request.user, 'profile', None)
                if not profile:
                    return JsonResponse({'status': 'error', 'message': 'Profile not found'}, status=404)
                # Allow setting any valid step (1: Categories, 2: Upload, 3: Filters, 4: Modify, 5: Completed)
                if 1 <= step_int <= 5:
                    profile.onboarding_step = step_int
                    profile.save()
                    return JsonResponse({'status': 'success', 'new_step': profile.onboarding_step})
            except ValueError:
                pass
        return JsonResponse({'status': 'error', 'message': 'Invalid step'}, status=400)
