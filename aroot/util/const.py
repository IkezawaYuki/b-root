from enum import Enum

NOT_CONNECTED = 0
CONNECTED = 1
EXPIRED = 2


class InstagramTokenStatus(Enum):
    NOT_CONNECTED = 0
    CONNECTED = 1
    EXPIRED = 2


class DashboardStatus(Enum):
    STARTER = "100"
    AUTH_PENDING = "101"
    AUTH_ERROR_INSTAGRAM = "102"
    AUTH_ERROR_WORDPRESS = "103"
    AUTH_SUCCESS = "200"
    TOKEN_EXPIRED = "201"
    EXECUTE_SUCCESS = "202"
    MOD_START_DATE = "203"
    UPDATE_INFORMATION = "301"
    HEALTHY = "0"


PAYMENT_TYPE_NONE = "none"
PAYMENT_TYPE_STRIPE = "stripe"
