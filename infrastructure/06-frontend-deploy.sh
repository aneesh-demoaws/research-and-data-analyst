#!/bin/bash
# Phase 6: Frontend Deployment
set -e

DATA_REGION="me-south-1"
AI_REGION="eu-west-1"
AGENT_ARN=""       # AgentCore Runtime ARN from Phase 5
KEY_PAIR=""        # Your EC2 key pair name
ALLOWED_IP=""      # Your IP in CIDR format (e.g., 1.2.3.4/32)
VPC_ID=""          # Your VPC ID
PUBLIC_SUBNET=""   # A public subnet ID
INSTANCE_PROFILE="" # IAM instance profile with bedrock-agentcore invoke permissions

echo "=== Phase 6: Frontend Deployment ==="

# 1. Create security group
FE_SG=$(aws ec2 create-security-group \
  --group-name neobank-frontend-sg \
  --description "NeoBank Streamlit Frontend" \
  --vpc-id $VPC_ID \
  --region $DATA_REGION \
  --query 'GroupId' --output text)

aws ec2 authorize-security-group-ingress --group-id $FE_SG --protocol tcp --port 22 --cidr $ALLOWED_IP --region $DATA_REGION
aws ec2 authorize-security-group-ingress --group-id $FE_SG --protocol tcp --port 8501 --cidr $ALLOWED_IP --region $DATA_REGION

# 2. Create user data script
cat > /tmp/neobank_userdata.sh << USERDATA
#!/bin/bash
yum update -y
yum install -y python3.11 python3.11-pip
pip3.11 install streamlit boto3

cat > /home/ec2-user/app.py << 'APPEOF'
$(cat src/frontend/app.py)
APPEOF

# Update AGENT_ARN in app.py
sed -i "s|AGENT_ARN = .*|AGENT_ARN = \"$AGENT_ARN\"|" /home/ec2-user/app.py

cat > /etc/systemd/system/streamlit.service << 'SVCEOF'
[Unit]
Description=Streamlit NeoBank AI Analyst
After=network.target
[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user
ExecStart=/usr/local/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=always
Environment=AWS_DEFAULT_REGION=$AI_REGION
[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable streamlit
systemctl start streamlit
USERDATA

# 3. Launch EC2
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 \
  --instance-type t3.small \
  --key-name $KEY_PAIR \
  --security-group-ids $FE_SG \
  --subnet-id $PUBLIC_SUBNET \
  --iam-instance-profile Name=$INSTANCE_PROFILE \
  --user-data file:///tmp/neobank_userdata.sh \
  --associate-public-ip-address \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":8,"VolumeType":"gp3","Encrypted":true}}]' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=NeoBank-Frontend}]" \
  --region $DATA_REGION \
  --query 'Instances[0].InstanceId' --output text)

echo "Waiting for instance..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $DATA_REGION

PUBLIC_IP=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID --region $DATA_REGION \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo ""
echo "=== Phase 6 Complete ==="
echo "Instance: $INSTANCE_ID"
echo "Frontend URL: http://$PUBLIC_IP:8501"
echo "Allow 2-3 minutes for user data script to complete."
