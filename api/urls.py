"""
URL configuration for server project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path
from django.views.generic import RedirectView

from api.entry_point_views import login_form, authenticate_user, register_form, create_user
from api.views.category_view import CategoryUpdateView
from api.views.csv_upload_view import CsvUploadView, CsvUploadDelete, CsvProcessView
from api.views.rule_view import RuleDefineView
from api.views.transaction_view import TransactionListView, EditTransactionCategory, TransactionDetailUpdateView

urlpatterns = [
    path("accounts/", login_form, name="login_form"),
    path("accounts/authenticate/", authenticate_user, name="authenticate_user"),
    path('accounts/register/', register_form, name='register_form'),
    path('accounts/create/', create_user, name='create_user'),
    path('transactions/upload/', CsvUploadView.as_view(), name='transactions_upload'),
    path('transactions/upload/process', CsvProcessView.as_view(), name='transactions_process'),
    path('transactions/upload/<int:pk>/delete/', CsvUploadDelete.as_view(), name='transactions_upload_delete'),
    path('transactions/', TransactionListView.as_view(), name='transaction_list'),
    path('transactions/<int:pk>/', TransactionDetailUpdateView.as_view(), name='transaction_detail'),
    path('transactions/rules/', RuleDefineView.as_view(), name='define_rule'),
    path('transactions/category/', CategoryUpdateView.as_view(), name='update_category'),
    path('transactions/category/edit', EditTransactionCategory.as_view(), name='update_transaction_category'),
    path("", RedirectView.as_view(url="transactions/"), name="entry_point")
]
