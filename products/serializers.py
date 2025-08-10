from rest_framework import serializers
from .models import Product, Category, ProductVariation
from pricing.models import PricelistItem

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'
        read_only_fields = ('organization',)

class ProductVariationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariation
        fields = ('id', 'product', 'name', 'sku', 'cost_price', 'unit_of_measure', 'is_active', 'created_at', 'updated_at', 'organization')
        read_only_fields = ('organization',)

class ProductSerializer(serializers.ModelSerializer):
    variations = ProductVariationSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ('organization',)

class ProductVariationWithPriceSerializer(ProductVariationSerializer):
    price = serializers.SerializerMethodField()

    class Meta(ProductVariationSerializer.Meta):
        fields = ProductVariationSerializer.Meta.fields + ('price',)

    def get_price(self, obj):
        pricelist_id = self.context.get('pricelist_id')
        if pricelist_id:
            try:
                pricelist_item = PricelistItem.objects.get(product_variation=obj, pricelist_id=pricelist_id)
                return pricelist_item.price
            except PricelistItem.DoesNotExist:
                return None
        return None

class ProductWithPriceSerializer(ProductSerializer):
    variations = ProductVariationWithPriceSerializer(many=True, read_only=True)

    def to_representation(self, instance):
        pricelist_id = self.context.get('request').query_params.get('pricelist_id')
        self.context['pricelist_id'] = pricelist_id
        return super().to_representation(instance)
