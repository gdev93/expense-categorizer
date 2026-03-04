from django.db.models import Func, IntegerField


class ArrayIntersectionCount(Func):
    """
    Custom function to count common elements between two arrays in PostgreSQL.
    Equivalent to: cardinality(array(select unnest(array1) intersect select unnest(array2)))
    """
    function = 'cardinality'
    template = "%(function)s(ARRAY(SELECT unnest(%(expressions)s) INTERSECT SELECT unnest(ARRAY[%(search_trigrams)s])))"
    output_field = IntegerField()