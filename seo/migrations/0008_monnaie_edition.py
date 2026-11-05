from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('seo', '0007_portail_collectif'), ('fedow_core', '0001_initial')]
    operations = [
        migrations.AddField(model_name='galaedition', name='currency_isolated',
                            field=models.BooleanField(default=False)),
        migrations.AddField(model_name='galaedition', name='currency',
                            field=models.OneToOneField(blank=True, null=True,
                                on_delete=django.db.models.deletion.PROTECT,
                                related_name='gala_edition', to='fedow_core.asset')),
    ]
