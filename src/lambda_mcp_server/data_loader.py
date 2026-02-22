"""One-time data loader — creates NeoBank database and loads sample data."""
import json
import os
import boto3
import pymssql


def get_connection(database="master"):
    sm = boto3.client("secretsmanager", region_name="me-south-1")
    secret = json.loads(sm.get_secret_value(SecretId=os.environ["SECRET_ARN"])["SecretString"])
    return pymssql.connect(
        server=os.environ["DB_HOST"], port=1433,
        user=secret["username"], password=secret["password"],
        database=database, autocommit=True,
    )


def handler(event, context):
    action = event.get("action", "setup")

    if action == "create_db":
        conn = get_connection("master")
        cursor = conn.cursor()
        cursor.execute("IF NOT EXISTS (SELECT * FROM sys.databases WHERE name='BankABC') CREATE DATABASE BankABC")
        conn.close()
        return {"status": "BankABC database created"}

    elif action == "create_tables":
        conn = get_connection("BankABC")
        cursor = conn.cursor()
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='customers')
            CREATE TABLE customers (
                id INT IDENTITY(1,1) PRIMARY KEY, customer_code NVARCHAR(20) NOT NULL UNIQUE,
                full_name NVARCHAR(200) NOT NULL, customer_type NVARCHAR(20),
                country NVARCHAR(50), sector NVARCHAR(100), risk_rating NVARCHAR(10),
                relationship_manager NVARCHAR(100), onboarding_date DATE,
                kyc_status NVARCHAR(20), total_exposure_usd DECIMAL(18,2), created_at DATETIME2 DEFAULT GETDATE())
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='financial_data')
            CREATE TABLE financial_data (
                id INT IDENTITY(1,1) PRIMARY KEY, customer_id INT FOREIGN KEY REFERENCES customers(id),
                fiscal_year INT, fiscal_quarter NVARCHAR(2), revenue_usd DECIMAL(18,2),
                net_income_usd DECIMAL(18,2), total_assets_usd DECIMAL(18,2),
                total_liabilities_usd DECIMAL(18,2), equity_usd DECIMAL(18,2),
                debt_to_equity_ratio DECIMAL(8,4), current_ratio DECIMAL(8,4),
                roe_pct DECIMAL(8,4), credit_rating NVARCHAR(10), report_date DATE)
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='market_analysis')
            CREATE TABLE market_analysis (
                id INT IDENTITY(1,1) PRIMARY KEY, sector NVARCHAR(100), region NVARCHAR(50),
                analysis_date DATE, gdp_growth_pct DECIMAL(8,4), inflation_rate_pct DECIMAL(8,4),
                interest_rate_pct DECIMAL(8,4), sector_outlook NVARCHAR(20),
                market_cap_usd_bn DECIMAL(18,4), pe_ratio DECIMAL(8,2),
                analyst_recommendation NVARCHAR(200), key_risks NVARCHAR(500), source NVARCHAR(100))
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='research_reports')
            CREATE TABLE research_reports (
                id INT IDENTITY(1,1) PRIMARY KEY, title NVARCHAR(300), report_type NVARCHAR(50),
                customer_id INT, sector NVARCHAR(100), author NVARCHAR(100),
                publish_date DATE, summary NVARCHAR(MAX), report_content VARBINARY(MAX),
                content_type NVARCHAR(50), file_size_bytes INT,
                classification NVARCHAR(20), tags NVARCHAR(500))
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='transactions')
            CREATE TABLE transactions (
                id INT IDENTITY(1,1) PRIMARY KEY, customer_id INT FOREIGN KEY REFERENCES customers(id),
                transaction_date DATETIME2, transaction_type NVARCHAR(30),
                amount_usd DECIMAL(18,2), currency NVARCHAR(3), counterparty NVARCHAR(200),
                description NVARCHAR(500), status NVARCHAR(20), risk_flag BIT DEFAULT 0)
        """)
        conn.close()
        return {"status": "All 5 tables created"}

    elif action == "load_customers":
        conn = get_connection("BankABC")
        cursor = conn.cursor()
        customers = [
            ('CUST001','Gulf Petrochemical Industries','Corporate','Bahrain','Oil & Gas','Medium','Ahmed Al-Khalifa','2018-03-15','Verified',45000000),
            ('CUST002','Al Baraka Banking Group','Corporate','Bahrain','Financial Services','Low','Fatima Hassan','2015-07-22','Verified',120000000),
            ('CUST003','Bahrain Telecommunications','Corporate','Bahrain','Telecommunications','Low','Mohammed Al-Dosari','2016-01-10','Verified',35000000),
            ('CUST004','National Oil & Gas Authority','Government','Bahrain','Oil & Gas','Low','Ahmed Al-Khalifa','2014-06-01','Verified',200000000),
            ('CUST005','Aluminum Bahrain (Alba)','Corporate','Bahrain','Manufacturing','Low','Sara Al-Mannai','2017-09-12','Verified',85000000),
            ('CUST006','Investcorp Holdings','Corporate','Bahrain','Financial Services','Medium','Fatima Hassan','2019-02-28','Verified',150000000),
            ('CUST007','Gulf Air','Corporate','Bahrain','Aviation','High','Mohammed Al-Dosari','2016-11-05','Verified',60000000),
            ('CUST008','Bahrain Real Estate Investment','Corporate','Bahrain','Real Estate','Medium','Sara Al-Mannai','2020-04-18','Verified',28000000),
            ('CUST009','Saudi Basic Industries (SABIC)','Corporate','Saudi Arabia','Petrochemicals','Low','Ahmed Al-Khalifa','2015-08-30','Verified',300000000),
            ('CUST010','Emirates NBD','Corporate','UAE','Financial Services','Low','Fatima Hassan','2017-03-14','Verified',175000000),
            ('CUST011','Kuwait Finance House','Corporate','Kuwait','Financial Services','Low','Fatima Hassan','2018-06-20','Verified',95000000),
            ('CUST012','Oman Oil Company','Corporate','Oman','Oil & Gas','Medium','Ahmed Al-Khalifa','2019-01-15','Verified',110000000),
            ('CUST013','Qatar National Bank','Corporate','Qatar','Financial Services','Low','Fatima Hassan','2016-04-22','Verified',250000000),
            ('CUST014','Al Jazeera Trading','SME','Bahrain','Trading','Medium','Sara Al-Mannai','2021-07-10','Verified',5000000),
            ('CUST015','Bahrain Development Bank','Government','Bahrain','Financial Services','Low','Mohammed Al-Dosari','2014-01-01','Verified',80000000),
            ('CUST016','Middle East Healthcare','Corporate','Bahrain','Healthcare','Low','Sara Al-Mannai','2020-09-05','Verified',15000000),
            ('CUST017','GCC Construction Group','Corporate','Saudi Arabia','Construction','High','Ahmed Al-Khalifa','2022-03-20','Pending',22000000),
            ('CUST018','Digital Bahrain Technologies','SME','Bahrain','Technology','Medium','Mohammed Al-Dosari','2023-01-15','Verified',3000000),
            ('CUST019','Arabian Shipping Lines','Corporate','UAE','Logistics','Medium','Ahmed Al-Khalifa','2018-11-28','Verified',42000000),
            ('CUST020','Bahrain Tourism Authority','Government','Bahrain','Tourism','Low','Sara Al-Mannai','2019-05-10','Verified',18000000),
        ]
        for c in customers:
            cursor.execute("INSERT INTO customers (customer_code,full_name,customer_type,country,sector,risk_rating,relationship_manager,onboarding_date,kyc_status,total_exposure_usd) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", c)
        conn.close()
        return {"status": f"{len(customers)} customers inserted"}

    elif action == "load_financial":
        conn = get_connection("BankABC")
        cursor = conn.cursor()
        import random
        random.seed(42)
        ratings = ['AAA','AA','A','BBB','BB']
        count = 0
        for cid in range(1, 21):
            for q in ['Q1','Q2','Q3','Q4']:
                cursor.execute(
                    "INSERT INTO financial_data (customer_id,fiscal_year,fiscal_quarter,revenue_usd,net_income_usd,total_assets_usd,total_liabilities_usd,equity_usd,debt_to_equity_ratio,current_ratio,roe_pct,credit_rating,report_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (cid, 2025, q, random.randint(5000000,55000000), random.randint(500000,10500000),
                     random.randint(50000000,550000000), random.randint(20000000,320000000),
                     random.randint(10000000,210000000), round(random.random()*3,4),
                     round(0.8+random.random()*2,4), round(random.random()*25,4),
                     random.choice(ratings), f"2025-{['03','06','09','12'][['Q1','Q2','Q3','Q4'].index(q)]}-30"))
                count += 1
        conn.close()
        return {"status": f"{count} financial records inserted"}

    elif action == "load_market":
        conn = get_connection("BankABC")
        cursor = conn.cursor()
        markets = [
            ('Oil & Gas','GCC','2025-12-15',3.2,2.1,5.25,'Positive',850.5,12.3,'Overweight — strong demand recovery','Geopolitical tensions, OPEC+ cuts','NeoBank Research'),
            ('Financial Services','GCC','2025-12-15',4.1,1.8,5.25,'Positive',420.8,10.5,'Buy — digital transformation driving growth','Regulatory changes, fintech competition','NeoBank Research'),
            ('Telecommunications','GCC','2025-12-15',2.8,2.3,5.25,'Neutral',180.2,15.7,'Hold — 5G capex cycle peaking','Spectrum costs, competition','NeoBank Research'),
            ('Real Estate','GCC','2025-12-15',3.5,3.1,5.25,'Positive',310.6,8.9,'Buy — mega-project pipeline strong','Interest rate sensitivity, oversupply risk','NeoBank Research'),
            ('Manufacturing','GCC','2025-12-15',2.5,2.7,5.25,'Neutral',95.3,11.2,'Hold — energy cost advantage','Supply chain disruptions, raw material costs','NeoBank Research'),
            ('Aviation','GCC','2025-12-15',5.2,2.0,5.25,'Positive',65.8,18.4,'Buy — tourism recovery accelerating','Fuel costs, geopolitical risk','NeoBank Research'),
            ('Healthcare','GCC','2025-12-15',6.1,1.5,5.25,'Positive',45.2,22.1,'Strong Buy — demographic tailwinds','Regulatory approvals, talent shortage','NeoBank Research'),
            ('Technology','GCC','2025-12-15',8.3,1.2,5.25,'Positive',28.7,35.6,'Strong Buy — Vision 2030 digital push','Talent competition, funding cycles','NeoBank Research'),
            ('Oil & Gas','Bahrain','2025-12-15',2.8,2.5,5.00,'Neutral',12.3,10.8,'Hold — production plateau','Reserve depletion, diversification need','NeoBank Research'),
            ('Financial Services','Bahrain','2025-12-15',4.5,1.6,5.00,'Positive',35.6,11.2,'Buy — fintech hub status growing','CBB regulation, competition from UAE','NeoBank Research'),
        ]
        for m in markets:
            cursor.execute("INSERT INTO market_analysis (sector,region,analysis_date,gdp_growth_pct,inflation_rate_pct,interest_rate_pct,sector_outlook,market_cap_usd_bn,pe_ratio,analyst_recommendation,key_risks,source) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", m)
        conn.close()
        return {"status": f"{len(markets)} market records inserted"}

    elif action == "load_reports":
        conn = get_connection("BankABC")
        cursor = conn.cursor()
        reports = [
            ('GCC Oil & Gas Sector Annual Review 2025','Market',None,'Oil & Gas','Dr. Ahmed Al-Khalifa','2025-12-01',
             'Comprehensive analysis of GCC oil and gas sector performance in 2025.',
             b'%PDF-1.4 GCC Oil Gas Sector Review 2025. Executive Summary: The GCC oil and gas sector demonstrated resilience in 2025 despite global economic headwinds. Total sector revenue reached $850B, driven by stable crude prices averaging $78/barrel. Key findings: 1) Bahrain production steady at 200K bpd from Abu Saafa field. 2) Saudi Aramco downstream expansion on track. 3) UAE renewable energy investments exceeded $15B. 4) Qatar LNG expansion Phase 2 progressing. Risk factors include geopolitical tensions and energy transition acceleration. Recommendation: Overweight GCC energy sector.',
             'application/pdf',45000,'Internal','oil,gas,gcc,annual,2025'),
            ('Credit Risk Assessment — Gulf Petrochemical','Credit',1,'Oil & Gas','Fatima Hassan','2025-11-15',
             'Credit risk assessment for Gulf Petrochemical Industries. Current exposure $45M.',
             b'%PDF-1.4 Credit Risk Assessment Report. Borrower: Gulf Petrochemical Industries BSC. Facility: $45,000,000 revolving credit. Financial Highlights: Revenue $2.1B (up 8% YoY). EBITDA margin 22%. Net debt/EBITDA 2.8x. Current ratio 1.45. Interest coverage 4.2x. Credit Rating: BBB+ (stable). Key Strengths: Diversified product portfolio, strategic location. Key Risks: Feedstock price volatility. Recommendation: APPROVE renewal of $45M facility.',
             'application/pdf',38000,'Confidential','credit,risk,petrochemical'),
            ('Bahrain Financial Services Regulatory Update Q4 2025','Regulatory',None,'Financial Services','Mohammed Al-Dosari','2025-12-20',
             'Central Bank of Bahrain regulatory updates for Q4 2025.',
             b'%PDF-1.4 CBB Regulatory Update Q4 2025. 1. Open Banking Framework effective March 2026. 2. Enhanced AML/CFT requirements. 3. Digital Asset Custody regulations finalized. 4. Basel III.1 implementation January 2027. 5. Mandatory ESG reporting from FY2026. Impact: Moderate IT investment required.',
             'application/pdf',52000,'Internal','regulatory,cbb,bahrain'),
            ('Al Baraka Banking Group Annual Credit Review','Annual',2,'Financial Services','Fatima Hassan','2025-10-30',
             'Annual credit review for Al Baraka Banking Group. Total exposure $120M.',
             b'%PDF-1.4 Annual Credit Review. Client: Al Baraka Banking Group. Total Exposure: $120M. Total assets $28.5B (up 6%). Net profit $285M (up 12%). CAR 16.2%. NPL ratio 3.8%. ROE 11.5%. Recommendation: INCREASE facility to $150M.',
             'application/pdf',41000,'Confidential','credit,annual,islamic,banking'),
            ('GCC Real Estate Market Outlook 2026','Market',None,'Real Estate','Sara Al-Mannai','2025-12-10',
             'Forward-looking analysis of GCC real estate markets.',
             b'%PDF-1.4 GCC Real Estate Outlook 2026. Market valued at $310B with projected 8% growth. Saudi mega-projects driving demand. Bahrain affordable housing initiative. UAE market stabilizing. Key Risks: Rising interest rates, oversupply in luxury segment.',
             'application/pdf',48000,'Internal','real,estate,gcc,outlook'),
        ]
        for r in reports:
            vals = list(r)
            blob = vals[7]
            vals[7] = None  # placeholder
            cursor.execute(
                "INSERT INTO research_reports (title,report_type,customer_id,sector,author,publish_date,summary,report_content,content_type,file_size_bytes,classification,tags) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,CONVERT(VARBINARY(MAX),%s),%s,%s,%s,%s)",
                (vals[0],vals[1],vals[2],vals[3],vals[4],vals[5],vals[6],blob.decode('latin-1'),vals[8],vals[9],vals[10],vals[11]))

        conn.close()
        return {"status": f"{len(reports)} research reports with blob data inserted"}

    elif action == "load_transactions":
        conn = get_connection("BankABC")
        cursor = conn.cursor()
        import random
        random.seed(99)
        types = ['Deposit','Withdrawal','Transfer','Loan','Payment','FX','Trade']
        currencies = ['USD','BHD','SAR','AED']
        counterparties = ['Citibank NY','HSBC London','Deutsche Bank','JP Morgan','Standard Chartered']
        count = 0
        for i in range(1200):
            cid = random.randint(1,20)
            day_offset = random.randint(0,364)
            cursor.execute(
                "INSERT INTO transactions (customer_id,transaction_date,transaction_type,amount_usd,currency,counterparty,description,status,risk_flag) VALUES (%s,DATEADD(DAY,%s,'2025-01-01'),%s,%s,%s,%s,%s,%s,%s)",
                (cid, day_offset, random.choice(types), random.randint(1000,5000000),
                 random.choice(currencies), random.choice(counterparties),
                 f'Banking transaction {i+1}',
                 'Completed' if random.random()>0.05 else ('Pending' if random.random()>0.5 else 'Failed'),
                 1 if random.random()<0.04 else 0))
            count += 1
        conn.close()
        return {"status": f"{count} transactions inserted"}

    elif action == "verify":
        conn = get_connection("BankABC")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 'customers' AS tbl, COUNT(*) AS cnt FROM customers UNION ALL
            SELECT 'financial_data', COUNT(*) FROM financial_data UNION ALL
            SELECT 'market_analysis', COUNT(*) FROM market_analysis UNION ALL
            SELECT 'research_reports', COUNT(*) FROM research_reports UNION ALL
            SELECT 'transactions', COUNT(*) FROM transactions
        """)
        return {"tables": cursor.fetchall()}

    return {"error": f"Unknown action: {action}"}
