import datetime
from dataclasses import dataclass

from django.core.cache import cache
from django.views import View

from api.models import Transaction


@dataclass
class YearMonthCacheValue:
    year: int
    months: list[int]


class MonthYearFilterMixin(View):
    def get_year_and_months(self):
        # 1. Generate a cache key based on the RAW request to skip parsing
        # We use the user ID and the full GET query string
        query_string = self.request.GET.urlencode()
        cache_key = f"filter_cache_{self.request.user.id}_{query_string}"

        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result.year, cached_result.months

        # 2. If NOT in cache, perform the parsing logic
        raw_year = self.request.GET.get('year')
        raw_months = self.request.GET.getlist('months', [])

        # Handle single month param
        single_month = self.request.GET.get('month')
        if single_month and single_month not in raw_months:
            raw_months.append(single_month)

        # Resolve Year
        if raw_year:
            try:
                selected_year = int(raw_year)
            except (TypeError, ValueError):
                # If invalid year passed, fallback to last transaction year or current year
                selected_year = self._get_default_year()
        else:
            selected_year = self._get_default_year()

        # Resolve Months
        processed_months = []
        for m in raw_months:
            if m:
                try:
                    processed_months.append(int(m))
                except (TypeError, ValueError):
                    pass

        # 3. Save to cache before returning
        result = YearMonthCacheValue(year=selected_year, months=processed_months)
        cache.set(cache_key, result, timeout=3600)

        return result.year, result.months

    def _get_default_year(self):
        last_t = Transaction.objects.filter(
            user=self.request.user,
            status='categorized'
        ).order_by('-transaction_date').first()
        return last_t.transaction_date.year if last_t else datetime.datetime.now().year

    # These are now helpers if you need to manually clear or set cache elsewhere
    def _make_cache_key(self, query_string: str):
        return f"filter_cache_{self.request.user.id}_{query_string}"