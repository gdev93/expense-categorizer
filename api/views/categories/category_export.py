import datetime
from decimal import Decimal
import pandas as pd
from django.db.models import Q
from django.http import HttpResponse
from django.views import View

from api.models import Category, Transaction
from .mixins import CategoryEnrichedMixin

class CategoryExportView(CategoryEnrichedMixin, View):
    def get(self, request, *args, **kwargs):
        """
        Exports category totals grouped by month to Excel.
        Uses active filters for year, months, search and selected categories.
        """
        # 1. Get filters and base categories
        filters = self.get_category_filters()
        base_queryset = Category.objects.filter(user=request.user)
        if filters['search']:
            base_queryset = base_queryset.filter(name__icontains=filters['search'])
        if filters['selected_category_ids']:
            base_queryset = base_queryset.filter(id__in=filters['selected_category_ids'])

        categories_dict = {c.id: c for c in base_queryset}
        category_ids = list(categories_dict.keys())

        # 2. Fetch transactions for selected period and categories
        tx_filter = Q(
            user=request.user, 
            category_id__in=category_ids, 
            transaction_date__year=filters['year']
        )
        if filters['months']:
            tx_filter &= Q(transaction_date__month__in=filters['months'])
            
        transactions = Transaction.objects.filter(tx_filter).select_related('category')

        # 3. Group by category and month
        from collections import defaultdict
        grouped = defaultdict(lambda: {'count': 0, 'sum': Decimal('0')})
        
        for tx in transactions:
            month = tx.transaction_date.month
            key = (tx.category_id, month)
            grouped[key]['count'] += 1
            grouped[key]['sum'] += (tx.amount or Decimal('0'))

        ITALIAN_MONTHS = {
            1: 'Gennaio', 2: 'Febbraio', 3: 'Marzo', 4: 'Aprile',
            5: 'Maggio', 6: 'Giugno', 7: 'Luglio', 8: 'Agosto',
            9: 'Settembre', 10: 'Ottobre', 11: 'Novembre', 12: 'Dicembre'
        }

        data = []
        # Sort by month then category name
        sorted_keys = sorted(grouped.keys(), key=lambda x: (x[1], categories_dict[x[0]].name))
        
        for (cat_id, month) in sorted_keys:
            cat = categories_dict[cat_id]
            data.append({
                'Mese': ITALIAN_MONTHS.get(month, ''),
                'Categoria': cat.name,
                'Descrizione': cat.description or '',
                'N. Transazioni': grouped[(cat_id, month)]['count'],
                'Totale Importo': float(grouped[(cat_id, month)]['sum'])
            })

        df = pd.DataFrame(data)

        # 4. Handle Case: Empty List
        if df.empty:
            df = pd.DataFrame(columns=['Mese', 'Categoria', 'Descrizione', 'N. Transazioni', 'Totale Importo'])

        # 5. Build Excel Response
        filename = f"categorie_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Categorie')

        return response
