document.addEventListener('DOMContentLoaded', () => {
    const drawer = document.getElementById('merchant-drawer');
    const drawerBody = document.getElementById('drawer-body');
    const drawerTitle = document.getElementById('drawer-title');
    const closeBtn = document.getElementById('close-drawer');

    document.querySelectorAll('.merchant-clickable').forEach(row => {
        row.addEventListener('click', async () => {
            const mId = row.dataset.merchantId;
            const cId = row.dataset.csvId;

            drawerBody.innerHTML = '<p>Caricamento...</p>';
            drawer.classList.add('open');
            try {
                const response = await fetch(`${TRANSACTION_BY_MERCHANT_BY_CSV}?merchant_id=${mId}&csv_upload_id=${cId}`);
                const data = await response.json();

                drawerTitle.innerText = data.merchant_name;

                let html = `<p class="text-muted">Dal ${data.first_date} al ${data.last_date}</p><hr>`;
                data.transactions.forEach(t => {
                    html += `
                        <div class="transaction-item-mini">
                            <div style="display:flex; justify-content:space-between;">
                                <strong>€${t.amount}</strong>
                                <small>${t.transaction_date}</small>
                            </div>
                            <div style="font-size: 0.85rem; color: #666;">${t.description}</div>
                        </div>`;
                });
                drawerBody.innerHTML = html;

            } catch (error) {
                drawerBody.innerHTML = '<p class="text-danger">Errore durante il caricamento.</p>';
            }
        });
    });

    closeBtn.addEventListener('click', () => {
        drawer.classList.remove('open');
    });
});