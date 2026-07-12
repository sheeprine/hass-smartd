"""Constants for the S.M.A.R.T. Disk Monitor integration."""

DOMAIN = "smartd"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_AUTH_TYPE = "auth_type"
CONF_PASSWORD = "password"
CONF_SSH_KEY = "ssh_private_key"
CONF_DEVICES = "devices"

# Auth type values
AUTH_TYPE_PASSWORD = "password"
AUTH_TYPE_KEY = "key"

# Defaults
DEFAULT_PORT = 22
DEFAULT_SCAN_INTERVAL = 300  # seconds

# Platform names
PLATFORM_SENSOR = "sensor"
PLATFORM_BINARY_SENSOR = "binary_sensor"

PLATFORMS = [PLATFORM_SENSOR, PLATFORM_BINARY_SENSOR]

# SMART attribute IDs
ATTR_ID_REALLOCATED_SECTORS = 5
ATTR_ID_PENDING_SECTORS = 197
ATTR_ID_UNCORRECTABLE_ERRORS = 198

# Coordinator data keys
DATA_COORDINATOR = "coordinator"

# Device type detection
DEVICE_TYPE_NVME = "nvme"
