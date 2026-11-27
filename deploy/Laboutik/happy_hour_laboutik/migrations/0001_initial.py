import datetime

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('APIcashless', '0267_auto_20260523_1635'),
    ]

    operations = [
        migrations.CreateModel(
            name='HappyHour',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('actif', models.BooleanField(default=False, verbose_name='Happy hour activé')),
                ('debut', models.TimeField(default=datetime.time(22, 30), verbose_name='Début')),
                ('fin', models.TimeField(default=datetime.time(23, 30), help_text='Si la fin est avant le début, la plage passe minuit.', verbose_name='Fin')),
            ],
            options={
                'verbose_name': 'Happy hour',
            },
        ),
        migrations.CreateModel(
            name='HappyHourPrice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prix', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Prix happy hour')),
                ('article', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='happy_hour_price', to='APIcashless.Articles', verbose_name='Article')),
            ],
            options={
                'verbose_name': 'Prix happy hour',
                'verbose_name_plural': 'Prix happy hour',
            },
        ),
    ]
