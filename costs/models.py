from django.contrib.auth.models import User
from django.db import models

from api.models import UploadFile


class CostConfiguration(models.Model):
    llm_model = models.CharField(max_length=100, unique=True, help_text="e.g., gemini-2.5-flash-lite")
    input_token_price_per_million = models.DecimalField(max_digits=10, decimal_places=4, help_text="Price in USD for 1 million input tokens")
    output_token_price_per_million = models.DecimalField(max_digits=10, decimal_places=4, help_text="Price in USD for 1 million output tokens")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.llm_model} (Active: {self.is_active})"

class ApiUsageLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_usage_logs')
    upload_file = models.ForeignKey(UploadFile, on_delete=models.SET_NULL, null=True, blank=True, related_name='api_usage_logs')
    number_of_transactions = models.IntegerField(default=0)
    cost_configuration = models.ForeignKey(CostConfiguration, on_delete=models.SET_NULL, null=True, blank=True)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    computed_cost = models.DecimalField(max_digits=12, decimal_places=6, default=0.0)
    input_cost = models.DecimalField(max_digits=12, decimal_places=6, default=0.0)
    output_cost = models.DecimalField(max_digits=12, decimal_places=6, default=0.0)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.timestamp} - {self.total_tokens} tokens"


class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    subscription_type = models.CharField(max_length=50, default='free_trial')
    end_timestamp = models.DateTimeField(null=False)