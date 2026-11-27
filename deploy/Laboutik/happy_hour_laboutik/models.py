import datetime

from django.core.validators import MinValueValidator
from django.db import models
from solo.models import SingletonModel


class HappyHour(SingletonModel):
    """Plage horaire quotidienne, à l'heure du fuseau de la configuration LaBoutik."""
    actif = models.BooleanField(default=False, verbose_name="Happy hour activé")
    debut = models.TimeField(default=datetime.time(22, 30), verbose_name="Début")
    fin = models.TimeField(default=datetime.time(23, 30), verbose_name="Fin",
                           help_text="Si la fin est avant le début, la plage passe minuit.")

    class Meta:
        verbose_name = "Happy hour"

    def __str__(self):
        etat = "activé" if self.actif else "désactivé"
        return f"Happy hour {self.debut:%H:%M}–{self.fin:%H:%M} ({etat})"


class HappyHourPrice(models.Model):
    """Prix happy hour d'un article. Absent = l'article garde son prix normal."""
    article = models.OneToOneField('APIcashless.Articles', on_delete=models.CASCADE,
                                   related_name='happy_hour_price', verbose_name="Article")
    prix = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)],
                               verbose_name="Prix happy hour")

    class Meta:
        verbose_name = "Prix happy hour"
        verbose_name_plural = "Prix happy hour"

    def __str__(self):
        return f"{self.article} : {self.prix} €"
