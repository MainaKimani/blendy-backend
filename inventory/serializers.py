from rest_framework import serializers
from .models import (
    Location, InventoryItem,
    StockMovement, StockTake, StockTakeItem
)
from products.models import Product, ProductVariation

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = '__all__'
        read_only_fields = ('organization',)

class InventoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        fields = '__all__'
        # available_quantity is a cache of SUM(StockMovement.quantity). Writing it
        # directly would let the balance drift from the ledger that is supposed to
        # explain it, so stock only moves through the restock/adjust endpoints.
        read_only_fields = ('organization', 'available_quantity')

class StockMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = '__all__'
        # Tenancy comes from the X-Organization header via OrganizationMiddleware
        # and is applied by OrganizationBaseViewSet.perform_create. Leaving it
        # writable made it a required body field, so the endpoint 400'd on a
        # value the client should never be setting.
        read_only_fields = ('organization',)

class StockTakeItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockTakeItem
        fields = '__all__'
        read_only_fields = ('organization',)

class StockTakeSerializer(serializers.ModelSerializer):
    items = StockTakeItemSerializer(many=True, read_only=True)

    class Meta:
        model = StockTake
        fields = '__all__'
        read_only_fields = ('organization',)


class LowStockItemSerializer(serializers.ModelSerializer):
    """US-3: a variation that has reached the threshold its owner set."""

    product_variation_id = serializers.UUIDField(
        source="product_variation.id", read_only=True
    )
    name = serializers.CharField(source="product_variation.name", read_only=True)
    sku = serializers.CharField(source="product_variation.sku", read_only=True)
    reorder_level = serializers.IntegerField(
        source="product_variation.reorder_level", read_only=True
    )
    location_name = serializers.CharField(source="location.name", read_only=True)
    shortfall = serializers.SerializerMethodField()

    class Meta:
        model = InventoryItem
        fields = (
            "id",
            "product_variation_id",
            "name",
            "sku",
            "location",
            "location_name",
            "available_quantity",
            "reorder_level",
            "shortfall",
        )

    def get_shortfall(self, obj):
        """How far below the threshold this has fallen; 0 when exactly on it."""
        return max(0, obj.product_variation.reorder_level - obj.available_quantity)


class RestockSerializer(serializers.Serializer):
    """US-17: record new stock arriving, without full supplier/PO management."""

    product_variation = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariation.objects.all()
    )
    quantity = serializers.IntegerField(min_value=1)
    # Captured now even though MVP reporting does not use it yet: retrofitting a
    # cost per unit onto movements that never recorded one would mean
    # reconstructing history for Phase 2 margin reporting (MVP §10.5).
    unit_cost = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    location = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(), required=False, allow_null=True
    )
    reference_number = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class StockAdjustmentSerializer(serializers.Serializer):
    """US-19: correct a stock figure, with a reason that is never optional."""

    product_variation = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariation.objects.all()
    )
    # Either a signed delta ("two broke") or the figure from a physical count.
    quantity = serializers.IntegerField(required=False)
    counted_quantity = serializers.IntegerField(required=False, min_value=0)
    # Required: an unexplained adjustment is exactly what the ledger exists to
    # prevent, so shrinkage and counting errors stay visible.
    reason = serializers.CharField(allow_blank=False)
    location = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(), required=False, allow_null=True
    )

    def validate(self, attrs):
        has_delta = attrs.get("quantity") is not None
        has_count = attrs.get("counted_quantity") is not None

        if has_delta == has_count:
            raise serializers.ValidationError(
                "Provide exactly one of 'quantity' (a signed change) or "
                "'counted_quantity' (the figure counted on the shelf)."
            )
        if has_delta and attrs["quantity"] == 0:
            raise serializers.ValidationError(
                {"quantity": "A stock adjustment cannot be zero."}
            )
        return attrs
