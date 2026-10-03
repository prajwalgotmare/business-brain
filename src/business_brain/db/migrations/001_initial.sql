CREATE TABLE tenants (
    tenant_id text PRIMARY KEY,
    tenant_name text NOT NULL UNIQUE,
    default_currency_code char(3) NOT NULL,
    timezone text NOT NULL,
    record_status text NOT NULL CHECK (record_status IN ('active', 'inactive', 'cancelled')),
    source_system text NOT NULL DEFAULT 'demo_generator',
    source_file text NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE regions (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), region_id text NOT NULL,
    region_name text NOT NULL, country_code char(2) NOT NULL, sensitivity text NOT NULL,
    source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, region_id)
);
CREATE TABLE products (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), product_id text NOT NULL,
    sku text NOT NULL, product_name text NOT NULL, category text NOT NULL,
    unit_of_measure text NOT NULL, list_price numeric(12,2) NOT NULL CHECK (list_price >= 0),
    standard_cost numeric(12,2) NOT NULL CHECK (standard_cost >= 0), currency_code char(3) NOT NULL,
    reorder_point integer NOT NULL CHECK (reorder_point >= 0), safety_stock integer NOT NULL CHECK (safety_stock >= 0),
    record_status text NOT NULL, sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator',
    source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, product_id), UNIQUE (tenant_id, sku)
);
CREATE TABLE warehouses (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), warehouse_id text NOT NULL,
    region_id text NOT NULL, warehouse_name text NOT NULL, country_code char(2) NOT NULL,
    timezone text NOT NULL, sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator',
    source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, warehouse_id), FOREIGN KEY (tenant_id, region_id) REFERENCES regions(tenant_id, region_id)
);
CREATE TABLE suppliers (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), supplier_id text NOT NULL,
    supplier_name text NOT NULL, payment_terms_days integer NOT NULL CHECK (payment_terms_days > 0),
    lead_time_days integer NOT NULL CHECK (lead_time_days > 0), currency_code char(3) NOT NULL,
    record_status text NOT NULL, sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator',
    source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, supplier_id)
);
CREATE TABLE carriers (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), carrier_id text NOT NULL,
    carrier_name text NOT NULL, service_level text NOT NULL, sla_delivery_days integer NOT NULL CHECK (sla_delivery_days > 0),
    record_status text NOT NULL, sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator',
    source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, carrier_id)
);
CREATE TABLE customers (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), customer_id text NOT NULL,
    customer_segment text NOT NULL, region_id text NOT NULL, display_name text NOT NULL,
    email_alias text NOT NULL, sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator',
    source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, customer_id),
    FOREIGN KEY (tenant_id, region_id) REFERENCES regions(tenant_id, region_id)
);
CREATE TABLE orders (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), order_id text NOT NULL,
    customer_id text NOT NULL, warehouse_id text NOT NULL, order_timestamp timestamptz NOT NULL,
    order_status text NOT NULL, sales_channel text NOT NULL, currency_code char(3) NOT NULL,
    subtotal_amount numeric(12,2) NOT NULL, discount_amount numeric(12,2) NOT NULL,
    tax_amount numeric(12,2) NOT NULL, shipping_amount numeric(12,2) NOT NULL,
    order_total_amount numeric(12,2) NOT NULL, sensitivity text NOT NULL,
    source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id), FOREIGN KEY (tenant_id, customer_id) REFERENCES customers(tenant_id, customer_id),
    FOREIGN KEY (tenant_id, warehouse_id) REFERENCES warehouses(tenant_id, warehouse_id)
);
CREATE TABLE purchase_orders (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), purchase_order_id text NOT NULL,
    supplier_id text NOT NULL, warehouse_id text NOT NULL, created_at timestamptz NOT NULL, expected_at timestamptz NOT NULL,
    purchase_order_status text NOT NULL, currency_code char(3) NOT NULL, subtotal_amount numeric(12,2) NOT NULL,
    tax_amount numeric(12,2) NOT NULL, freight_amount numeric(12,2) NOT NULL, total_amount numeric(12,2) NOT NULL,
    approval_required boolean NOT NULL, sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator',
    source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, purchase_order_id),
    FOREIGN KEY (tenant_id, supplier_id) REFERENCES suppliers(tenant_id, supplier_id),
    FOREIGN KEY (tenant_id, warehouse_id) REFERENCES warehouses(tenant_id, warehouse_id)
);
CREATE TABLE shipments (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), shipment_id text NOT NULL, shipment_direction text NOT NULL,
    order_id text, purchase_order_id text, carrier_id text NOT NULL, origin_warehouse_id text,
    destination_warehouse_id text, destination_region_id text NOT NULL, tracking_number text NOT NULL,
    shipped_at timestamptz NOT NULL, promised_delivery_at timestamptz NOT NULL, delivered_at timestamptz,
    shipment_status text NOT NULL, freight_charge_amount numeric(12,2) NOT NULL, currency_code char(3) NOT NULL,
    sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, shipment_id), UNIQUE (tenant_id, tracking_number),
    FOREIGN KEY (tenant_id, order_id) REFERENCES orders(tenant_id, order_id),
    FOREIGN KEY (tenant_id, purchase_order_id) REFERENCES purchase_orders(tenant_id, purchase_order_id),
    FOREIGN KEY (tenant_id, carrier_id) REFERENCES carriers(tenant_id, carrier_id),
    FOREIGN KEY (tenant_id, origin_warehouse_id) REFERENCES warehouses(tenant_id, warehouse_id),
    FOREIGN KEY (tenant_id, destination_warehouse_id) REFERENCES warehouses(tenant_id, warehouse_id),
    FOREIGN KEY (tenant_id, destination_region_id) REFERENCES regions(tenant_id, region_id),
    CHECK ((shipment_direction = 'outbound' AND order_id IS NOT NULL AND purchase_order_id IS NULL)
        OR (shipment_direction = 'inbound' AND purchase_order_id IS NOT NULL AND order_id IS NULL))
);
CREATE TABLE order_lines (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), order_line_id text NOT NULL, order_id text NOT NULL,
    product_id text NOT NULL, quantity integer NOT NULL CHECK (quantity > 0), unit_price numeric(12,2) NOT NULL,
    discount_amount numeric(12,2) NOT NULL, net_amount numeric(12,2) NOT NULL, unit_cost_snapshot numeric(12,2) NOT NULL,
    sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, order_line_id),
    FOREIGN KEY (tenant_id, order_id) REFERENCES orders(tenant_id, order_id),
    FOREIGN KEY (tenant_id, product_id) REFERENCES products(tenant_id, product_id)
);
CREATE TABLE inventory_balances (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), inventory_balance_id text NOT NULL,
    warehouse_id text NOT NULL, product_id text NOT NULL, snapshot_at timestamptz NOT NULL,
    on_hand_quantity integer NOT NULL CHECK (on_hand_quantity >= 0), allocated_quantity integer NOT NULL,
    available_quantity integer NOT NULL, inbound_quantity integer NOT NULL CHECK (inbound_quantity >= 0), sensitivity text NOT NULL,
    source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, inventory_balance_id), FOREIGN KEY (tenant_id, warehouse_id) REFERENCES warehouses(tenant_id, warehouse_id),
    FOREIGN KEY (tenant_id, product_id) REFERENCES products(tenant_id, product_id),
    CHECK (allocated_quantity >= 0 AND allocated_quantity <= on_hand_quantity AND available_quantity = on_hand_quantity - allocated_quantity)
);
CREATE TABLE purchase_order_lines (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), purchase_order_line_id text NOT NULL,
    purchase_order_id text NOT NULL, product_id text NOT NULL, quantity integer NOT NULL CHECK (quantity > 0),
    unit_cost numeric(12,2) NOT NULL, line_amount numeric(12,2) NOT NULL, sensitivity text NOT NULL,
    source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, purchase_order_line_id),
    FOREIGN KEY (tenant_id, purchase_order_id) REFERENCES purchase_orders(tenant_id, purchase_order_id),
    FOREIGN KEY (tenant_id, product_id) REFERENCES products(tenant_id, product_id)
);
CREATE TABLE inventory_movements (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), inventory_movement_id text NOT NULL,
    warehouse_id text NOT NULL, product_id text NOT NULL, occurred_at timestamptz NOT NULL,
    movement_type text NOT NULL, quantity_delta integer NOT NULL CHECK (quantity_delta <> 0), reference_type text NOT NULL,
    reference_id text NOT NULL, sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator',
    source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, inventory_movement_id),
    FOREIGN KEY (tenant_id, warehouse_id) REFERENCES warehouses(tenant_id, warehouse_id),
    FOREIGN KEY (tenant_id, product_id) REFERENCES products(tenant_id, product_id)
);
CREATE TABLE tracking_events (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), tracking_event_id text NOT NULL, shipment_id text NOT NULL,
    event_time timestamptz NOT NULL, event_type text NOT NULL, location_code text NOT NULL, reason_code text,
    event_source text NOT NULL, raw_event_id text NOT NULL, sensitivity text NOT NULL,
    source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, tracking_event_id), UNIQUE (tenant_id, event_source, raw_event_id),
    FOREIGN KEY (tenant_id, shipment_id) REFERENCES shipments(tenant_id, shipment_id)
);
CREATE TABLE delivery_exceptions (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), delivery_exception_id text NOT NULL,
    shipment_id text NOT NULL, tracking_event_id text NOT NULL, reason_code text NOT NULL, opened_at timestamptz NOT NULL,
    resolved_at timestamptz, exception_status text NOT NULL, customer_impact text NOT NULL, sensitivity text NOT NULL,
    source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, delivery_exception_id), FOREIGN KEY (tenant_id, shipment_id) REFERENCES shipments(tenant_id, shipment_id),
    FOREIGN KEY (tenant_id, tracking_event_id) REFERENCES tracking_events(tenant_id, tracking_event_id)
);
CREATE TABLE shipment_items (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), shipment_item_id text NOT NULL, shipment_id text NOT NULL,
    product_id text NOT NULL, expected_quantity integer NOT NULL CHECK (expected_quantity > 0),
    received_quantity integer NOT NULL CHECK (received_quantity >= 0), sensitivity text NOT NULL,
    source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, shipment_item_id), FOREIGN KEY (tenant_id, shipment_id) REFERENCES shipments(tenant_id, shipment_id),
    FOREIGN KEY (tenant_id, product_id) REFERENCES products(tenant_id, product_id)
);
CREATE TABLE carrier_sla_facts (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), carrier_sla_fact_id text NOT NULL,
    shipment_id text NOT NULL, carrier_id text NOT NULL, promised_delivery_at timestamptz NOT NULL,
    actual_delivery_at timestamptz, evaluated_at timestamptz NOT NULL, evaluation_basis text NOT NULL,
    sla_status text NOT NULL, delay_minutes integer NOT NULL CHECK (delay_minutes >= 0), penalty_eligible boolean NOT NULL,
    provisional_credit_amount numeric(12,2) NOT NULL, currency_code char(3) NOT NULL, sensitivity text NOT NULL,
    source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, carrier_sla_fact_id), FOREIGN KEY (tenant_id, shipment_id) REFERENCES shipments(tenant_id, shipment_id),
    FOREIGN KEY (tenant_id, carrier_id) REFERENCES carriers(tenant_id, carrier_id)
);
CREATE TABLE carrier_manifest_entries (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), manifest_entry_id text NOT NULL, shipment_id text NOT NULL,
    carrier_id text NOT NULL, tracking_number text NOT NULL, service_level text NOT NULL,
    reported_weight_kg numeric(12,3) NOT NULL, base_charge_amount numeric(12,2) NOT NULL,
    fuel_surcharge_amount numeric(12,2) NOT NULL, reported_charge_amount numeric(12,2) NOT NULL,
    currency_code char(3) NOT NULL, manifest_date date NOT NULL, delivery_status text NOT NULL, sensitivity text NOT NULL,
    source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, manifest_entry_id), FOREIGN KEY (tenant_id, shipment_id) REFERENCES shipments(tenant_id, shipment_id),
    FOREIGN KEY (tenant_id, carrier_id) REFERENCES carriers(tenant_id, carrier_id)
);
CREATE TABLE vendor_invoices (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), vendor_invoice_id text NOT NULL, supplier_id text NOT NULL,
    purchase_order_id text, invoice_number text NOT NULL, invoice_date date NOT NULL, due_date date NOT NULL,
    invoice_status text NOT NULL, currency_code char(3) NOT NULL, subtotal_amount numeric(12,2) NOT NULL,
    tax_amount numeric(12,2) NOT NULL, total_amount numeric(12,2) NOT NULL, outstanding_amount numeric(12,2) NOT NULL,
    sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, vendor_invoice_id),
    UNIQUE (tenant_id, supplier_id, invoice_number), FOREIGN KEY (tenant_id, supplier_id) REFERENCES suppliers(tenant_id, supplier_id),
    FOREIGN KEY (tenant_id, purchase_order_id) REFERENCES purchase_orders(tenant_id, purchase_order_id)
);
CREATE TABLE vendor_invoice_lines (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), vendor_invoice_line_id text NOT NULL,
    vendor_invoice_id text NOT NULL, line_type text NOT NULL, description text NOT NULL, shipment_id text,
    quantity numeric(12,3) NOT NULL, unit_price numeric(12,2) NOT NULL, line_amount numeric(12,2) NOT NULL,
    sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, vendor_invoice_line_id),
    FOREIGN KEY (tenant_id, vendor_invoice_id) REFERENCES vendor_invoices(tenant_id, vendor_invoice_id),
    FOREIGN KEY (tenant_id, shipment_id) REFERENCES shipments(tenant_id, shipment_id)
);
CREATE TABLE payments (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), payment_id text NOT NULL, vendor_invoice_id text NOT NULL,
    payment_date date NOT NULL, payment_amount numeric(12,2) NOT NULL CHECK (payment_amount > 0), currency_code char(3) NOT NULL,
    payment_status text NOT NULL, sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator',
    source_file text NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, payment_id),
    FOREIGN KEY (tenant_id, vendor_invoice_id) REFERENCES vendor_invoices(tenant_id, vendor_invoice_id)
);
CREATE TABLE regional_margin_snapshots (
    tenant_id text NOT NULL REFERENCES tenants(tenant_id), margin_snapshot_id text NOT NULL, region_id text NOT NULL,
    week_start_date date NOT NULL, revenue_amount numeric(12,2) NOT NULL, cost_of_goods_amount numeric(12,2) NOT NULL,
    freight_expense_amount numeric(12,2) NOT NULL, refund_amount numeric(12,2) NOT NULL,
    net_profit_amount numeric(12,2) NOT NULL, net_margin_pct numeric(8,4) NOT NULL, calculated_at timestamptz NOT NULL,
    sensitivity text NOT NULL, source_system text NOT NULL DEFAULT 'demo_generator', source_file text NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, margin_snapshot_id),
    UNIQUE (tenant_id, region_id, week_start_date), FOREIGN KEY (tenant_id, region_id) REFERENCES regions(tenant_id, region_id)
);

CREATE INDEX idx_orders_tenant_timestamp ON orders (tenant_id, order_timestamp);
CREATE INDEX idx_inventory_lookup ON inventory_balances (tenant_id, warehouse_id, product_id, snapshot_at DESC);
CREATE INDEX idx_shipments_delivery ON shipments (tenant_id, shipment_status, promised_delivery_at);
CREATE INDEX idx_tracking_shipment_time ON tracking_events (tenant_id, shipment_id, event_time);
CREATE INDEX idx_invoices_due ON vendor_invoices (tenant_id, invoice_status, due_date);
CREATE INDEX idx_margin_region_week ON regional_margin_snapshots (tenant_id, region_id, week_start_date);
