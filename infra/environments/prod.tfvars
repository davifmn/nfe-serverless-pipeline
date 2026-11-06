environment            = "prod"
region                 = "sa-east-1"
alarm_email            = "oncall@example.com"
log_retention_days     = 90
ingest_max_concurrency = 10
api_clients            = ["accounting", "erp-integration"]
api_rate_limit         = 50
production             = true
