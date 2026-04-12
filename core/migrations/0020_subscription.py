from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_expense_receipt'),
    ]

    operations = [
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.BigAutoField(auto_now_add=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('society_name', models.CharField(max_length=200)),
                ('plan_tier', models.CharField(choices=[('1-250', '1-250 Flats'), ('251-500', '251-500 Flats'), ('501+', '501 & Above Flats')], max_length=20)),
                ('duration_months', models.IntegerField(choices=[(1, '1 Month'), (6, '6 Months'), (12, '1 Year')])),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('start_date', models.DateTimeField(auto_now_add=True)),
                ('end_date', models.DateTimeField()),
                ('is_active', models.BooleanField(default=True)),
                ('secretary', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subscriptions', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
