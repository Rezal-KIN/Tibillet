from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [("BaseBillet", "0221_configuration_module_newsletter")]
    operations = [
        migrations.CreateModel(
            name="CawlPayment",
            fields=[
                ("payment", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, primary_key=True,
                    related_name="cawl_payment", serialize=False, to="BaseBillet.paiement_stripe")),
                ("merchant_id", models.CharField(max_length=128)),
                ("test_mode", models.BooleanField(default=True)),
                ("amount", models.PositiveIntegerField()),
                ("hosted_checkout_id", models.CharField(max_length=128, null=True, unique=True)),
                ("checkout_url", models.URLField(blank=True, max_length=1000)),
                ("provider_payment_id", models.CharField(max_length=128, null=True, unique=True)),
                ("provider_status", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="CawlWebhook",
            fields=[
                ("event_id", models.CharField(max_length=128, primary_key=True, serialize=False)),
                ("event_type", models.CharField(max_length=128)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
