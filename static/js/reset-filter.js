document.addEventListener('DOMContentLoaded', () => {
    const resetFilter = document.getElementById('delete-category-search');
    if (resetFilter) {
        const searchInput = document.getElementById('id_search');
        if (searchInput) searchInput.value = '';
    }
})