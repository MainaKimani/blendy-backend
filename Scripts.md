Scripts


## Creating an org
org = Organization.objects.create(
    name="Mitchy Fits",
    slug="mitchy-fits",
    domain="mitchyfits.co.ke",
    business_type="ecommerce",
    contact_email="info@mitchyfits.co.ke",
    contact_phone="+254700000000",
    address="Nairobi, Kenya",
    tax_number="P051234567X",
)

org = Organization.objects.get(slug="mitchy-fits")

## Create a super user not tied to an org
user = CustomUser.objects.create_superuser(
    email="kalexmaina@gmail.com",
    username="Superadmin",
    password="pass@12345"
)

## Create a super user tied to an org
from users.models import CustomUser
from organization.models import Organization

org = Organization.objects.get(slug="blendy-technologies")

user = CustomUser.objects.create_superuser(
    email="alxmaish@gmail.com",
    username="Admin",
    password="pass@12345",
    organization=org
)

user