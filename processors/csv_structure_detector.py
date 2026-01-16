import logging
from math import floor
from django.contrib.auth.models import User
from agent.agent import ExpenseCategorizerAgent, AgentTransactionUpload
from api.models import Transaction, CsvUpload
from costs.services import CostService

logger = logging.getLogger(__name__)

class CsvStructureDetector:
    def __init__(self, user: User, agent: ExpenseCategorizerAgent, min_threshold: int, sample_size_percentage: float):
        self.user = user
        self.agent = agent
        self.min_threshold = min_threshold
        self.sample_size_percentage = sample_size_percentage

    def setup_csv_upload_structure(self, current_data: list[Transaction], csv_upload: CsvUpload) -> CsvUpload:
        if csv_upload.description_column_name and csv_upload.date_column_name and (csv_upload.income_amount_column_name or csv_upload.expense_amount_column_name):
            return csv_upload

        csv_upload_same_structure = None
        all_csv_uploads = list(CsvUpload.objects.filter(user=self.user).exclude(id=csv_upload.id))
        for csv_upload_candidate in all_csv_uploads:
            first_transaction_candidate = Transaction.objects.filter(user=self.user, csv_upload=csv_upload_candidate,
                                                                     original_amount__isnull=False,
                                                                     category__isnull=False).first()
            if not first_transaction_candidate:
                continue
            first_transaction_raw_data = first_transaction_candidate.raw_data
            first_transaction_raw_data_keys = set(first_transaction_raw_data.keys())
            new_transaction_raw_data_keys = set(current_data[0].raw_data.keys())
            # the idea is to check that each element in the set in the other set
            if first_transaction_raw_data_keys == new_transaction_raw_data_keys:
                csv_upload_same_structure = csv_upload_candidate
                break
        
        if not csv_upload_same_structure:
            transaction_sample_size = min(len(current_data), max(self.min_threshold, floor(len(current_data) * self.sample_size_percentage)))
            result_from_agent, response = self.agent.detect_csv_structure(
                [AgentTransactionUpload(transaction_id=tx.id, raw_text=tx.raw_data) for tx in
                 current_data[:transaction_sample_size]])
            
            if response:
                CostService.log_api_usage(
                    user=self.user,
                    llm_model=response.model_name,
                    input_tokens=response.prompt_tokens,
                    output_tokens=response.candidate_tokens,
                    csv_upload=csv_upload
                )

            description_column_name = result_from_agent.description_field
            notes = result_from_agent.notes
            merchant_column_name = result_from_agent.merchant_field
            date_column_name = result_from_agent.transaction_date_field
            income_amount_column_name = result_from_agent.income_amount_field or result_from_agent.expense_amount_field
            expense_amount_column_name = result_from_agent.expense_amount_field or result_from_agent.income_amount_field
            operation_type_column_name = result_from_agent.operation_type_field
        else:
            description_column_name = csv_upload_same_structure.description_column_name
            notes = csv_upload_same_structure.notes
            merchant_column_name = csv_upload_same_structure.merchant_column_name
            date_column_name = csv_upload_same_structure.date_column_name
            income_amount_column_name = csv_upload_same_structure.income_amount_column_name
            expense_amount_column_name = csv_upload_same_structure.expense_amount_column_name
            operation_type_column_name = csv_upload_same_structure.operation_type_column_name

        csv_upload.description_column_name = description_column_name
        csv_upload.merchant_column_name = merchant_column_name
        csv_upload.date_column_name = date_column_name
        csv_upload.income_amount_column_name = income_amount_column_name
        csv_upload.expense_amount_column_name = expense_amount_column_name
        csv_upload.operation_type_column_name = operation_type_column_name
        csv_upload.notes = notes
        csv_upload.save()
        return csv_upload
