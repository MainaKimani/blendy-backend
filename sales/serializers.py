from rest_framework import serializers
from .models import Sale, SaleItem
from inventory.models import AgentInventoryItem
from products.models import ProductVariation
from django.db import transaction

class SaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = '__all__'
        read_only_fields = ('total_price', 'sale',)

class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Sale
        fields = '__all__'
        read_only_fields = ('created_by', 'updated_by', 'organization')

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        created_by = self.context['request'].user
        organization = self.context['request'].organization

        with transaction.atomic():
            # Check and decrement agent inventory before creating sale items
            for item_data in items_data:
                product_variation = item_data.get('product_variation')
                quantity = item_data.get('quantity')

                try:
                    agent_inventory = AgentInventoryItem.objects.select_for_update().get(
                        agent=created_by,
                        product_variation=product_variation,
                        organization=organization
                    )
                except AgentInventoryItem.DoesNotExist:
                    raise serializers.ValidationError(f"Product variation {product_variation.name} not found in agent's inventory.")

                if agent_inventory.quantity < quantity:
                    raise serializers.ValidationError(f"Not enough stock for {product_variation.name} in agent's inventory. Available: {agent_inventory.quantity}, Requested: {quantity}")

                agent_inventory.quantity -= quantity
                agent_inventory.save()

            sale = Sale.objects.create(created_by=created_by, organization=organization, **validated_data)

            for item_data in items_data:
                # Calculate total_price for each SaleItem
                quantity = item_data.get('quantity')
                unit_price = item_data.get('unit_price')
                discount = item_data.get('discount', 0.00)
                item_total_price = (quantity * unit_price) - discount
                item_data['total_price'] = item_total_price
                SaleItem.objects.create(sale=sale, **item_data)
        return sale

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items')
        updated_by = self.context['request'].user
        organization = self.context['request'].organization

        with transaction.atomic():
            # Revert old inventory quantities (simplified: assumes old items are fully replaced)
            for old_item in instance.items.all():
                try:
                    agent_inventory = AgentInventoryItem.objects.select_for_update().get(
                        agent=instance.created_by, # Assuming the same agent for the sale
                        product_variation=old_item.product_variation,
                        organization=organization
                    )
                    agent_inventory.quantity += old_item.quantity
                    agent_inventory.save()
                except AgentInventoryItem.DoesNotExist:
                    # Log or handle case where old inventory item is missing
                    pass

            # Clear existing items and recreate
            instance.items.all().delete()

            # Check and decrement new agent inventory
            for item_data in items_data:
                product_variation = item_data.get('product_variation')
                quantity = item_data.get('quantity')

                try:
                    agent_inventory = AgentInventoryItem.objects.select_for_update().get(
                        agent=updated_by,
                        product_variation=product_variation,
                        organization=organization
                    )
                except AgentInventoryItem.DoesNotExist:
                    raise serializers.ValidationError(f"Product variation {product_variation.name} not found in agent's inventory.")

                if agent_inventory.quantity < quantity:
                    raise serializers.ValidationError(f"Not enough stock for {product_variation.name} in agent's inventory. Available: {agent_inventory.quantity}, Requested: {quantity}")

                agent_inventory.quantity -= quantity
                agent_inventory.save()

            # Update Sale fields
            instance.customer_name = validated_data.get('customer_name', instance.customer_name)
            instance.updated_by = updated_by
            instance.save()

            for item_data in items_data:
                quantity = item_data.get('quantity')
                unit_price = item_data.get('unit_price')
                discount = item_data.get('discount', 0.00)
                item_total_price = (quantity * unit_price) - discount
                item_data['total_price'] = item_total_price
                SaleItem.objects.create(sale=instance, **item_data)
        return instance
