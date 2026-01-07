from decimal import Decimal
from django.db.models import Sum
from .models import ApiUsageLog, CostConfiguration

class CostService:
    @staticmethod
    def log_api_usage(user, model_name, input_tokens, output_tokens, csv_upload=None):
        """
        Logs API usage and computes cost based on current configuration.
        """
        # Try to find an active configuration for this model
        config = CostConfiguration.objects.filter(model_name=model_name, is_active=True).first()
        
        computed_cost = Decimal('0.0')
        if config:
            input_cost = (Decimal(str(input_tokens)) * config.input_token_price_per_million) / Decimal('1000000')
            output_cost = (Decimal(str(output_tokens)) * config.output_token_price_per_million) / Decimal('1000000')
            computed_cost = input_cost + output_cost
        
        usage_log = ApiUsageLog.objects.create(
            user=user,
            csv_upload=csv_upload,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            computed_cost=computed_cost
        )
        return usage_log

    @staticmethod
    def get_user_total_cost(user):
        """
        Returns total cost for a specific user.
        """
        result = ApiUsageLog.objects.filter(user=user).aggregate(total=Sum('computed_cost'))
        return result['total'] or Decimal('0.0')

    @staticmethod
    def get_csv_upload_cost(csv_upload):
        """
        Returns total cost for a specific CSV upload.
        """
        result = ApiUsageLog.objects.filter(csv_upload=csv_upload).aggregate(total=Sum('computed_cost'))
        return result['total'] or Decimal('0.0')
