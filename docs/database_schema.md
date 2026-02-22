# Database Schema

## Overview

The NeoBank database contains 5 tables with 1,315 total records representing a GCC banking dataset.

## Tables

### customers (20 rows)

| Column | Type | Description |
|--------|------|-------------|
| id | INT (PK) | Auto-increment |
| customer_code | NVARCHAR(20) | Unique code (e.g., CUST001) |
| full_name | NVARCHAR(200) | Company/entity name |
| customer_type | NVARCHAR(20) | Corporate, Government, SME |
| country | NVARCHAR(50) | Bahrain, Saudi Arabia, UAE, Kuwait, Qatar, Oman |
| sector | NVARCHAR(100) | Oil & Gas, Financial Services, Telecom, etc. |
| risk_rating | NVARCHAR(10) | Low, Medium, High |
| relationship_manager | NVARCHAR(100) | Assigned RM |
| onboarding_date | DATE | Client onboarding date |
| kyc_status | NVARCHAR(20) | Verified, Pending |
| total_exposure_usd | DECIMAL(18,2) | Total credit exposure |

### financial_data (80 rows)

4 quarters (Q1-Q4 2025) per customer.

| Column | Type | Description |
|--------|------|-------------|
| id | INT (PK) | Auto-increment |
| customer_id | INT (FK) | References customers.id |
| fiscal_year | INT | 2025 |
| fiscal_quarter | NVARCHAR(2) | Q1, Q2, Q3, Q4 |
| revenue_usd | DECIMAL(18,2) | Quarterly revenue |
| net_income_usd | DECIMAL(18,2) | Net income |
| total_assets_usd | DECIMAL(18,2) | Total assets |
| total_liabilities_usd | DECIMAL(18,2) | Total liabilities |
| equity_usd | DECIMAL(18,2) | Shareholder equity |
| debt_to_equity_ratio | DECIMAL(8,4) | D/E ratio |
| current_ratio | DECIMAL(8,4) | Current ratio |
| roe_pct | DECIMAL(8,4) | Return on equity % |
| credit_rating | NVARCHAR(10) | AAA, AA, A, BBB, BB |
| report_date | DATE | Quarter end date |

### market_analysis (10 rows)

GCC and Bahrain sector analysis.

| Column | Type | Description |
|--------|------|-------------|
| id | INT (PK) | Auto-increment |
| sector | NVARCHAR(100) | Industry sector |
| region | NVARCHAR(50) | GCC or Bahrain |
| analysis_date | DATE | Analysis date |
| gdp_growth_pct | DECIMAL(8,4) | GDP growth rate |
| inflation_rate_pct | DECIMAL(8,4) | Inflation rate |
| interest_rate_pct | DECIMAL(8,4) | Interest rate |
| sector_outlook | NVARCHAR(20) | Positive, Neutral |
| market_cap_usd_bn | DECIMAL(18,4) | Market cap in billions |
| pe_ratio | DECIMAL(8,2) | Price/earnings ratio |
| analyst_recommendation | NVARCHAR(200) | Buy/Hold/Sell recommendation |
| key_risks | NVARCHAR(500) | Risk factors |
| source | NVARCHAR(100) | Data source |

### research_reports (5 rows)

Reports with VARBINARY blob content (simulated PDFs).

| Column | Type | Description |
|--------|------|-------------|
| id | INT (PK) | Auto-increment |
| title | NVARCHAR(300) | Report title |
| report_type | NVARCHAR(50) | Market, Credit, Regulatory, Annual |
| customer_id | INT | Optional FK to customers |
| sector | NVARCHAR(100) | Related sector |
| author | NVARCHAR(100) | Report author |
| publish_date | DATE | Publication date |
| summary | NVARCHAR(MAX) | Text summary |
| **report_content** | **VARBINARY(MAX)** | **Binary PDF content** |
| content_type | NVARCHAR(50) | application/pdf |
| file_size_bytes | INT | File size |
| classification | NVARCHAR(20) | Internal, Confidential |
| tags | NVARCHAR(500) | Comma-separated tags |

### transactions (1,200 rows)

Banking transactions across all customers.

| Column | Type | Description |
|--------|------|-------------|
| id | INT (PK) | Auto-increment |
| customer_id | INT (FK) | References customers.id |
| transaction_date | DATETIME2 | Transaction timestamp |
| transaction_type | NVARCHAR(30) | Deposit, Withdrawal, Transfer, Loan, Payment, FX, Trade |
| amount_usd | DECIMAL(18,2) | Amount in USD |
| currency | NVARCHAR(3) | USD, BHD, SAR, AED |
| counterparty | NVARCHAR(200) | Counterparty bank |
| description | NVARCHAR(500) | Transaction description |
| status | NVARCHAR(20) | Completed, Pending, Failed |
| risk_flag | BIT | 1 = flagged (~4% of transactions) |

## BLOB Reports

| # | Title | Type | Classification |
|---|-------|------|----------------|
| 1 | GCC Oil & Gas Sector Annual Review 2025 | Market | Internal |
| 2 | Credit Risk Assessment — Gulf Petrochemical | Credit | Confidential |
| 3 | Bahrain Financial Services Regulatory Update Q4 2025 | Regulatory | Internal |
| 4 | Al Baraka Banking Group Annual Credit Review | Annual | Confidential |
| 5 | GCC Real Estate Market Outlook 2026 | Market | Internal |

## Sample Queries

```sql
-- Top customers by exposure
SELECT TOP 5 full_name, total_exposure_usd FROM customers ORDER BY total_exposure_usd DESC

-- Financial performance by country
SELECT c.country, AVG(f.debt_to_equity_ratio) as avg_dte, AVG(f.roe_pct) as avg_roe
FROM customers c JOIN financial_data f ON c.id = f.customer_id
WHERE f.fiscal_quarter = 'Q4' GROUP BY c.country

-- High-risk transactions
SELECT transaction_type, COUNT(*) as cnt, SUM(amount_usd) as total
FROM transactions WHERE risk_flag = 1 GROUP BY transaction_type

-- Sectors with positive outlook
SELECT sector, region, gdp_growth_pct, analyst_recommendation
FROM market_analysis WHERE sector_outlook = 'Positive'
```
