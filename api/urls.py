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
from django.urls import path, include
from django.views.generic import RedirectView

from api.views.category_view import CategoryCreateView, CategoryListView, CategoryDetailView, CategoryDeleteView, \
    CategoryUpdateView, CategoryExportView, CategorySearchView, CategoryFromMerchant
from api.views.merchant_views import MerchantSearchView
from api.views.transactions.create_views import TransactionCreateView
from api.views.transactions.export_views import TransactionExportView
from api.views.transactions.list_views import TransactionListView
from api.views.transactions.query_views import TransactionByMerchant
from api.views.transactions.update_views import EditTransactionCategory, TransactionDetailUpdateView
from api.views.upload_file_view import UploadFileView, UploadFileDelete, UploadProgressView, \
    UploadFileCheckView
from api.views.onboarding_views import OnboardingStepView
from api.views.error_views import trigger_403, trigger_500, trigger_502, trigger_503

urlpatterns = [
    path('onboarding/step/', OnboardingStepView.as_view(), name='onboarding_step'),
    path('onboarding/update-step/', OnboardingStepView.as_view(), name='update_onboarding_step'),
    path('test-403/', trigger_403, name='test_403'),
    path('test-500/', trigger_500, name='test_500'),
    path('test-502/', trigger_502, name='test_502'),
    path('test-503/', trigger_503, name='test_503'),
    path("accounts/", include('allauth.urls')),
    path('transactions/upload/', UploadFileView.as_view(), name='transactions_upload'),
    path('transactions/upload/progress/', UploadProgressView.as_view(), name='transactions_progress'),
    path('transactions/upload/check', UploadFileCheckView.as_view(), name='transactions_upload_check'),
    path('transactions/upload/<int:pk>/delete/', UploadFileDelete.as_view(), name='transactions_upload_delete'),
    path('transactions/upload/<int:upload_file_id>/', TransactionListView.as_view(), name='transactions_upload_detail'),
    path('transactions/', TransactionListView.as_view(), name='transaction_list'),
    path('transactions/create/', TransactionCreateView.as_view(), name='transaction_create'),
    path('transactions/by_merchant/', TransactionByMerchant.as_view(),
         name='transactions_by_merchant'),
    path('transactions/export/', TransactionExportView.as_view(), name='transaction_export'),
    path('transactions/<int:pk>/', TransactionDetailUpdateView.as_view(), name='transaction_detail'),
    path('transactions/category/edit', EditTransactionCategory.as_view(), name='update_transaction_category'),
    path('categories/create/', CategoryCreateView.as_view(), name='create_category'),
    path('categories/', CategoryListView.as_view(), name='category_list'),
    path('categories/export/', CategoryExportView.as_view(), name='category_export'),
    path('categories/<int:pk>/', CategoryDetailView.as_view(), name='category_detail'),
    path('categories/<int:pk>/edit/', CategoryUpdateView.as_view(), name='category_update'),
    path('categories/<int:pk>/delete/', CategoryDeleteView.as_view(), name='category_delete'),
    path('merchants/search',MerchantSearchView.as_view(),name='merchant_search'),
    path('categories/from-merchant/', CategoryFromMerchant.as_view(), name='category_from_merchant'),
    path('categories/search', CategorySearchView.as_view(), name='category_search'),
    path("", RedirectView.as_view(url="transactions/"), name="entry_point"),
]
