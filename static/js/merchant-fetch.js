document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.merchant-clickable').forEach(row => {
        row.addEventListener('click', async () => {
            const mId = row.dataset.merchantId;
            const cId = row.dataset.csvId;
            const expansionPanel = document.getElementById(`details-${mId}`);
            const contentArea = expansionPanel.querySelector('.expansion-content');

            // 1. If it's already open, close it
            if (expansionPanel.classList.contains('is-open')) {
                expansionPanel.classList.remove('is-open');
                return;
            }

            // 2. Optional: Close other open panels first
            document.querySelectorAll('.merchant-details-expansion').forEach(el => el.classList.remove('is-open'));

            // 3. Load data if empty or refresh
            contentArea.innerHTML = '<p class="text-muted">Caricamento transazioni...</p>';
            expansionPanel.classList.add('is-open');

            try {
                const response = await fetch(`${TRANSACTION_BY_MERCHANT_BY_CSV}?merchant_id=${mId}&csv_upload_id=${cId}`);
                const data = await response.json();

                if (data.transactions.length === 0) {
                    contentArea.innerHTML = '<p>Nessuna transazione trovata.</p>';
                    return;
                }

                let html = '';
                data.transactions.forEach(t => {
                    html += `
                        <div class="mini-transaction-row">
                            <span class="mini-date">${t.transaction_date}</span>
                            <span class="mini-desc">${t.description}</span>
                            <span class="mini-amount">€${t.amount}</span>
                        </div>`;
                });
                contentArea.innerHTML = html;

            } catch (error) {
                contentArea.innerHTML = '<p class="text-danger">Errore nel caricamento.</p>';
            }
        });
    });
});