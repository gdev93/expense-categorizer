# CSV Metadata Algorithm

After making the first categorization via AI, it is possible to find the csv structure by matching amount, description, date, merchant values
in the raw data of the transaction row.
When first mapping is achieved, if the user is uploading a csv with same structure, we can safely parse amount, description, date and merchant:
we can find a similar transaction by matching the merchant name and/or description. Then categorize and skip agent.

## First upload
We parse the csv raw data using csv header mapping and add a csv metadata that will be used as umbrella to fetch that csv transaction. Since no csv mapping is found, the parsed transaction is invalid and we leverage the agent.
### 2nd Batch
After done with first batch, we can create the csv header mapping:
1) find first transaction with status categorized in the csv upload.
2) create a mapping of the csv headers:
   1) take `raw_data`from the `Transaction`.
   2) take `original_amount`, `description`, `merchant_raw_name`, `transaction_date` values, and iterate on the raw_data value, and find the original key.
   3) create the mapping `AMOUNT->csv_amount_header`, `DESCRIPTION->csv_date_header`, `DATE->date_csv_header`, `MERCHANT->merchant_csv_header`.
On the second batch processing, it is now possible to make precise parsing of the raw data:
1) Find date, description, amount and merchant from the ``raw_data``
2) if there is a mapping for ``merchant``, find a transaction with that merchant name (`ILIKE` query) and return.
3) if not, find a transaction with similar description (`WORD_SIMILARITY` with threshold > `0.8`).
4) if not, leverage the agent.

## Second upload
On the second upload, it is highly possible that csv strucure is the same:
1) fetch last ``<tuning-parameter>`` number of csv mappings that reference a `<tuning-parameter` number of categorized transactions.
2) for each csv header mapping, try parse (might be useful to add a depth parameter if there are too many csv mappings).
3) If amount is parsed, description is parsed, date is parsed, and optionally the merchant, repeat 2nd Batch processing by first checking similar transaction.