from django.contrib import admin
from .models import Pricelist, PricelistItem

admin.site.register(Pricelist)
admin.site.register(PricelistItem)