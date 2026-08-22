from decimal import Decimal

from rest_framework import serializers
from django.db import transaction
from django.db.models import prefetch_related_objects

from inventory.services import (
    InsufficientStock,
    get_default_location,
    record_movement,
)
from payments.serializers import PaymentSerializer
from pricing.services import (
    PricelistUnavailable,
    VariationNotPriced,
    get_prices,
    require_default_pricelist,
)
from .models import Sale, SaleItem


class SaleItemSerializer(serializers.ModelSerializer):
    # The variation is what is written; the parent product is still exposed on
    # read so existing clients keep the response shape they had. Read from the
    # variation's product_id column rather than by traversing to the Product
    # itself: the id is what is emitted either way, and the traversal cost a
    # query per line.
    product = serializers.UUIDField(
        source="product_variation.product_id", read_only=True
    )

    class Meta:
        model = SaleItem
        fields = "__all__"
        read_only_fields = (
            "total_price",
            "sale",
            "organization",
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

    def _price_line(self, item_data, product_variation, user, pricelist, prices):
        """Verify the submitted prices against the pricelist.

        Prices are never taken on trust: unit_price must equal the variation's
        price on the pricelist exactly, and selling_price must equal unit_price
        minus the discount exactly. Any concession therefore has to be declared
        in the discount field, where it stays visible, rather than hidden in a
        reduced unit price. Returns (unit_price, discount, selling_price, total).
        """
        quantity = item_data.get("quantity")
        unit_price = item_data.get("unit_price")
        discount = item_data.get("discount") or Decimal("0.00")
        selling_price = item_data.get("selling_price")

        catalogue_price = prices.get(product_variation.id)
        if catalogue_price is None:
            raise serializers.ValidationError(
                {"items": str(VariationNotPriced(product_variation, pricelist))}
            )

        if unit_price is None:
            unit_price = catalogue_price
        if unit_price != catalogue_price:
            raise serializers.ValidationError(
                {
                    "items": (
                        f"unit_price {unit_price} does not match the price "
                        f"{catalogue_price} on '{pricelist.name}' for "
                        f"{product_variation.name}."
                    )
                }
            )

        if discount < Decimal("0.00"):
            raise serializers.ValidationError({"items": "discount cannot be negative."})
        if discount > unit_price:
            raise serializers.ValidationError(
                {
                    "items": (
                        f"discount {discount} exceeds the unit price {unit_price}; "
                        "a line cannot be worth less than nothing."
                    )
                }
            )
        if discount and user is None:
            # Guest checkout stays open, but it cannot grant itself money off.
            raise serializers.ValidationError(
                {"items": "A discount may only be applied by a signed-in user."}
            )

        expected_selling_price = unit_price - discount
        if selling_price is None:
            selling_price = expected_selling_price
        if selling_price != expected_selling_price:
            raise serializers.ValidationError(
                {
                    "items": (
                        f"selling_price {selling_price} does not equal unit_price "
                        f"{unit_price} minus discount {discount}."
                    )
                }
            )

        return unit_price, discount, selling_price, quantity * selling_price

    def _build_items(self, sale, items_data, user):
        """Create the sale's lines, resolving what they all share only once.

        The pricelist lookup and the stock location are identical for every line
        of a sale, so they are resolved for the basket rather than per line.
        """
        variations = [item_data["product_variation"] for item_data in items_data]
        prices = get_prices(sale.pricelist, variations)
        location = get_default_location(sale.organization)

        return [
            self._build_item(sale, item_data, user, prices, location)
            for item_data in items_data
        ]

    def _build_item(self, sale, item_data, user, prices, location):
        """Create one sale line and move its stock out of the ledger."""
        product_variation = item_data["product_variation"]

        if product_variation.organization_id != sale.organization_id:
            raise serializers.ValidationError(
                {"items": "Product variation does not belong to this organization."}
            )

        unit_price, discount, selling_price, line_total = self._price_line(
            item_data, product_variation, user, sale.pricelist, prices
        )
        quantity = item_data.get("quantity")

        item = SaleItem.objects.create(
            sale=sale,
            organization=sale.organization,
            product_variation=product_variation,
            quantity=quantity,
            unit_price=unit_price,
            discount=discount,
            selling_price=selling_price,
            # Snapshotted so the margin on this sale stays computable even after
            # the variation's cost is updated.
            cost_price=product_variation.cost_price,
            total_price=line_total,
        )

        try:
            record_movement(
                organization=sale.organization,
                product_variation=product_variation,
                movement_type="SALE",
                quantity=-quantity,
                location=location,
                user=user,
                reference_number=str(sale.id),
                notes=f"Sale {sale.id}",
            )
        except InsufficientStock as exc:
            raise serializers.ValidationError({"items": str(exc)}) from exc

        return item

    def _reverse_item_stock(self, item, user, location):
        """Return a sale line's stock to the ledger when the line is removed."""
        record_movement(
            organization=item.organization,
            product_variation=item.product_variation,
            movement_type="ADJUSTMENT",
            quantity=item.quantity,
            location=location,
            user=user,
            reference_number=str(item.sale_id),
            notes=f"Reversal of edited sale {item.sale_id}",
            # A correction must always be recordable, even if later movements
            # already took the balance down.
            allow_negative=True,
        )

    def _current_user(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return user if user is not None and user.is_authenticated else None

    def _require_pricelist(self, organization):
        try:
            return require_default_pricelist(organization)
        except PricelistUnavailable as exc:
            raise serializers.ValidationError({"pricelist": str(exc)}) from exc

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        user = self._current_user()

        with transaction.atomic():
            # Resolved before anything is written: without a pricelist there is
            # no price to sell at, so the sale must not happen at all.
            validated_data["pricelist"] = self._require_pricelist(
                validated_data["organization"]
            )
            sale = Sale.objects.create(**validated_data)
            self._build_items(sale, items_data, user)

        # Populate the caches the response then reads, in a fixed number of
        # queries rather than one per line. Without this the created sale is a
        # bare instance, so serializing it walks back to the database for its
        # lines, again for total_amount, and once per line for the variation.
        prefetch_related_objects(
            [sale], "items__product_variation", "payments__transactions"
        )
        return sale
    
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        user = self._current_user()

        with transaction.atomic():
            # Update the Sale fields
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            if items_data is not None:
                # An edit reprices against the list the sale was made on, or the
                # current default for sales that predate pricelists.
                if instance.pricelist is None:
                    instance.pricelist = self._require_pricelist(
                        instance.organization
                    )
                    instance.save(update_fields=["pricelist"])

                # Replacing the lines has to put the old lines' stock back,
                # otherwise every edit silently loses inventory. Interim
                # behaviour: once eTIMS submission exists, an invoiced sale must
                # be corrected by credit note instead of being edited at all.
                location = get_default_location(instance.organization)
                for existing in instance.items.select_related("product_variation"):
                    self._reverse_item_stock(existing, user, location)
                instance.items.all().delete()

                self._build_items(instance, items_data, user)

        return instance
