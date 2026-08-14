from rest_framework import serializers
from .models import Pricelist, PricelistItem

class PricelistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pricelist
        fields = '__all__'
        read_only_fields = ('organization',)

class PricelistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricelistItem
        fields = '__all__'
        read_only_fields = ('organization',)
