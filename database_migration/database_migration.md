# Specification: CSV to Database Ingestion Script

## 1. Overview
This script acts as the initial data pipeline step. Its job is to ingest all CSV files in the current working directory and load them into a centralized SQLite database file. Following the data ingestion, it must generate a Markdown artifact documenting the resulting database schema.

## 2. Input & Loading Requirements
*   **Source Data**: Dynamically locate and read all files matching `*.csv` in the relative root directory (`./`).
*   **Database Target**: Connect to a local SQLite database named `data.db` in the same directory.
*   **Table Naming**: Convert each CSV into a distinct table. The table name must be derived directly from the CSV filename (e.g., `northwind_complaints.csv` becomes table `northwind_complaints`).
*   **Data Type Inference**: The script should automatically infer and apply appropriate SQL data types (e.g., INTEGER, REAL, TEXT, DATETIME) for each column during the table creation process, rather than defaulting to generic text fields.
*   **Idempotency**: If the script is executed multiple times, it should safely overwrite or replace existing tables in `data.db` without duplicating data.

## 3. Output Artifacts
The script must successfully yield two files:
1.  **`data.db`**: The populated SQLite database file containing all distinct tables.
2.  **`schema.md`**: A generated Markdown document that acts as a data dictionary. For every table created in the database, this document must list the table name, all its columns, and their assigned SQL data types in a clean, readable format (such as a bulleted list or Markdown tables).