import django_filters

from .models import Report, ReportSubject


class ReportFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status", lookup_expr="iexact")
    subject = django_filters.NumberFilter(field_name="subject_id")
    created_from = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.DateFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Report
        fields = ("status", "subject", "created_from", "created_to")


class ReportSubjectFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter(field_name="is_active")
    title = django_filters.CharFilter(field_name="title", lookup_expr="icontains")

    class Meta:
        model = ReportSubject
        fields = ("is_active", "title")
