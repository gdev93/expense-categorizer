from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from api.models import Profile

class OnboardingStepView(LoginRequiredMixin, View):
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
