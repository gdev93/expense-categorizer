/**
 * Transforms the clicked <span> into a custom dropdown menu using pre-loaded options.
 * This function relies on the global array: CATEGORY_OPTIONS.
 */
function makeSelectable(element, event) {
    if (event) event.stopPropagation();

    // Exit if already transformed
    if (element.classList.contains('category-pill-container')) {
        return;
    }

    // Retrieve IDs from the HTML data attributes
    const currentCategoryId = element.getAttribute('data-current-category-id');
    const transactionId = element.getAttribute('data-transaction-id');
    const currentHTML = element.innerHTML;

    // 1. Create container
    const container = document.createElement('div');
    container.className = 'category-pill-container';

    // 2. Create the pill span
    const span = document.createElement('span');
    span.className = 'transaction-category';
    span.style.cursor = 'pointer';
    span.innerHTML = currentHTML;
    span.onclick = function(e) {
        e.stopPropagation();
        toggleCategoryMenu(this);
    };

    // 3. Create the dropdown menu
    const menu = document.createElement('div');
    menu.className = 'category-dropdown-menu';

    // 4. Populate options using the global CATEGORY_OPTIONS
    CATEGORY_OPTIONS.forEach(category => {
        const item = document.createElement('div');
        item.className = 'category-dropdown-item';
        item.setAttribute('data-category-id', category.id);
        if (String(category.id) === currentCategoryId) {
            item.classList.add('active');
        }
        item.textContent = category.name;

        item.onclick = function(e) {
            e.stopPropagation();
            submitCategoryChange(category.id, category.name, transactionId, span, menu);
        };
        menu.appendChild(item);
    });

    container.appendChild(span);
    container.appendChild(menu);

    // 5. Replace the original element
    element.parentNode.replaceChild(container, element);

    // 6. Open immediately
    toggleCategoryMenu(span);
}

async function submitCategoryChange(newCategoryId, newCategoryName, transactionId, span, menu) {
    // Visual feedback & close menu
    span.textContent = newCategoryName;
    menu.classList.remove('show');
    const container = span.closest('.category-pill-container');
    if (container) container.classList.remove('is-open');

    // Update active state in menu
    menu.querySelectorAll('.category-dropdown-item').forEach(item => {
        if (item.getAttribute('data-category-id') == newCategoryId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    const formData = new FormData();
    formData.append('category_id', newCategoryId);
    formData.append('transaction_id', transactionId);

    try {
        const response = await fetch(BASE_EDIT_TRANSACTION_URL, {
            method: 'POST',
            headers: {
                'X-CSRFToken': EDIT_TRANSACTION_CATEGORY_CSRF_TOKEN
            },
            body: formData,
        });

        if (!response.ok) {
            span.style.backgroundColor = '#f8d7da';
            throw new Error(`Update failed with status: ${response.status}`);
        }

        if (response.redirected) {
            window.location.href = response.url;
            return;
        }

        // Success: visual feedback
        span.style.backgroundColor = '#d4edda';
        setTimeout(() => {
            span.style.backgroundColor = '';
        }, 800);

    } catch (error) {
        console.error("Error updating transaction category:", error);
        span.style.backgroundColor = '#f8d7da';
        alert("Failed to update transaction category. Check console for details.");
    }
}