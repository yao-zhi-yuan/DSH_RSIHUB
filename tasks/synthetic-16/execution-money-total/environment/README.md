Implement `invoice_total(items, tax_basis_points)`.

Each item has integer `unit_cents` and `quantity`. Reject negative values. Compute subtotal in cents, then tax using integer half-up rounding where 10,000 basis points equals 100%. Return `{'subtotal_cents', 'tax_cents', 'total_cents'}`.
