import logging
import os
from math import floor

from django.contrib.auth.models import User

from agent.agent import ExpenseCategorizerAgent, AgentTransactionUpload
from api.models import UploadFile, FileStructureMetadata
from costs.services import CostService

logger = logging.getLogger(__name__)


class CsvStructureDetector(ExpenseCategorizerAgent):
    file_structure_sample_size_percentage = os.environ.get('FILE_STRUCTURE_SAMPLE_SIZE_PERCENTAGE', 0.1)
    file_structure_min_threshold = os.environ.get('FILE_STRUCTURE_MIN_THRESHOLD', 30)

    def setup_upload_file_structure(self, current_data: list[dict[str, str]], upload_file: UploadFile, user:User) -> UploadFile:
        # Check if columns are already set
        if upload_file.description_column_name and upload_file.date_column_name and (
                upload_file.income_amount_column_name or upload_file.expense_amount_column_name):
            logger.info(f"UploadFile {upload_file.id} already has a defined structure. Skipping detection.")
            return upload_file

        if not any(current_data):
            return upload_file

        new_transaction_raw_data_keys = set(current_data[0].keys())
        column_description_hash = FileStructureMetadata.generate_tuple_hash(new_transaction_raw_data_keys)
        file_metadata = FileStructureMetadata.objects.filter(row_hash=column_description_hash).first()

        if file_metadata:
            logger.info(f"Matching structure found in FileMetadata! Using schema from FileMetadata {file_metadata.id}.")
            description_column_name = file_metadata.description_column_name
            notes = file_metadata.notes
            merchant_column_name = file_metadata.merchant_column_name
            date_column_name = file_metadata.date_column_name
            income_amount_column_name = file_metadata.income_amount_column_name
            expense_amount_column_name = file_metadata.expense_amount_column_name
            operation_type_column_name = file_metadata.operation_type_column_name
        else:
            transaction_sample_size = min(len(current_data), max(self.file_structure_min_threshold, floor(
                len(current_data) * self.file_structure_sample_size_percentage)))

            result_from_agent, response = self.detect_csv_structure(
                [AgentTransactionUpload(raw_text=tx, transaction_id=0) for tx in
                 current_data[:transaction_sample_size]])
            if response:
                logger.debug(
                    f"Agent response received. Model: {response.model_name}, Prompt Tokens: {response.prompt_tokens}")
                CostService.log_api_usage(
                    user=user,
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