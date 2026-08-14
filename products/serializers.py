from rest_framework import serializers
from django.db import transaction
from .models import Product, Category, ProductImage, ProductVariation, Currency, UOM
from pricing.models import PricelistItem
from pricing.services import (
    PricelistUnavailable,
    get_default_pricelist,
    get_price,
    require_default_pricelist,
    set_price,
)


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
    # The selling price is not a property of the variation: it is written to the
    # organization's default pricelist, which is what sales are priced from.
    selling_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, write_only=True
    )
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
            "selling_price",
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
        # Handled by the viewset, which has the tenant needed to resolve the
        # pricelist the price belongs on.
        raise NotImplementedError(
            "Create variations through ProductVariationViewSet."
        )

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
    # Written to the default pricelist rather than to the variation itself.
    selling_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, write_only=True
    )
    # Read back from whichever pricelist applies.
    price = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariation
        fields = (
            "id",
            "name",
            "sku",
            "cost_price",
            "selling_price",
            "price",
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

    def get_price(self, obj):
        """The variation's price on the organization's default pricelist."""
        pricelist = get_default_pricelist(obj.organization)
        return get_price(pricelist, obj) if pricelist is not None else None


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
    # A product is not sellable without at least one priced variation, so an
    # empty list is refused rather than creating an unsellable product.
    variations = ProductVariationSerializer(
        many=True, required=True, allow_empty=False
    )
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

        # Prices land on the default pricelist, so it has to exist. Refusing here
        # is the same rule sales apply: without a pricelist, nothing can trade.
        try:
            pricelist = require_default_pricelist(product.organization)
        except PricelistUnavailable as exc:
            raise serializers.ValidationError({"variations": str(exc)}) from exc

        # Create the variations, recording each price on the pricelist
        for variation_data in variations_data:
            selling_price = variation_data.pop("selling_price")
            variation = ProductVariation.objects.create(
                product=product, organization=product.organization, **variation_data
            )
            set_price(
                organization=product.organization,
                pricelist=pricelist,
                product_variation=variation,
                price=selling_price,
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
    """Resolves price against an explicitly requested list, not the default."""

    class Meta(ProductVariationSerializer.Meta):
        pass

    def get_price(self, obj):
        pricelist_id = self.context.get("pricelist_id")
        if not pricelist_id:
            return None

        pricelist_item = PricelistItem.objects.filter(
            product_variation=obj,
            pricelist_id=pricelist_id,
            # pricelist_id is client-supplied, so scope it to the variation's
            # tenant rather than trusting it to name a pricelist we own.
            organization_id=obj.organization_id,
        ).first()
        return pricelist_item.price if pricelist_item is not None else None


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
