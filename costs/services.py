from decimal import Decimal
from django.db.models import Sum
from .models import ApiUsageLog, CostConfiguration

class CostService:
    @staticmethod
    def log_api_usage(user, llm_model, input_tokens, output_tokens, upload_file=None):
        """
        Logs API usage and computes cost based on current configuration.
        """
        # Try to find an active configuration for this model
        config = CostConfiguration.objects.filter(llm_model=llm_model, is_active=True).first()
        
        computed_cost = Decimal('0.0')
        input_cost = Decimal('0.0')
        output_cost = Decimal('0.0')
        final_earning = Decimal('0.0')

        if config:
            input_cost = (Decimal(str(input_tokens)) * config.input_token_price_per_million) / Decimal('1000000')
            output_cost = (Decimal(str(output_tokens)) * config.output_token_price_per_million) / Decimal('1000000')
            computed_cost = input_cost + output_cost
            final_earning = computed_cost * (Decimal('1') + (config.earning_multiplier_percentage / Decimal('100')))
        
        usage_log = ApiUsageLog.objects.create(
            user=user,
            upload_file=upload_file,
            cost_configuration=config,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            computed_cost=computed_cost,
            input_cost=input_cost,
            output_cost=output_cost,
            final_earning=final_earning
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
    def get_upload_file_cost(upload_file):
        """
        Returns total cost for a specific CSV upload.
        """
        result = ApiUsageLog.objects.filter(upload_file=upload_file).aggregate(total=Sum('computed_cost'))
        return result['total'] or Decimal('0.0')
