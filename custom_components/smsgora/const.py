"""Constants for the SMS Gora integration."""

DOMAIN = "smsgora"
DEFAULT_BASE_URL = "https://tekservix.com/smsgora/api/v1"

CONF_RECIPIENTS = "recipients"
CONF_DEVICE_ID = "device_id"
CONF_WEBHOOK_ID = "webhook_id"
CONF_REMOTE_WEBHOOK_ID = "remote_webhook_id"
CONF_WEBHOOK_SECRET = "webhook_secret"

EVENT_SMS_RECEIVED = "smsgora_sms_received"
EVENT_SMS_STATUS = "smsgora_sms_status"

SERVICE_SEND_SMS = "send_sms"
