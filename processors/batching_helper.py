import os
from typing import Any

class BatchingHelper:
    batch_size = int(os.environ.get('AGENT_BATCH_SIZE', 30))

    def __init__(self, batch_size: int = batch_size):
        self.batch_size = batch_size

    def compute_batches(self, data: list[Any]) -> list[list[Any]]:
        """
        Create "smart" batches:
        - Use computed batch_size as the base size
        - Do NOT create an extra smaller remainder batch
        - Instead, append the remainder to the *last* batch
          (so last batch may be larger than batch_size)
        """
        data_count = len(data)
        if data_count == 0:
            return []

        batch_size = self.batch_size

        # If everything fits in one batch, return it.
        if data_count <= batch_size:
            return [data]

        full_batches = data_count // batch_size
        remainder = data_count % batch_size

        batches: list[list[Any]] = []

        # Build full batches; if there's a remainder, extend the *last* batch to include it.
        for batch_num in range(full_batches):
            start_idx = batch_num * batch_size
            end_idx = start_idx + batch_size

            is_last_full_batch = (batch_num == full_batches - 1)
            if is_last_full_batch and remainder:
                end_idx += remainder  # absorb the remainder into the last batch

            batch = data[start_idx:end_idx]
            batches.append(batch)

        return batches
