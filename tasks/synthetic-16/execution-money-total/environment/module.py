def invoice_total(items, tax_basis_points):
    subtotal = sum(x['unit_cents'] for x in items)
    tax = round(subtotal * tax_basis_points / 10000)
    return {'subtotal_cents': subtotal, 'tax_cents': tax, 'total_cents': subtotal + tax}
