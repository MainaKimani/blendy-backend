from rest_framework import serializers
from django.db import transaction

from payments.serializers import PaymentSerializer
from .models import Sale, SaleItem


class SaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = "__all__"
        read_only_fields = (
            "total_price",
            "sale",
        )


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)
    total_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Sale
        fields = (
            "id",
            "customer_name",
            "sale_date",
            "shipping_fee",
            "status",
            "payment_status",
            "customer_email",
            "customer_phone",
            "shipping_city",
            "shipping_address",
            "items",
            "payments",
            "total_amount",
        )

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        request = self.context.get("request")

        with transaction.atomic():
            # Create the sale record
            sale = Sale.objects.create(**validated_data)

            # Create each SaleItem associated with this sale
            for item_data in items_data:
                quantity = item_data.get("quantity")
                unit_price = item_data.get("unit_price")
                discount = item_data.get("discount", 0.00)

                # Calculate the line total
                line_total = (quantity * unit_price) - discount

                SaleItem.objects.create(sale=sale, total_price=line_total, **item_data)

        return sale
    
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
    
        with transaction.atomic():
            # Update the Sale fields
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
    
            if items_data is not None:
                # Delete existing items and recreate
                instance.items.all().delete()
    
                for item_data in items_data:
                    quantity = item_data.get("quantity")
                    unit_price = item_data.get("unit_price")
                    discount = item_data.get("discount", 0.00)
                    line_total = (quantity * unit_price) - discount
    
                    SaleItem.objects.create(sale=instance, total_price=line_total, **item_data)
    
        return instance
