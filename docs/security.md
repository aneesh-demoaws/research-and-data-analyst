# Security Posture

## Defense in Depth

| Layer | Control | Details |
|-------|---------|---------|
| Authentication | IAM + SigV4 | All API calls authenticated, no anonymous access |
| Network | VPC + Private Subnets | RDS and Lambda MCP Server in private subnets |
| Network | Security Groups | Port 1433 restricted to Lambda SG only |
| Network | VPC Endpoints | Secrets Manager accessed via VPC endpoint (no internet) |
| Encryption | KMS | RDS encrypted at rest with AWS-managed KMS key |
| Secrets | Secrets Manager | DB credentials never in code or environment variables |
| Access Control | Resource Policies | Lambda functions restricted to specific principals |
| Access Control | IAM Roles | Least-privilege roles for each component |
| Data Protection | Read-Only SQL | Write operations (DROP, DELETE, INSERT, etc.) blocked in Lambda |
| Frontend | IP Restriction | Security Group limits access to specific CIDR |

## IAM Roles

| Role | Purpose | Permissions |
|------|---------|-------------|
| Lambda MCP Role | MCP Server execution | VPC access, Secrets Manager read, CloudWatch logs |
| Lambda Proxy Role | Proxy execution | Invoke MCP Server Lambda, CloudWatch logs |
| Gateway Role | AgentCore Gateway | Invoke Proxy Lambda |
| Runtime Exec Role | AgentCore Runtime | Invoke Gateway, Bedrock model access |
| EC2 Instance Role | Frontend | Invoke AgentCore Runtime |

## Network Architecture

```
Internet
    │
    ▼ (restricted to specific IP)
┌─────────────────────────────────────────┐
│ Public Subnet                            │
│   EC2 (Streamlit) ← SG: 8501 from IP   │
└─────────────────────────────────────────┘
    │ (no direct DB access)
    │
┌─────────────────────────────────────────┐
│ Private Subnets                          │
│   Lambda MCP Server ← SG: outbound only │
│   RDS MSSQL ← SG: 1433 from Lambda SG  │
│   VPC Endpoint (Secrets Manager)         │
└─────────────────────────────────────────┘
```

## Recommendations for Production

1. Enable RDS deletion protection
2. Enable Multi-AZ for RDS
3. Add WAF in front of the frontend
4. Enable CloudTrail for API audit logging
5. Add Bedrock Guardrails for content filtering
6. Implement query cost estimation before execution
7. Add rate limiting on the frontend
8. Use AWS Certificate Manager for HTTPS on the frontend
