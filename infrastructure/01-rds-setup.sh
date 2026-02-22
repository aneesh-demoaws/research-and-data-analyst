#!/bin/bash
# Phase 1: RDS MSSQL Setup
# Edit these variables for your environment
set -e

DATA_REGION="me-south-1"
DB_INSTANCE_ID="neobank-mssql"
DB_NAME="NeoBank"
SECRET_NAME="neobank/rds-credentials"
DB_USERNAME="admin"
DB_PASSWORD="$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)"
VPC_ID=""          # Set your VPC ID
PRIVATE_SUBNETS="" # Comma-separated private subnet IDs

echo "=== Phase 1: RDS MSSQL Setup ==="

# 1. Create DB subnet group
echo "Creating DB subnet group..."
aws rds create-db-subnet-group \
  --db-subnet-group-name neobank-rds-private \
  --db-subnet-group-description "NeoBank RDS private subnets" \
  --subnet-ids $(echo $PRIVATE_SUBNETS | tr ',' ' ') \
  --region $DATA_REGION

# 2. Create RDS security group
echo "Creating RDS security group..."
RDS_SG=$(aws ec2 create-security-group \
  --group-name neobank-rds-sg \
  --description "NeoBank RDS MSSQL" \
  --vpc-id $VPC_ID \
  --region $DATA_REGION \
  --query 'GroupId' --output text)
echo "RDS SG: $RDS_SG"

# 3. Create Lambda security group
LAMBDA_SG=$(aws ec2 create-security-group \
  --group-name neobank-lambda-sg \
  --description "NeoBank Lambda MCP Server" \
  --vpc-id $VPC_ID \
  --region $DATA_REGION \
  --query 'GroupId' --output text)
echo "Lambda SG: $LAMBDA_SG"

# 4. Allow Lambda → RDS on port 1433
aws ec2 authorize-security-group-ingress \
  --group-id $RDS_SG \
  --protocol tcp --port 1433 \
  --source-group $LAMBDA_SG \
  --region $DATA_REGION

# 5. Create Secrets Manager secret
echo "Creating Secrets Manager secret..."
aws secretsmanager create-secret \
  --name $SECRET_NAME \
  --secret-string "{\"username\":\"$DB_USERNAME\",\"password\":\"$DB_PASSWORD\",\"port\":1433}" \
  --region $DATA_REGION

# 6. Create VPC endpoint for Secrets Manager
echo "Creating Secrets Manager VPC endpoint..."
aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$DATA_REGION.secretsmanager \
  --vpc-endpoint-type Interface \
  --subnet-ids $(echo $PRIVATE_SUBNETS | tr ',' ' ') \
  --private-dns-enabled \
  --region $DATA_REGION

# 7. Create RDS instance
echo "Creating RDS MSSQL instance (this takes ~10 minutes)..."
aws rds create-db-instance \
  --db-instance-identifier $DB_INSTANCE_ID \
  --db-instance-class db.t3.xlarge \
  --engine sqlserver-ex \
  --master-username $DB_USERNAME \
  --master-user-password "$DB_PASSWORD" \
  --allocated-storage 20 \
  --storage-encrypted \
  --no-publicly-accessible \
  --vpc-security-group-ids $RDS_SG \
  --db-subnet-group-name neobank-rds-private \
  --backup-retention-period 7 \
  --region $DATA_REGION

echo ""
echo "=== Phase 1 Complete ==="
echo "RDS SG: $RDS_SG"
echo "Lambda SG: $LAMBDA_SG"
echo "DB Password stored in Secrets Manager: $SECRET_NAME"
echo ""
echo "Wait for RDS to be available:"
echo "  aws rds wait db-instance-available --db-instance-identifier $DB_INSTANCE_ID --region $DATA_REGION"
