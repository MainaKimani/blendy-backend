from django_filters import rest_framework as filters
from .models import Product


# This helper class allows you to pass a comma-separated list in the URL
class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    pass


class ProductFilter(filters.FilterSet):
    # 'gte' = Greater than or equal to
    # 'lte' = Less than or equal to
    # Price lives on the pricelist now, so filter across the product's priced
    # variations. distinct() because a product with several priced variations
    # would otherwise be returned once per match.
    min_price = filters.NumberFilter(
        field_name="variations__pricelist_items__price",
        lookup_expr="gte",
        distinct=True,
    )
    max_price = filters.NumberFilter(
        field_name="variations__pricelist_items__price",
        lookup_expr="lte",
        distinct=True,
    )

    # Filter by a list of IDs: ?category_ids=1,2,3
    categories = CharInFilter(field_name="category__id", lookup_expr="in")

    # 'icontains' = Case-insensitive partial match
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")

    tag = filters.CharFilter(field_name="tags", lookup_expr="icontains")

    sizes = CharInFilter(field_name="variations__size", lookup_expr="in")

    # Filtering by date ranges
    created_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")

    class Meta:
        model = Product
        # You can still include standard exact matches here
        fields = ["category", "sizes", "is_active"]

    @property
    def get_queryset(self):
    # .distinct() is vital here so the 'count' in pagination is accurate
        return (
            Product.objects.all()
            .select_related("category")
            .prefetch_related("images", "variations")
            .distinct()
        )



