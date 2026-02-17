from django.shortcuts import render

# Create your views here.
def index(request):
    user = request.user
    return render(
        request=request,
        template_name='main/index.html',
        context={'user_avatar': user.username[0].capitalize(),
                 'user_name': f"{user.first_name} {user.last_name}",
                 'main_content': 'users/users.html'
                 }

    )