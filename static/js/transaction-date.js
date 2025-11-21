document.addEventListener('DOMContentLoaded', function() {
    // Get the transaction date input field
    const transactionDateInput = document.getElementById('id_transaction_date');

    if (transactionDateInput) {
        // Parse URL query parameters
        const urlParams = new URLSearchParams(window.location.search);
        const selectedMonth = urlParams.get('selected_month');

        let dateToSet;

        if (selectedMonth) {
            // If selected_month parameter exists, use it
            const monthNumber = parseInt(selectedMonth, 10);

            // Get current year (you might want to also pass selected_year if needed)
            const currentYear = new Date().getFullYear();

            // Create date for first day of the selected month
            dateToSet = new Date(currentYear, monthNumber - 1, 1);
        } else {
            // Fallback to first day of current month
            const today = new Date();
            dateToSet = new Date(today.getFullYear(), today.getMonth(), 1);
        }

        // Format date as YYYY-MM-DD for input[type="date"]
        const year = dateToSet.getFullYear();
        const month = String(dateToSet.getMonth() + 1).padStart(2, '0');
        const day = String(dateToSet.getDate()).padStart(2, '0');
        // Set the value
        transactionDateInput.value = `${year}-${month}-${day}`;
    }
});