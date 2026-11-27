from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cawl_fedow', '0002_walletrefundrequest_walletrefund_and_more'),
    ]

    operations = [
        # FR : Les recharges existantes n'avaient pas de frais : défaut 0.
        # EN: Existing refills had no fee, hence the 0 default.
        migrations.AddField(
            model_name='checkout',
            name='fee',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
