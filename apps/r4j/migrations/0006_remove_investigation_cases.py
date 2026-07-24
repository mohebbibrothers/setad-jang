# Generated manually after product scope change: R4J no longer owns operational cases.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("r4j", "0005_r4jinvestigationcase_r4jcaseevent_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="R4JCaseEvent",
        ),
        migrations.DeleteModel(
            name="R4JInvestigationCase",
        ),
    ]
