from django.http import JsonResponse, HttpRequest
from django.views import View
from api.models import Merchant
from processors.similarity_matcher import SimilarityMatcher

class CategoryFromMerchant(View, SimilarityMatcher):

    def get(self, request:HttpRequest, *args, **kwargs):
        merchant_id = request.GET.get('merchant_id')
        if not merchant_id:
            return JsonResponse({'category_id': None, 'category_name': None})

        try:
            merchant = Merchant.objects.get(id=merchant_id, user=request.user)
            category = self.find_most_frequent_category_for_merchant(merchant)
            if category:
                return JsonResponse({'category_id': category.id, 'category_name': category.name})
        except Merchant.DoesNotExist:
            pass

        return JsonResponse({'category_id': None, 'category_name': None})
