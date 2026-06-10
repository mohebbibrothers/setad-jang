"""
URL routing for the LMS application.

Concrete API endpoints are added in LMS API phases. Keeping the namespace wired
from Phase 1 allows schema/config checks to stay stable as the app grows.
"""


app_name = "lms"

urlpatterns: list = []
