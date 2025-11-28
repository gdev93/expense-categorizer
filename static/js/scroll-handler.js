document.addEventListener('DOMContentLoaded', function() {

    // CONFIGURATION
    // 1. Generic ID: Use id="scroll-target" on any page's target element
    const TARGET_ELEMENT_ID = 'scroll-target';

    // 2. Generic Selectors: Triggers on pagination OR any link with class 'trigger-scroll'
    const TRIGGER_SELECTOR = '.pagination a, .trigger-scroll';

    const STORAGE_KEY = 'scroll_pending_flag';
    const HEADER_OFFSET = 100;

    // ---------------------------------------------------------
    // LOGIC (No changes needed below here)
    // ---------------------------------------------------------

    // 1. CHECK: Should we scroll? (Runs on every page load)
    if (sessionStorage.getItem(STORAGE_KEY) === 'true') {
        const targetElement = document.getElementById(TARGET_ELEMENT_ID);

        if (targetElement) {
            // Wait a tiny bit to ensure layout is settled
            setTimeout(() => {
                const elementPosition = targetElement.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - HEADER_OFFSET;

                window.scrollTo({
                    top: offsetPosition,
                    behavior: "smooth"
                });
            }, 100);
        }

        // CRITICAL: Clear the flag so a manual refresh (F5) doesn't scroll again
        sessionStorage.removeItem(STORAGE_KEY);
    }

    // 2. LISTEN: Did the user click a trigger?
    const triggers = document.querySelectorAll(TRIGGER_SELECTOR);
    triggers.forEach(link => {
        link.addEventListener('click', function() {
            // Set the flag for the NEXT page load
            sessionStorage.setItem(STORAGE_KEY, 'true');
        });
    });
});