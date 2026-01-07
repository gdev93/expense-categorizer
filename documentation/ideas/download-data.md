Design Document: Transaction CSV Export API (Version 1.1)
This document outlines the high-level design for a memory-efficient CSV export system integrated into the Django application. The system is designed to handle large-scale financial data transfers by streaming rows directly from the database to the client.

1. API Specification
Detail	Definition
Endpoint	POST /api/transactions/export/
Authentication	Required (via User model)
Input Parameters	upload_ids (List), start_date, end_date
Response Format	text/csv (Streamed)

Esporta in Fogli

2. Architecture & Data Flow
A. The Selector Layer
The selector logic filters the Transaction model based on user input.

Filtering: Restricts data to the authenticated user.

Time Range: Applies filters on the transaction_date field.

Relation Loading: Uses select_related('csv_upload') to efficiently access the source file metadata without extra queries.

Batching: Employs .iterator() to fetch records from PostgreSQL in chunks, preventing high memory usage.

B. The Exporter Layer (The Streamer)
A Python generator transforms model instances into CSV strings on the fly.

Header Generation: The generator first yields the translated Italian headers.

Row Mapping: For every Transaction object, it extracts:

transaction_date

amount

transaction_type

description

csv_upload.file_name

Streaming: The StreamingHttpResponse consumes this generator, pushing data to the client as it is created.

3. CSV Field & Language Mapping
The system uses a predefined mapping to ensure the exported file is user-friendly for Italian-speaking users.

English Header (Internal)	Italian Header (Exported)	Model Field Source
Date	Data	transaction_date
Amount	Importo	amount
Transaction Type	Tipo di Transazione	transaction_type
Bank Description	Descrizione Bancaria	description
Original CSV Source	File Sorgente	csv_upload.file_name

Esporta in Fogli

4. Performance Safeguards
Memory Footprint: By utilizing the .iterator() method on the Transaction QuerySet, the server's RAM usage remains constant regardless of whether 100 or 100,000 rows are exported.

Database Efficiency: The query is optimized by existing database indexes on user, transaction_type, and transaction_date.

Connection Resilience: Because the stream begins immediately, the browser acknowledges the download start right away, significantly reducing the risk of gateway timeouts (504 errors).

5. Next Steps
Would you like me to provide the Python generator function code that implements this specific Italian-to-English header mapping for your views?