---

## Blendy Backend Documentation

### 1. Project Overview

**Project Name:** Blendy Backend

**Purpose:**
The Blendy Backend is a robust and scalable system designed to serve as the core operational engine for a business. It provides comprehensive functionalities for managing critical business processes, including user authentication and authorization, inventory control, product catalog management, sales order processing, and organizational structure definition. It aims to offer a secure, efficient, and extensible foundation for various client applications (web, mobile, desktop) that require a centralized business management system.

**Target Audience:**
*   Businesses of various sizes looking for a comprehensive solution to manage their internal operations.
*   Developers building front-end applications (web, mobile, desktop) that need to interact with a powerful and well-structured backend for business logic and data storage.
*   System administrators responsible for deploying, configuring, and maintaining the business management system.

### 2. Key Features

*   **Secure User Authentication & Authorization:** Manages user accounts, login, registration, and granular access control based on roles and permissions.
*   **Comprehensive Inventory Management:** Tracks product stock levels, manages multiple storage locations, and records all inventory movements (receipts, dispatches, transfers).
*   **Product Catalog Management:** Centralized system for defining, categorizing, and managing all products offered by the business.
*   **Sales Order Processing:** Facilitates the creation, tracking, and fulfillment of sales orders, including customer management and invoice generation.
*   **Organizational Structure Management:** Allows for the definition and management of the company's internal structure, such as departments and branches.

### 3. Module-wise Detailed Documentation and Use Cases

The Blendy Backend is structured into several Django applications, each responsible for a specific domain of business logic.

#### 3.1. Authentication

