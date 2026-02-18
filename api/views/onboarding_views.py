from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from api.models import Profile, OnboardingStep

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

        total_steps = OnboardingStep.objects.count()
        context = {
            'step': step,
            'total_steps': total_steps,
        }
        
        # Get step specific data from database
        onboarding_step = OnboardingStep.objects.filter(step_number=step).first()
        if onboarding_step:
            context.update({
                'title': onboarding_step.title,
                'description': onboarding_step.description,
                'mock_type': onboarding_step.mock_type,
            })
            
        return render(request, 'components/onboarding_step.html', context)

    def post(self, request, *args, **kwargs):
        step = request.POST.get('step')
        if step:
            try:
                step_int = int(step)
                profile = getattr(request.user, 'profile', None)
                if not profile:
                    return JsonResponse({'status': 'error', 'message': 'Profile not found'}, status=404)
                
                total_steps = OnboardingStep.objects.count()
                # Allow setting any valid step or the next one (Completed)
                if 1 <= step_int <= total_steps + 1:
                    profile.onboarding_step = step_int
                    profile.save()
                    return JsonResponse({'status': 'success', 'new_step': profile.onboarding_step})
            except ValueError:
                pass
        return JsonResponse({'status': 'error', 'message': 'Invalid step'}, status=400)
