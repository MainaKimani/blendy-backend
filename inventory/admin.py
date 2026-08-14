from django.contrib import admin

from .models import InventoryItem, Location, StockMovement

admin.site.register(Location)
admin.site.register(InventoryItem)
admin.site.register(StockMovement)
