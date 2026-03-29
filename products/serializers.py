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


class ProductVariationWriteSerializer(serializers.ModelSerializer):
    uom_id = serializers.PrimaryKeyRelatedField(
        queryset=UOM.objects.all(), source="uom", write_only=True, required=False
    )
    currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(),
        source="currency",
        write_only=True,
        required=False,
    )
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source="product", write_only=True
    )

    class Meta:
        model = ProductVariation
        fields = (
            "id",
            "sku",
            "cost_price",
            "uom_id",
            "currency_id",
            "color",
            "pack_size",
            "measurement",
            "size",
            "reorder_level",
            "barcode",
            "is_active",
            "product_id",
        )

    def create(self, validated_data):
        if isinstance(validated_data, list):
            return ProductVariation.objects.bulk_create(
                [ProductVariation(**item) for item in validated_data]
            )
        return ProductVariation.objects.create(**validated_data)

    def update(self, instance, validated_data):
        # single update
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


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
        exclude = ("product", "organization")


class ProductImageWritableSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source="product",
        write_only=True
    )
    images = ProductImageSerializer(many=True, required=False)
    class Meta:
        model = ProductImage
        fields = ["product_id", "images"]

    @transaction.atomic
    def create(self, validated_data):
        images_data = validated_data.pop("images", [])

        # get the product first
        product = validated_data.get("product")

        for image_data in images_data:
            ProductImage.objects.create(
                product=product, organization=product.organization, **image_data
            )

        return product


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, required=False)
    category = CategorySerializer(read_only=True)
    variations = ProductVariationSerializer(many=True, required=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source="category",
    )
    available_sizes = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    other_images = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "images",
            "description",
            "category",
            "price",
            "category_id",
            "is_active",
            "created_at",
            "updated_at",
            "created_by",
            "variations",
            "primary_image",
            "other_images",
            "available_sizes",
            "tags",
        )
        read_only_fields = ("category", "available_sizes")

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

    def get_available_sizes(self, obj):
        return obj.variations.values_list("size", flat=True)

    def get_primary_image(self, obj):
        primary_image = obj.images.filter(is_primary=True).first()
        if primary_image:
            return primary_image.image.url
        return None

    def get_other_images(self, obj):
        other_images = obj.images.filter(is_primary=False)
        return [image.image.url for image in other_images]


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
