def mast_product_table(rows):
    """Keep selected product records from being interpreted as observation IDs."""
    from astropy.table import Table

    return Table(rows=rows)