*   **Purpose:** Handles all aspects of user identity verification, including user registration, login, session management, and token generation for secure API access.
*   **Key Entities (Inferred):**
    *   `User`: Represents a system user (likely extending Django's built-in User model).
    *   `Token`: Used for API authentication (e.g., JWT or similar).
*   **Detailed Use Cases:**
    *   **User Registration:**
        *   **Scenario:** A new employee or customer needs access to the system.
        *   **Action:** The user provides necessary credentials (e.g., username, email, password) to create a new account.
        *   **System Response:** A new user record is created, and an initial authentication token might be issued.
    *   **User Login:**
        *   **Scenario:** An existing user wants to access the system's functionalities.
        *   **Action:** The user submits their username/email and password.
        *   **System Response:** Upon successful authentication, an access token and a refresh token are issued.
    *   **Token Refresh:**
        *   **Scenario:** A user's access token has expired, but they are still active in the system.
        *   **Action:** The client application uses the refresh token to obtain a new access token without requiring re-login.
        *   **System Response:** A new, valid access token is provided.
    *   **Password Reset:**
        *   **Scenario:** A user forgets their password and needs to regain access.
        *   **Action:** The user initiates a password reset process, typically via email verification.
        *   **System Response:** A secure link or code is sent to the user's registered email, allowing them to set a new password.
*   **Inferred API Endpoints:**
    *   `POST /api/auth/register/`
    *   `POST /api/auth/login/`
    *   `POST /api/auth/token/refresh/`
    *   `POST /api/auth/password/reset/`

#### 3.2. Authorization

*   **Purpose:** Manages the roles and permissions within the system, ensuring that users can only access resources and perform actions for which they have explicit authorization.
*   **Key Entities (Inferred):**
    *   `Role`: Defines a collection of permissions (e.g., "Admin", "Inventory Manager", "Sales Associate").
    *   `Permission`: Represents a specific action or access right (e.g., "can_create_product", "can_view_sales_report").
*   **Detailed Use Cases:**
    *   **Assign Role to User:**
        *   **Scenario:** A new employee joins the sales team and needs appropriate system access.
        *   **Action:** An administrator assigns the "Sales Associate" role to the new user.
        *   **System Response:** The user inherits all permissions associated with the "Sales Associate" role.
    *   **Check Permissions for Action:**
        *   **Scenario:** A user attempts to delete a product from the catalog.
        *   **Action:** The system checks if the user's assigned roles grant the "can_delete_product" permission.
        *   **System Response:** If authorized, the action proceeds; otherwise, an "Access Denied" error is returned.
    *   **Define New Role:**
        *   **Scenario:** The business introduces a new operational role, e.g., "Warehouse Supervisor," requiring a specific set of permissions.
        *   **Action:** An administrator creates a new "Warehouse Supervisor" role and assigns relevant permissions (e.g., "can_transfer_stock", "can_view_inventory_audit").
        *   **System Response:** The new role is available for assignment to users.
*   **Inferred API Endpoints:**
    *   `GET /api/authorization/roles/`
    *   `POST /api/authorization/roles/`
    *   `GET /api/authorization/permissions/`

#### 3.3. Inventory

*   **Purpose:** Provides a comprehensive system for tracking and managing product stock levels, locations, and all movements within the supply chain.
*   **Key Entities (Inferred):**
    *   `Product`: Reference to a product from the `products` app.
    *   `Location`: Represents a physical storage location (e.g., "Warehouse A", "Shelf 3", "Retail Store Front").
    *   `Stock`: Records the quantity of a specific product at a specific location.
    *   `StockMovement`: Logs all changes in stock (e.g., receipt, dispatch, transfer, adjustment).
*   **Detailed Use Cases:**
    *   **Receive New Stock:**
        *   **Scenario:** A new shipment of products arrives at the warehouse.
        *   **Action:** An inventory manager records the quantity of each product received and its designated storage location.
        *   **System Response:** Stock levels for the respective products and locations are increased, and a `StockMovement` record is created.
    *   **Dispatch Stock for Sale/Order Fulfillment:**
        *   **Scenario:** Products are picked from the warehouse to fulfill a customer order.
        *   **Action:** The system deducts the ordered quantity from the appropriate location's stock.
        *   **System Response:** Stock levels are decreased, and a `StockMovement` record is created, often linked to a sales order.
    *   **Transfer Stock Between Locations:**
        *   **Scenario:** Products need to be moved from the main warehouse to a retail store.
        *   **Action:** An inventory manager initiates a stock transfer, specifying source and destination locations and quantities.
        *   **System Response:** Stock is decreased at the source and increased at the destination, with corresponding `StockMovement` records.
    *   **View Current Stock Levels:**
        *   **Scenario:** A sales representative needs to check product availability before promising delivery.
        *   **Action:** The user queries the system for current stock levels of a specific product or across all products/locations.
        *   **System Response:** A real-time report of available quantities per product and location is displayed.
    *   **Perform Inventory Audit/Adjustment:**
        *   **Scenario:** A physical count reveals discrepancies with system records.
        *   **Action:** An inventory manager records adjustments to match physical stock, noting reasons for discrepancies.
        *   **System Response:** Stock levels are updated, and an adjustment `StockMovement` record is created.
*   **Inferred API Endpoints:**
    *   `GET /api/inventory/stock/`
    *   `POST /api/inventory/stock/movements/`
    *   `GET /api/inventory/locations/`

#### 3.4. Organization

*   **Purpose:** Defines and manages the internal hierarchical structure of the business, such as departments, branches, or business units.
*   **Key Entities (Inferred):**
    *   `Organization`: The top-level business entity.
    *   `Department`: A functional division within the organization (e.g., "Sales", "Marketing", "Logistics").
    *   `Branch`: A geographical or operational branch of the organization.
*   **Detailed Use Cases:**
    *   **Create New Department:**
        *   **Scenario:** The company establishes a new "Customer Success" department.
        *   **Action:** An administrator creates a new department record with its name and description.
        *   **System Response:** The new department is added to the organizational structure.
    *   **Assign User to Department/Branch:**
        *   **Scenario:** A new employee needs to be associated with their respective department for reporting and access control.
        *   **Action:** An administrator assigns a user to a specific department or branch.
        *   **System Response:** The user's profile is updated to reflect their organizational affiliation.
    *   **View Organizational Hierarchy:**
        *   **Scenario:** A manager needs to understand the company's structure or find contact information for a specific department.
        *   **Action:** The user requests a view of the organizational chart or a list of departments/branches.
        *   **System Response:** A structured representation of the organization is displayed.
*   **Inferred API Endpoints:**
    *   `GET /api/organization/departments/`
    *   `POST /api/organization/departments/`
    *   `GET /api/organization/branches/`

#### 3.5. Products

*   **Purpose:** Manages the master catalog of all products and services offered by the business, including their attributes, pricing, and categorization.
*   **Key Entities (Inferred):**
    *   `Product`: Represents an item for sale, with attributes like name, description, SKU, price, weight, dimensions.
    *   `Category`: Used to group products (e.g., "Electronics", "Apparel", "Home Goods").
*   **Detailed Use Cases:**
    *   **Create New Product:**
        *   **Scenario:** The business introduces a new item to its sales catalog.
        *   **Action:** A product manager enters all relevant details for the new product, including its name, description, price, and assigns it to one or more categories.
        *   **System Response:** The new product is added to the catalog and becomes available for sales and inventory management.
    *   **Update Product Information:**
        *   **Scenario:** The price of a product changes, or its description needs to be updated.
        *   **Action:** A product manager modifies the attributes of an existing product.
        *   **System Response:** The product's details are updated across the system.
    *   **Browse Products:**
        *   **Scenario:** A sales associate needs to find a specific product or view all products within a category.
        *   **Action:** The user searches or filters the product catalog.
        *   **System Response:** A list of matching products with their key details is displayed.
    *   **Manage Categories:**
        *   **Scenario:** The business wants to reorganize its product offerings or add new product types.
        *   **Action:** An administrator creates, renames, or deletes product categories.
        *   **System Response:** The product categorization structure is updated.
*   **Inferred API Endpoints:**
    *   `GET /api/products/`
    *   `POST /api/products/`
    *   `GET /api/products/{id}/`
    *   `PUT /api/products/{id}/`
    *   `GET /api/products/categories/`

#### 3.6. Sales

*   **Purpose:** Manages the entire sales process, from creating customer orders to processing payments and generating invoices.
*   **Key Entities (Inferred):**
    *   `Customer`: Represents a buyer, with contact and billing information.
    *   `Order`: A record of products/services purchased by a customer.
    *   `OrderItem`: Details of individual products within an order (quantity, price at time of sale).
    *   `Invoice`: A formal request for payment or record of a completed transaction.
*   **Detailed Use Cases:**
    *   **Create Sales Order:**
        *   **Scenario:** A customer places an order for several products.
        *   **Action:** A sales associate creates a new order, selects the customer, and adds the desired products and quantities.
        *   **System Response:** A new sales order is created, and inventory is typically reserved or deducted.
    *   **Process Payment for Order:**
        *   **Scenario:** A customer pays for their order.
        *   **Action:** The system records the payment details (amount, method, date) against the order.
        *   **System Response:** The order status is updated to "Paid" or "Partially Paid."
    *   **Generate Invoice:**
        *   **Scenario:** A completed order requires a formal invoice for the customer or accounting.
        *   **Action:** The system generates an invoice based on the order details.
        *   **System Response:** A printable or digital invoice document is created, often with a unique invoice number.
    *   **Track Order Status:**
        *   **Scenario:** A customer or sales manager wants to know the current status of an order (e.g., "Pending", "Processing", "Shipped", "Completed").
        *   **Action:** The user queries the system for an order's status.
        *   **System Response:** The current status and relevant historical events of the order are displayed.
    *   **View Sales History/Reports:**
        *   **Scenario:** A sales manager needs to analyze past sales performance.
        *   **Action:** The user requests sales reports, filtered by date, product, or customer.
        *   **System Response:** Aggregated sales data, trends, and detailed transaction lists are provided.
*   **Inferred API Endpoints:**
    *   `GET /api/sales/orders/`
    *   `POST /api/sales/orders/`
    *   `GET /api/sales/orders/{id}/`
    *   `POST /api/sales/orders/{id}/payment/`
    *   `GET /api/sales/customers/`
    *   `POST /api/sales/invoices/`

#### 3.7. Users

*   **Purpose:** Manages detailed user profiles and their association with organizational roles, extending beyond basic authentication to include personal and professional information.
*   **Key Entities (Inferred):**
    *   `UserProfile`: Contains additional user-specific data not covered by the basic `User` model (e.g., phone number, address, department, job title).
*   **Detailed Use Cases:**
    *   **View User Profile:**
        *   **Scenario:** A manager needs to view an employee's contact details or assigned department.
        *   **Action:** The user queries for a specific user's profile.
        *   **System Response:** The detailed profile information for the requested user is displayed.
    *   **Update User Profile:**
        *   **Scenario:** A user's contact information changes, or an administrator needs to update their job title.
        *   **Action:** The user or administrator modifies the fields in a user's profile.
        *   **System Response:** The user's profile information is updated in the database.
    *   **Manage User Roles (via Users app):**
        *   **Scenario:** An administrator needs to change a user's access level by modifying their assigned roles.
        *   **Action:** The administrator updates the roles associated with a specific user.
        *   **System Response:** The user's permissions are immediately updated based on the new role assignments.
*   **Inferred API Endpoints:**
    *   `GET /api/users/profile/`
    *   `PUT /api/users/profile/{id}/`
    *   `GET /api/users/` (for admin to list users)

### 5. Technical Stack

*   **Backend Framework:** Django (Python)
*   **API Framework:** Django REST Framework (inferred from `serializers.py` and `views.py` in apps)
*   **Database:** SQLite (default for development, easily configurable for production-grade databases like PostgreSQL, MySQL, etc.)
*   **Authentication:** Token-based authentication (e.g., JWT) for secure API access.

### 5. Setup and Installation (Brief)

To get the Blendy Backend running locally:

1.  **Clone the repository:**
    ```bash
    git clone <repository_url> blendy-backend
    cd blendy-backend
    ```
2.  **Create a Python virtual environment:**
    ```bash
    python -m venv venv
    ```
3.  **Activate the virtual environment:**
    ```bash
    source venv/bin/activate
    ```
4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
5.  **Run database migrations:**
    ```bash
    python manage.py migrate
    ```
6.  **Create a superuser (for admin access):**
    ```bash
    python manage.py createsuperuser
    ```
7.  **Start the development server:**
    ```bash
    python manage.py runserver
    ```
    The API will typically be accessible at `http://127.0.0.1:8000/api/`.

---