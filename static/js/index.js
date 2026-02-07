
document.addEventListener('DOMContentLoaded', function() {
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');

    // Function to open/close menu
    function toggleMenu() {
        const isClosed = !sidebar.classList.contains('active');

        if (isClosed) {
            sidebar.classList.add('active');
            overlay.classList.add('active');
            // Optional: Prevent body scrolling when menu is open
            document.body.style.overflow = 'hidden';
        } else {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        }
    }

    // Event Listeners
    if (menuToggle) {
        menuToggle.addEventListener('click', toggleMenu);
    }

    if (overlay) {
        overlay.addEventListener('click', toggleMenu);
    }

    // Close menu when pressing ESC key
    document.addEventListener('keydown', function(event) {
        if (event.key === "Escape" && sidebar.classList.contains('active')) {
            toggleMenu();
        }
    });

    // Logout functionality
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function() {
            const logoutForm = document.getElementById('logout-form');
            if (logoutForm) {
                logoutForm.submit();
            }
        });
    }
});
// Set active nav item based on current page
function setActiveNavItem() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');

    navLinks.forEach(link => {
        link.classList.remove('active');
        const linkPath = link.getAttribute('data-page') || link.getAttribute('href');

        if (currentPath === linkPath) {
            link.classList.add('active');
        }
    });
}

// Handle nav link clicks
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', function (e) {
        // Remove active class from all links
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));

        // Add active class to clicked link
        this.classList.add('active');

        // Close sidebar on mobile
        if (window.innerWidth < 768) {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
        }

        // Store active page in sessionStorage
        const href = this.getAttribute('href');
        sessionStorage.setItem('activeNavItem', href);
    });
});

// Set active item on page load
setActiveNavItem();

/**
 * Toggles the custom multiselect dropdown menu.
 * @param {string} id - The ID of the multiselect container.
 * @param {Event} event - The click event.
 */
function toggleMultiselect(id, event) {
    if (event) event.stopPropagation();
    
    const el = document.getElementById(id);
    if (!el) return;

    const wasOpen = el.classList.contains('is-open');
    
    // Close all other multiselects to prevent overlap
    document.querySelectorAll('.custom-multiselect').forEach(m => {
        m.classList.remove('is-open');
    });
    
    // Toggle current
    if (!wasOpen) {
        el.classList.add('is-open');
    }
}


/**
 * Updates the trigger text and visual state of a custom multiselect.
 * @param {string} id - The ID of the multiselect container.
 */
function updateMultiselect(id) {
    const el = document.getElementById(id);
    if (!el) return;

    const checkboxes = el.querySelectorAll('input[type="checkbox"]');
    const triggerText = el.querySelector('.trigger-text');
    if (!triggerText) return;

    const selectedCheckboxes = Array.from(checkboxes).filter(cb => cb.checked);
    const selectedCount = selectedCheckboxes.length;

    const placeholder = el.getAttribute('data-placeholder') || 'Seleziona';
    const pluralText = el.getAttribute('data-plural-text') || 'selezionati';

    // Handle hidden input to ensure parameter is sent when nothing is selected
    const firstCheckbox = checkboxes[0];
    if (firstCheckbox && firstCheckbox.name) {
        const name = firstCheckbox.name;
        // Search for existing hidden input with this name that IS NOT one of our checkboxes
        // (though checkboxes are type="checkbox", we want to be sure)
        let hiddenInput = el.querySelector(`input[type="hidden"][name="${name}"]`);

        if (selectedCount === 0) {
            if (!hiddenInput) {
                hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = name;
                hiddenInput.value = '';
                // If checkboxes are associated with a form via 'form' attribute
                if (firstCheckbox.hasAttribute('form')) {
                    hiddenInput.setAttribute('form', firstCheckbox.getAttribute('form'));
                }
                el.appendChild(hiddenInput);
            }
        } else if (hiddenInput) {
            hiddenInput.remove();
        }
    }

    // Update visual state of individual items
    checkboxes.forEach(cb => {
        const item = cb.closest('.multiselect-item');
        if (item) {
            if (cb.checked) {
                item.classList.add('is-selected');
            } else {
                item.classList.remove('is-selected');
            }
        }
    });

    // Update the trigger display text
    if (selectedCount === 0) {
        triggerText.textContent = placeholder;
    } else if (selectedCount === 1) {
        const item = selectedCheckboxes[0].closest('.multiselect-item');
        const labelText = item ? item.textContent.trim() : '';
        // Remove Material Icon text from the string (it's the first word usually)
        const cleanedText = labelText.replace(/^(label|event|calendar_today|calendar_month|rule|check_circle|sync)/, '').trim();
        triggerText.textContent = cleanedText;
    } else {
        triggerText.textContent = `${selectedCount} ${pluralText}`;
    }

    // Close the multiselect dropdown after selection
    el.classList.remove('is-open');
}
/**
 * Initializes all multiselect components on the page.
 */
