document.addEventListener('DOMContentLoaded', () => {
    const dataCache = new Map();
    const openState = new Map();
    let currentlyOpenId = null;

    const rows = document.querySelectorAll('.merchant-clickable');

    rows.forEach(row => {
        row.addEventListener('click', async (event) => {

            const mId = row.dataset.merchantId;

            const params = new URLSearchParams(window.location.search);
            params.set('merchant_id', mId);

            const cacheKey = mId;
            const expansionPanel = document.getElementById(`details-${mId}`);

            const contentArea = expansionPanel.querySelector('.expansion-content');

            // 1. Toggle Close logic
            if (openState.get(mId)) {
                expansionPanel.classList.remove('is-open');
                openState.set(mId, false);
                currentlyOpenId = null;
                return;
            }

            // 2. Auto-close previous
            if (currentlyOpenId && currentlyOpenId !== mId) {
                const prevPanel = document.getElementById(`details-${currentlyOpenId}`);
                if (prevPanel) prevPanel.classList.remove('is-open');
                openState.set(currentlyOpenId, false);
            }

            // 3. Cache Check
            if (dataCache.has(cacheKey)) {
                contentArea.innerHTML = dataCache.get(cacheKey);
                expansionPanel.classList.add('is-open');
                openState.set(mId, true);
                currentlyOpenId = mId;
                return;
            }

            contentArea.innerHTML = '<p class="text-muted"><span class="material-icons spin-animation" style="font-size: 1.2rem; vertical-align: middle; margin-right: 8px;">sync</span>Caricamento transazioni...</p>';

            try {
                const response = await fetch(`${TRANSACTION_BY_MERCHANT_BY_CSV_URL}?${params.toString()}`);
                const data = await response.json();

                let html = '';
                if (data.transactions.length === 0) {
                    html = '<p>Nessuna transazione trovata.</p>';
                } else {
                    data.transactions.forEach(t => {
                        const finalUrl = TRANSACTION_DETAIL_URL.replace('0', t.id);
                        const amountClass = t.transaction_type === 'income' ? 'is-income' : '';
                        html += `
                            <div class="mini-transaction-row" onclick="window.location.href='${finalUrl}'">
                                <span class="mini-date">${t.transaction_date}</span>
                                <span class="mini-desc">${t.description}</span>
                                <span class="mini-amount ${amountClass}">€${t.amount}</span>
                                <span class="mini-chevron">›</span>
                            </div>`;
                    });
                }

                dataCache.set(cacheKey, html);
                contentArea.innerHTML = html;
                expansionPanel.classList.add('is-open');
                openState.set(mId, true);
                currentlyOpenId = mId;
                console.log(`[MerchantFetch] Panel expanded and cached.`);

            } catch (error) {
                console.error(`[MerchantFetch] Fetch error:`, error);
                contentArea.innerHTML = '<p class="text-danger">Errore nel caricamento.</p>';
            }
        });
    });
});