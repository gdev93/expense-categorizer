document.addEventListener('DOMContentLoaded', function() {
    const TARGET_ELEMENT_ID = 'scroll-target';
    const TRIGGER_SELECTOR = '.pagination a, .trigger-scroll';
    const STORAGE_KEY = 'scroll_pending_flag';
    const HEADER_OFFSET = 100;
    if (sessionStorage.getItem(STORAGE_KEY) === 'true') {
        const targetElement = document.getElementById(TARGET_ELEMENT_ID);
        if (targetElement) {
            setTimeout(() => {
                const elementPosition = targetElement.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - HEADER_OFFSET;
                window.scrollTo({
                    top: offsetPosition,
                    behavior: "smooth"
                });
            }, 100);
        }
        sessionStorage.removeItem(STORAGE_KEY);
    }
    const triggers = document.querySelectorAll(TRIGGER_SELECTOR);
    triggers.forEach(link => {
        link.addEventListener('click', function() {
            sessionStorage.setItem(STORAGE_KEY, 'true');
        });
    });
});
