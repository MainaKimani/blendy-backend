from rest_framework import serializers
from django.db import transaction
from .models import Product, Category, ProductImage, ProductVariation, Currency, UOM
from pricing.models import PricelistItem
from django.db import transaction


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = "__all__"
        read_only_fields = ("organization",)


class UOMSerializer(serializers.ModelSerializer):
    class Meta:
        model = UOM
        fields = "__all__"
        read_only_fields = ("organization",)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"
        read_only_fields = ("organization",)


class ProductVariationSerializer(serializers.ModelSerializer):
    uom = UOMSerializer(read_only=True)
    uom_id = serializers.UUIDField(read_only=True, source="uom")
    currency = CurrencySerializer(read_only=True)
    currency_id = serializers.UUIDField(read_only=True, source="currency")
    name = serializers.CharField(read_only=True)
    product_id = serializers.UUIDField(read_only=True, source="product")

    class Meta:
        model = ProductVariation
        fields = (
            "id",
            "name",
            "sku",
            "cost_price",
            "uom",
            "uom_id",
            "currency",
            "currency_id",
            "color",
            "pack_size",
            "measurement",
            "size",
            "reorder_level",
            "barcode",
            "is_active",
            "created_at",
            "updated_at",
            "organization",
            "product_id",
        )
        read_only_fields = ("organization", "uom", "currency")


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        exclude = ("product",)


class ProductSerializer(serializers.ModelSerializer):
    variations = ProductVariationSerializer(many=True, required=False)
    images = ProductImageSerializer(many=True, required=False)
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source="category",
        write_only=True,
    )

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "sku",
            "images",
            "description",
            "category",
            "category_id",
            "is_active",
            "created_at",
            "updated_at",
            "created_by",
            "variations",
            "organization",
        )
        read_only_fields = ("organization", "category")

    @transaction.atomic
    def create(self, validated_data):
        variations_data = validated_data.pop("variations", [])
        images_data = validated_data.pop("images", [])

        # Create the product first
        product = Product.objects.create(**validated_data)

        # Create the variations
        for variation_data in variations_data:
            ProductVariation.objects.create(
                product=product, organization=product.organization, **variation_data
            )

        # Create images
        for image_data in images_data:
            ProductImage.objects.create(
                product=product, organization=product.organization, **image_data
            )

        return product


class ProductVariationWithPriceSerializer(ProductVariationSerializer):
    price = serializers.SerializerMethodField()

    class Meta(ProductVariationSerializer.Meta):
        fields = ProductVariationSerializer.Meta.fields + ("price",)

    def get_price(self, obj):
        pricelist_id = self.context.get("pricelist_id")
        if pricelist_id:
            try:
                pricelist_item = PricelistItem.objects.get(
                    product_variation=obj, pricelist_id=pricelist_id
                )
                return pricelist_item.price
            except PricelistItem.DoesNotExist:
                return None
        return None


class ProductWithPriceSerializer(ProductSerializer):
    variations = ProductVariationWithPriceSerializer(many=True, read_only=True)

    def to_representation(self, instance):
        pricelist_id = self.context.get("request").query_params.get("pricelist_id")
        self.context["pricelist_id"] = pricelist_id
        return super().to_representation(instance)


class ProductDetailSerializer(ProductSerializer):
    variations = ProductVariationSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)

    class Meta(ProductSerializer.Meta):
        pass