function initAllMultiselects() {
    document.querySelectorAll('.custom-multiselect').forEach(el => {
        if (el.id) updateMultiselect(el.id);
    });
}

/**
 * Category Dropdown Menu logic
 */
function toggleCategoryMenu(span) {
    const container = span.closest('.category-pill-container');
    const menu = span.nextElementSibling;
    if (!menu || !container) return;

    // Close all other menus first
    document.querySelectorAll('.category-dropdown-menu.show').forEach(m => {
        if (m !== menu) {
            m.classList.remove('show');
            m.classList.remove('open-above');
            const otherContainer = m.closest('.category-pill-container');
            if (otherContainer) otherContainer.classList.remove('is-open');
        }
    });

    const isOpening = !menu.classList.contains('show');
    
    if (isOpening) {
        // Reset positioning before calculating
        menu.classList.remove('open-above');
        menu.classList.add('show');

        const rect = menu.getBoundingClientRect();
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
        
        // If the menu overflows the bottom of the viewport
        if (rect.bottom > viewportHeight) {
            const spanRect = span.getBoundingClientRect();
            // And if there's more space above the span than below it
            if (spanRect.top > viewportHeight - spanRect.bottom) {
                menu.classList.add('open-above');
            }
        }
    } else {
        menu.classList.remove('show');
        menu.classList.remove('open-above');
    }

    container.classList.toggle('is-open', isOpening);
}

/**
 * Toggles the visibility of the collapsible filter section.
 */
function toggleFilters() {
    const collapsible = document.getElementById('filter-collapsible');
    if (collapsible) {
        collapsible.classList.toggle('show');
    }
}

/**
 * Updates the visual state of filter toggle buttons based on whether filters are active.
 */
function updateFilterButtonsState() {
    document.querySelectorAll('.filters').forEach(form => {
        const toggleBtn = form.querySelector('.filter-toggle-btn');
        if (!toggleBtn) return;

        let hasActiveFilters = false;

        // Check text/search inputs (search, amount)
        form.querySelectorAll('input[type="text"], input[type="search"], input[type="number"]').forEach(input => {
            if (input.value.trim() !== '') {
                hasActiveFilters = true;
            }
        });

        // Check checkboxes
        form.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
            if (checkbox.checked) {
                hasActiveFilters = true;
            }
        });

        // Check select elements
        form.querySelectorAll('select').forEach(select => {
            // We ignore structural/contextual fields
            if (select.name === 'year' || select.id === 'year' || select.name === 'view_type' || select.name === 'amount_operator' || select.name === 'paginate_by') return;

            if (select.multiple) {
                if (Array.from(select.selectedOptions).some(opt => opt.value !== '')) {
                    hasActiveFilters = true;
                }
            } else {
                if (select.value !== '') {
                    hasActiveFilters = true;
                }
            }
        });

        if (hasActiveFilters) {
            toggleBtn.classList.add('filters-active');
        } else {
            toggleBtn.classList.remove('filters-active');
        }
    });
}

/**
 * Truly clears all filter inputs in a form and updates the visual state.
 * @param {string} formId - The ID of the form to clear.
 */
