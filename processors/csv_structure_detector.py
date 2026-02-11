import logging
import os
from math import floor
import pandas as pd

from django.contrib.auth.models import User

from agent.agent import ExpenseCategorizerAgent, AgentTransactionUpload, CsvStructure
from api.models import UploadFile, FileStructureMetadata
from costs.services import CostService
from processors.utils import retry_with_backoff

logger = logging.getLogger(__name__)


class CsvStructureDetector(ExpenseCategorizerAgent):
    file_structure_sample_size_percentage = os.environ.get('FILE_STRUCTURE_SAMPLE_SIZE_PERCENTAGE', 0.1)
    file_structure_min_threshold = os.environ.get('FILE_STRUCTURE_MIN_THRESHOLD', 30)

    def _detect_date_column(self, data: list[dict[str, str]]) -> str | None:
        if not any(data):
            return None

        df = pd.DataFrame(data)
        date_columns = []

        for col in df.columns:
            try:
                # Try to parse as date. dayfirst=True for European formats
                parsed_dates = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
                # If more than 80% are valid dates, it's a candidate
                if parsed_dates.notnull().mean() > 0.8:
                    date_columns.append((col, parsed_dates))
            except Exception:
                continue

        if not date_columns:
            return None

        if len(date_columns) == 1:
            return date_columns[0][0]

        # If multiple, find the one that is systematically more recent
        best_col, best_series = date_columns[0]

        for next_col, next_series in date_columns[1:]:
            common_mask = best_series.notnull() & next_series.notnull()
            if not common_mask.any():
                continue
            # The common mask guarantees that the comparison is between a couple of not null dates. It is possible because they are
            # series of the same data frame that share the same index
            recent_count = (next_series[common_mask] > best_series[common_mask]).sum()
            older_count = (next_series[common_mask] < best_series[common_mask]).sum()

            if recent_count > older_count:
                best_col, best_series = next_col, next_series

        return best_col

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

            detected_date_column = self._detect_date_column(current_data[:transaction_sample_size])

            result_from_agent, response = retry_with_backoff(
                self.detect_csv_structure,
                on_failure=(CsvStructure(None, None, None, None, None, None, None, "low"), None),
                transactions=[AgentTransactionUpload(raw_text=tx, transaction_id=0) for tx in
                 current_data[:transaction_sample_size]],
                known_date_column=detected_date_column
            )
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
            date_column_name = detected_date_column or result_from_agent.transaction_date_field
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