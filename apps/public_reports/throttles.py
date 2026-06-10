from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class ReportCreateAnonThrottle(AnonRateThrottle):
    scope = "report_create_anon"


class ReportCreateUserThrottle(UserRateThrottle):
    scope = "report_create_user"
