
**Purpose:** What to paste into Sevalla dashboard

```
# sevalla_assets/ENV_TEMPLATE.txt
# Copy these into Sevalla Dashboard → Settings → Environment Variables

# ============================================================================
# BACKEND SERVICE ENVIRONMENT VARIABLES
# ============================================================================

AWS_ACCESS_KEY_ID=AKIAXXXXXXXXXXXXXXXX
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_DEFAULT_REGION=us-east-1
LOG_LEVEL=INFO

# ============================================================================
# FRONTEND SERVICE ENVIRONMENT VARIABLES
# ============================================================================

BACKEND_URL=http://backend:8000

# ============================================================================
# NOTES
# ============================================================================
# - NEVER commit these to GitHub!
# - Set these manually in Sevalla dashboard
# - Backend reads AWS credentials from os.environ automatically (boto3)
# - Frontend reads BACKEND_URL for service discovery
```