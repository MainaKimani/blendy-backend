from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from users.models import SalesAgentProfile, CustomUser
from .models import Sale, SaleItem
from .serializers import SaleSerializer, SaleItemSerializer
from users.serializers import SalesAgentProfileSerializer
from inventory.models import InventoryItem, StockMovement, AgentInventoryItem
from products.models import Product, ProductVariation
from inventory.views import OrganizationBaseViewSet
from users.permissions import IsOrganizationUser, HasUserPermission


class SalesAgentProfileViewSet(OrganizationBaseViewSet):
    """
    A viewset for viewing and editing sales agent profiles.
    """

    queryset = SalesAgentProfile.objects.all()
    serializer_class = SalesAgentProfileSerializer

    def get_permissions(self):
        if self.action == "list" or self.action == "retrieve":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                HasUserPermission("sales.view_salesagentprofile"),
            ]
        elif self.action == "create":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                HasUserPermission("sales.add_salesagentprofile"),
            ]
        elif self.action == "update" or self.action == "partial_update":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                HasUserPermission("sales.change_salesagentprofile"),
            ]
        elif self.action == "destroy":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                HasUserPermission("sales.delete_salesagentprofile"),
            ]
        return [IsAuthenticated(), IsOrganizationUser()]


class IssueStockToAgentView(APIView):
    def get_permissions(self):
        return []

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        product_variation_id = request.data.get("product_variation_id")
        agent_id = request.data.get("agent_id")
        location_id = request.data.get("location_id")
        quantity = int(request.data.get("quantity", 0))

        if not all([product_variation_id, agent_id, location_id, quantity > 0]):
            return Response(
                {"error": "Missing required fields or invalid quantity."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Lock the inventory item row to prevent race conditions
            inventory_item = InventoryItem.objects.select_for_update().get(
                product_variation=product_variation_id,
                location_id=location_id,
                organization=request.organization,
            )

            if inventory_item.available_quantity < quantity:
                return Response(
                    {"error": "Not enough stock available in the warehouse."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            agent = CustomUser.objects.get(
                id=agent_id, organization=request.organization
            )
            product_variation = ProductVariation.objects.get(
                id=product_variation_id, organization=request.organization
            )

            # Decrease warehouse stock
            inventory_item.available_quantity -= quantity
            inventory_item.save()

            # Increase agent's stock
            agent_inventory, created = AgentInventoryItem.objects.get_or_create(
                agent=agent,
                product_variation=product_variation,
                organization=request.organization,
                defaults={"quantity": 0},
            )
            agent_inventory.quantity += quantity
            agent_inventory.save()

            # Create a stock movement record for auditing
            StockMovement.objects.create(
                organization=request.organization,
                product_variation=product_variation,
                location_id=location_id,
                movement_type="PICK",
                quantity=quantity,
                notes=f"Issued to agent {agent.username}",
                created_by=request.user,
            )

            return Response(
                {
                    "success": f"Successfully issued {quantity} of {product_variation.name} to {agent.username}."
                },
                status=status.HTTP_200_OK,
            )

        except InventoryItem.DoesNotExist:
            return Response(
                {"error": "Inventory item not found at this location."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "Sales agent not found."}, status=status.HTTP_404_NOT_FOUND
            )
        except ProductVariation.DoesNotExist:
            return Response(
                {"error": "Product variation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer

    def perform_create(self, serializer):
        # If user is anonymous, created_by will be None, which matches your model
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save()

    def get_permissions(self):
        # Allow guests to POST (checkout), but require Auth to GET/PUT/PATCH
        if self.action == "create":
            return []
        return []


class SaleItemViewSet(viewsets.ModelViewSet):
    queryset = SaleItem.objects.all()
    serializer_class = SaleItemSerializer

    def get_permissions(self):
        return [IsAuthenticated()]
