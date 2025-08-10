I have implemented the following changes to the Blendy backend:

**1. Product Variations and Price Lists:**

*   **`ProductVariation` Model:** Introduced a new `ProductVariation` model in `products/models.py` to allow products to have different sizes, weights, and other attributes. The `cost_price` and `unit_of_measure` fields were moved from the `Product` model to `ProductVariation`.
*   **`pricing` App:** Created a new Django app named `pricing` to manage price lists.
*   **`Pricelist` Model:** Added a `Pricelist` model in `pricing/models.py` to define different pricing tiers (e.g., "Retail", "Wholesale").
*   **`PricelistItem` Model:** Added a `PricelistItem` model in `pricing/models.py` to link `ProductVariation` instances to `Pricelist` instances with a specific `price`.
*   **Migrations:** Created and applied new database migrations for both `products` and `pricing` apps to reflect these model changes.
*   **Serializers:**
    *   Updated `products/serializers.py` to include `ProductVariationSerializer` and to make the `organization` field read-only in `CategorySerializer`, `ProductSerializer`, and `ProductVariationSerializer`.
    *   Created `pricing/serializers.py` with `PricelistSerializer` and `PricelistItemSerializer`, making the `organization` field read-only in `PricelistSerializer`.
    *   Introduced `ProductVariationWithPriceSerializer` and `ProductWithPriceSerializer` in `products/serializers.py` to allow fetching product variations with their prices based on a specified pricelist.
*   **Views:**
    *   Updated `products/views.py` to include `ProductVariationViewSet` and `ProductWithPriceViewSet`.
    *   Created `pricing/views.py` with `PricelistViewSet` and `PricelistItemViewSet`.
    *   Temporarily removed permission checks from `CategoryViewSet`, `ProductViewSet`, `ProductVariationViewSet`, `PricelistViewSet`, and `PricelistItemViewSet` for testing purposes, and then restored them.
*   **URLs:**
    *   Updated `products/urls.py` to include URLs for `ProductVariationViewSet` and `ProductWithPriceViewSet`.
    *   Created `pricing/urls.py` with URLs for `PricelistViewSet` and `PricelistItemViewSet`.
    *   Included `pricing.urls` in the main `blendy_backend/urls.py`.
*   **Testing:** Successfully tested the creation of categories, products, product variations, pricelists, and pricelist items. Also tested the new endpoint to list products with prices for a given pricelist.

**2. Sales and Discounts:**

*   **`Sale` Model:** Created a new `Sale` model in `sales/models.py` to represent sales transactions. This model now includes `created_by` and `updated_by` fields to track the user who created or last updated the sale. The `total_amount` field was removed and is now a calculated property.
*   **`SaleItem` Model:** Created a new `SaleItem` model in `sales/models.py` to represent individual items within a sale. This model includes a `discount` field to allow for item-level discounts.
*   **Migrations:** Created and applied new database migrations for the `sales` app to reflect these model changes.
*   **Serializers:**
    *   Updated `sales/serializers.py` to include `SaleSerializer` and `SaleItemSerializer`.
    *   The `SaleSerializer` handles nested creation and updates of `SaleItem` instances.
    *   The `created_by`, `updated_by`, and `organization` fields in `SaleSerializer` are read-only. The `total_amount` is now a `ReadOnlyField`.
    *   The `total_price` and `sale` fields in `SaleItemSerializer` are read-only.
*   **Views:**
    *   Updated `sales/views.py` to include `SaleViewSet` and `SaleItemViewSet`.
    *   The `RecordSaleView` was removed as its functionality is now handled by `SaleViewSet`.
    *   The `perform_create` and `perform_update` methods in `SaleViewSet` automatically set the `created_by` and `updated_by` fields based on the requesting user.
    *   Temporarily removed permission checks from `SaleViewSet` and `SaleItemViewSet` for testing purposes, and then restored them.
*   **URLs:** Updated `sales/urls.py` to include URLs for `SaleViewSet` and `SaleItemViewSet`, and removed the URL for `RecordSaleView`.
*   **Testing:** Successfully tested the creation of a sale with a discounted item, confirming the `total_amount` is correctly calculated as a property.

These changes provide a robust foundation for managing product variations, flexible pricing, and detailed sales records with discount capabilities, adhering to the specified sales logic.