function clearFilters(formId) {
    const form = document.getElementById(formId);
    if (!form) return;

    // form.elements includes all controls belonging to the form (even via form attribute)
    Array.from(form.elements).forEach(el => {
        // We preserve structural filters like year and view_type
        if (el.name === 'view_type' || el.name === 'year' || el.id === 'year' || el.name === 'paginate_by' || el.type === 'hidden') {
            return;
        }

        if (el.tagName === 'INPUT') {
            if (['text', 'search', 'number', 'date'].includes(el.type)) {
                el.value = '';
            } else if (el.type === 'checkbox') {
                el.checked = false;
            }
        } else if (el.tagName === 'SELECT') {
            if (el.multiple) {
                Array.from(el.options).forEach(opt => opt.selected = false);
            } else {
                el.selectedIndex = 0;
            }

            // Specific case for amount_operator which might default to 'eq'
            if (el.name === 'amount_operator') {
                el.value = 'eq';
            }
        }
    });

    // Update the filter button visual state
    updateFilterButtonsState();
    initAllMultiselects();
}

// Initial check and HTMX integration
document.addEventListener('DOMContentLoaded', () => {
    updateFilterButtonsState();
    initAllMultiselects();
    
    // Update after any HTMX swap to catch changes from the server or user interaction
    document.body.addEventListener('htmx:afterSwap', () => {
        updateFilterButtonsState();
        initAllMultiselects();
    });
});

/**
 * Shows an alert message styled like Django messages.
 * @param {string} message - The message to display.
 * @param {string} type - The type of alert (success, danger, warning, info).
 */
function showAlert(message, type = 'danger') {
    let container = document.querySelector('.messages-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'messages-container';
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.prepend(container);
        } else {
            document.body.prepend(container);
        }
    }

    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.setAttribute('role', 'alert');
    
    const formattedMessage = message.replace(/\n/g, '<br>');
    
    alertDiv.innerHTML = `
        ${formattedMessage}
        <button type="button" class="close-btn" onclick="this.parentElement.remove();">
            <span class="material-icons">close</span>
        </button>
    `;
    
    container.appendChild(alertDiv);
}

window.addEventListener('click', function(event) {
    if (!event.target.closest('.custom-multiselect')) {
        document.querySelectorAll('.custom-multiselect').forEach(m => {
            m.classList.remove('is-open');
        });
    }

    if (!event.target.closest('.category-pill-container')) {
        document.querySelectorAll('.category-dropdown-menu.show').forEach(menu => {
            menu.classList.remove('show');
            menu.classList.remove('open-above');
            const container = menu.closest('.category-pill-container');
            if (container) container.classList.remove('is-open');
        });
    }

    // Also close merchant search results when clicking outside
    const searchContainer = document.getElementById('merchant-search-results');
    const searchInput = document.getElementById('id_merchant_name');
    if (searchContainer && !searchContainer.contains(event.target) && event.target !== searchInput) {
        searchContainer.innerHTML = '';
    }

    // Also close category search results when clicking outside
    const categoryContainer = document.getElementById('category-search-results');
    const categoryInput = document.getElementById('id_category_name');
    if (categoryContainer && !categoryContainer.contains(event.target) && event.target !== categoryInput) {
        categoryContainer.innerHTML = '';
    }
});

/**
 * Merchant search selection
 */
function selectMerchant(name, id) {
    const input = document.getElementById('id_merchant_name');
    const idInput = document.getElementById('id_merchant_id');
    const container = document.getElementById('merchant-search-results');
    if (input) {
        input.value = name;
        // Trigger a change event so HTMX or other listeners know it changed
        input.dispatchEvent(new Event('change'));
    }
    if (idInput) {
        idInput.value = id || '';
    }
    if (container) {
        container.innerHTML = '';
    }
}

/**
 * Category search selection
 */
function selectCategory(name) {
    const input = document.getElementById('id_category_name');
    const container = document.getElementById('category-search-results');
    if (input) {
        input.value = name;
        input.dispatchEvent(new Event('change'));
    }
    if (container) {
        container.innerHTML = '';
    }
}
