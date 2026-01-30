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
        # 1. Handle Reset
        if self.request.GET.get('reset') == '1':
            keys_to_clear = [
                'filter_year', 'filter_months', 'filter_category', 
                'filter_upload_file', 'filter_amount', 'filter_amount_operator',
                'filter_search', 'filter_view_type', 'filter_status',
                'filter_category_search', 'filter_category_selected'
            ]
            for key in keys_to_clear:
                if key in self.request.session:
                    del self.request.session[key]

        # 2. Determine raw year and months from GET or Session
        has_year_in_get = 'year' in self.request.GET
        has_months_in_get = 'months' in self.request.GET or 'month' in self.request.GET

        if has_year_in_get:
            raw_year = self.request.GET.get('year')
            self.request.session['filter_year'] = raw_year
        else:
            raw_year = self.request.session.get('filter_year')

        if has_months_in_get:
            raw_months = self.request.GET.getlist('months', [])
            single_month = self.request.GET.get('month')
            if single_month and single_month not in raw_months:
                raw_months.append(single_month)
            self.request.session['filter_months'] = raw_months
        else:
            raw_months = self.request.session.get('filter_months', [])

        # 2. Parsing logic
        # Resolve Year
        if raw_year:
            try:
                selected_year = int(raw_year)
            except (TypeError, ValueError):
                selected_year = self._get_default_year()
        else:
            selected_year = self._get_default_year()

        # Resolve Months
        processed_months = []
        if raw_months:
            for m in raw_months:
                if m:
                    try:
                        processed_months.append(int(m))
                    except (TypeError, ValueError):
                        pass

        return selected_year, processed_months

    def _get_default_year(self):
        last_t = Transaction.objects.filter(
            user=self.request.user,
            status='categorized'
        ).order_by('-transaction_date').first()
        return last_t.transaction_date.year if last_t and last_t.transaction_date else datetime.datetime.now().year

    # These are now helpers if you need to manually clear or set cache elsewhere
    def _make_cache_key(self, query_string: str):
        return f"filter_cache_{self.request.user.id}_{query_string}"