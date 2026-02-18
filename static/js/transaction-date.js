document.addEventListener('DOMContentLoaded', function() {
    const transactionDateInput = document.getElementById('id_transaction_date');
    if (transactionDateInput) {
        const urlParams = new URLSearchParams(window.location.search);
        const selectedMonth = urlParams.get('selected_month');
        let dateToSet;
        if (selectedMonth) {
            const monthNumber = parseInt(selectedMonth, 10);
            const currentYear = new Date().getFullYear();
            dateToSet = new Date(currentYear, monthNumber - 1, 1);
        } else {
            const today = new Date();
            dateToSet = new Date(today.getFullYear(), today.getMonth(), 1);
        }
        const year = dateToSet.getFullYear();
        const month = String(dateToSet.getMonth() + 1).padStart(2, '0');
        const day = String(dateToSet.getDate()).padStart(2, '0');
        transactionDateInput.value = `${year}-${month}-${day}`;
    }
});
