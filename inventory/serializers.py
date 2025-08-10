from rest_framework import serializers
from .models import (
    Location, InventoryItem, 
    StockMovement, StockTake, StockTakeItem, AgentInventoryItem
)
from products.models import Product, ProductVariation

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = '__all__'

class InventoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        fields = '__all__'
        read_only_fields = ('organization',)

class StockMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = '__all__'

class StockTakeItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockTakeItem
        fields = '__all__'

class StockTakeSerializer(serializers.ModelSerializer):
    items = StockTakeItemSerializer(many=True, read_only=True)

    class Meta:
        model = StockTake
        fields = '__all__'

class AgentInventoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentInventoryItem
        fields = '__all__'
