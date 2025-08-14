from rest_framework import serializers
from django.db import transaction
from .models import Product, Category, ProductVariation, Currency, UOM
from pricing.models import PricelistItem

class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = '__all__'
        read_only_fields = ('organization',)

class UOMSerializer(serializers.ModelSerializer):
    class Meta:
        model = UOM
        fields = '__all__'
        read_only_fields = ('organization',)

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'
        read_only_fields = ('organization',)

class ProductVariationSerializer(serializers.ModelSerializer):
    uom = UOMSerializer(read_only=True)
    uom_id = serializers.UUIDField(write_only=True, source='uom')
    currency = CurrencySerializer(read_only=True)
    currency_id = serializers.UUIDField(write_only=True, source='currency')
    name = serializers.CharField(read_only=True)

    class Meta:
        model = ProductVariation
        fields = ('id', 'name', 'sku', 'cost_price', 'uom', 'uom_id', 'currency', 'currency_id', 'color', 'pack_size', 'measurement', 'size', 'is_active', 'created_at', 'updated_at', 'organization')
        read_only_fields = ('organization', 'uom', 'currency')

class ProductSerializer(serializers.ModelSerializer):
    variations = ProductVariationSerializer(many=True)
    category = CategorySerializer(read_only=True)
    category_id = serializers.UUIDField(write_only=True, source='category')

    class Meta:
        model = Product
        fields = ('id', 'name', 'sku', 'description', 'category', 'category_id', 'reorder_level', 'is_active', 'barcode', 'created_at', 'updated_at', 'created_by', 'variations', 'organization')
        read_only_fields = ('organization', 'category')

    def create(self, validated_data):
        variations_data = validated_data.pop('variations')
        with transaction.atomic():
            product = Product.objects.create(**validated_data)
            for variation_data in variations_data:
                ProductVariation.objects.create(product=product, organization=product.organization, **variation_data)
        return product

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


class ProductDetailSerializer(ProductSerializer):
    variations = ProductVariationSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)

    class Meta(ProductSerializer.Meta):
        pass
