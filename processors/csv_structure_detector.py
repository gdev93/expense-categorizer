import logging
from math import floor
from django.contrib.auth.models import User
from agent.agent import ExpenseCategorizerAgent, AgentTransactionUpload
from api.models import Transaction, UploadFile
from costs.services import CostService

logger = logging.getLogger(__name__)


class CsvStructureDetector:
    def __init__(self, user: User, agent: ExpenseCategorizerAgent, min_threshold: int, sample_size_percentage: float):
        self.user = user
        self.agent = agent
        self.min_threshold = min_threshold
        self.sample_size_percentage = sample_size_percentage

    def setup_upload_file_structure(self, current_data: list[Transaction], upload_file: UploadFile) -> UploadFile:
        # Check if columns are already set
        if upload_file.description_column_name and upload_file.date_column_name and (
                upload_file.income_amount_column_name or upload_file.expense_amount_column_name):
            logger.info(f"UploadFile {upload_file.id} already has a defined structure. Skipping detection.")
            return upload_file

        upload_file_same_structure = None
        all_upload_files = list(UploadFile.objects.filter(user=self.user).exclude(id=upload_file.id))

        logger.debug(
            f"Checking {len(all_upload_files)} previous uploads for a matching structure for User {self.user.id}.")

        for upload_file_candidate in all_upload_files:
            first_transaction_candidate = Transaction.objects.filter(user=self.user, upload_file=upload_file_candidate,
                                                                     original_amount__isnull=False,
                                                                     category__isnull=False).first()
            if not first_transaction_candidate:
                continue

            first_transaction_raw_data = first_transaction_candidate.raw_data
            first_transaction_raw_data_keys = set(first_transaction_raw_data.keys())
            new_transaction_raw_data_keys = set(current_data[0].raw_data.keys())

            if first_transaction_raw_data_keys == new_transaction_raw_data_keys:
                logger.info(f"Matching structure found! Using schema from UploadFile {upload_file_candidate.id}.")
                upload_file_same_structure = upload_file_candidate
                break

        if not upload_file_same_structure:
            transaction_sample_size = min(len(current_data), max(self.min_threshold, floor(
                len(current_data) * self.sample_size_percentage)))

            logger.info(
                f"No matching structure found. Requesting Agent detection with a sample size of {transaction_sample_size}.")

            result_from_agent, response = self.agent.detect_csv_structure(
                [AgentTransactionUpload(transaction_id=tx.id, raw_text=tx.raw_data) for tx in
                 current_data[:transaction_sample_size]])

            if response:
                logger.debug(
                    f"Agent response received. Model: {response.model_name}, Prompt Tokens: {response.prompt_tokens}")
                CostService.log_api_usage(
                    user=self.user,
                    llm_model=response.model_name,
                    input_tokens=response.prompt_tokens,
                    output_tokens=response.candidate_tokens,
                    number_of_transactions=0,
                    upload_file=upload_file
                )

            description_column_name = result_from_agent.description_field
            notes = result_from_agent.notes
            merchant_column_name = result_from_agent.merchant_field
            date_column_name = result_from_agent.transaction_date_field
            income_amount_column_name = result_from_agent.income_amount_field or result_from_agent.expense_amount_field
            expense_amount_column_name = result_from_agent.expense_amount_field or result_from_agent.income_amount_field
            operation_type_column_name = result_from_agent.operation_type_field
        else:
            description_column_name = upload_file_same_structure.description_column_name
            notes = upload_file_same_structure.notes
            merchant_column_name = upload_file_same_structure.merchant_column_name
            date_column_name = upload_file_same_structure.date_column_name
            income_amount_column_name = upload_file_same_structure.income_amount_column_name
            expense_amount_column_name = upload_file_same_structure.expense_amount_column_name
            operation_type_column_name = upload_file_same_structure.operation_type_column_name

        # Update and save
        upload_file.description_column_name = description_column_name
        upload_file.merchant_column_name = merchant_column_name
        upload_file.date_column_name = date_column_name
        upload_file.income_amount_column_name = income_amount_column_name
        upload_file.expense_amount_column_name = expense_amount_column_name
        upload_file.operation_type_column_name = operation_type_column_name
        upload_file.notes = notes
        upload_file.save()

        logger.info(f"Successfully updated structure for UploadFile {upload_file.id}. Date column: {date_column_name}, expense column: {expense_amount_column_name}, operation type column: {operation_type_column_name}, income column: {income_amount_column_name}, description column: {description_column_name}.")
        return upload_file