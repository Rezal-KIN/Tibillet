from django.contrib import admin
from solo.admin import SingletonModelAdmin

from administration.adminstaff import staff_admin_site
from happy_hour_laboutik.models import HappyHour, HappyHourPrice


class HappyHourPriceInline(admin.StackedInline):
    model = HappyHourPrice
    extra = 0
    max_num = 1
    can_delete = True
    verbose_name = "Prix happy hour (laisser vide : pas de happy hour pour cet article)"
    verbose_name_plural = verbose_name


class HappyHourAdmin(SingletonModelAdmin):
    fields = ('actif', 'debut', 'fin')


staff_admin_site.register(HappyHour, HappyHourAdmin)
