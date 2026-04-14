from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_expense_receipt'),
    ]

    operations = [
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('society_name', models.CharField(max_length=200)),
                ('secretary_id', models.PositiveIntegerField(blank=True, null=True)),
                ('plan_tier', models.CharField(choices=[('1-250', '1-250 Flats'), ('251-500', '251-500 Flats'), ('501+', '501 & Above Flats')], max_length=20)),
                ('duration_months', models.IntegerField(choices=[(1, '1 Month'), (6, '6 Months'), (12, '1 Year')])),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('payment_proof', models.ImageField(blank=True, null=True, upload_to='subscription_proofs/')),
                ('status', models.CharField(choices=[('pending', 'Pending Payment'), ('review', 'Under Review'), ('active', 'Active'), ('expired', 'Expired')], default='pending', max_length=20)),
                ('start_date', models.DateTimeField(auto_now_add=True)),
                ('end_date', models.DateTimeField()),
                ('is_active', models.BooleanField(default=False)),
            ],
        ),
    ]
