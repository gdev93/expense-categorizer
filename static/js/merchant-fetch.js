document.addEventListener('DOMContentLoaded', () => {
    const dataCache = new Map();
    const openState = new Map();
    let currentlyOpenId = null;

    console.log("[MerchantFetch] Script initialized and ready.");

    const rows = document.querySelectorAll('.merchant-clickable');
    console.log(`[MerchantFetch] Found ${rows.length} clickable rows.`);

    rows.forEach(row => {
        row.addEventListener('click', async (event) => {
            // Check if the click was on the category select or form
            if (event.target.closest('.quick-category-form')) {
                console.log("[MerchantFetch] Click ignored: category selector used.");
                return;
            }

            const mId = row.dataset.merchantId;
            const cId = row.dataset.csvId;
            console.log(`[MerchantFetch] Row clicked. Merchant ID: ${mId}, CSV ID: ${cId}`);

            const cacheKey = `${mId}-${cId}`;
            const expansionPanel = document.getElementById(`details-${mId}`);

            if (!expansionPanel) {
                console.error(`[MerchantFetch] Error: Expansion panel 'details-${mId}' not found in DOM.`);
                return;
            }

            const contentArea = expansionPanel.querySelector('.expansion-content');

            // 1. Toggle Close logic
            if (openState.get(mId)) {
                console.log(`[MerchantFetch] Closing panel: ${mId}`);
                expansionPanel.classList.remove('is-open');
                openState.set(mId, false);
                currentlyOpenId = null;
                return;
            }

            // 2. Auto-close previous
            if (currentlyOpenId && currentlyOpenId !== mId) {
                console.log(`[MerchantFetch] Auto-closing previous: ${currentlyOpenId}`);
                const prevPanel = document.getElementById(`details-${currentlyOpenId}`);
                if (prevPanel) prevPanel.classList.remove('is-open');
                openState.set(currentlyOpenId, false);
            }

            // 3. Cache Check
            if (dataCache.has(cacheKey)) {
                console.log(`[MerchantFetch] Rendering from cache: ${cacheKey}`);
                contentArea.innerHTML = dataCache.get(cacheKey);
                expansionPanel.classList.add('is-open');
                openState.set(mId, true);
                currentlyOpenId = mId;
                return;
            }

            // 4. Fetch
            console.log(`[MerchantFetch] Fetching data from server...`);
            contentArea.innerHTML = '<p class="text-muted">Caricamento transazioni...</p>';

            try {
                const response = await fetch(`${TRANSACTION_BY_MERCHANT_BY_CSV_URL}?merchant_id=${mId}&csv_upload_id=${cId}`);
                const data = await response.json();

                let html = '';
                if (data.transactions.length === 0) {
                    html = '<p>Nessuna transazione trovata.</p>';
                } else {
                    data.transactions.forEach(t => {
                        const finalUrl = TRANSACTION_DETAIL_URL.replace('0', t.id);
                        html += `
                            <div class="mini-transaction-row" onclick="window.location.href='${finalUrl}'" style="cursor:pointer;">
                                <span class="mini-date">${t.transaction_date}</span>
                                <span class="mini-desc">${t.description}</span>
                                <span class="mini-amount">€${t.amount}</span>
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