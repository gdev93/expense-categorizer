document.addEventListener('DOMContentLoaded', function() {
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function normalizePath(path) {
        if (!path) return '';
        // Remove query parameters and hash
        const cleanPath = path.split('?')[0].split('#')[0];
        // Ensure it starts and ends with a slash
        let normalized = cleanPath.startsWith('/') ? cleanPath : '/' + cleanPath;
        if (!normalized.endsWith('/')) {
            normalized += '/';
        }
        return normalized;
    }

    function isOnTargetPage(currentPath, targetPath) {
        const current = normalizePath(currentPath);
        const target = normalizePath(targetPath);
        // Match if it's the exact path or a sub-path
        return current.startsWith(target);
    }

    function updateStep(step, redirectUrl) {
        fetch('/onboarding/update-step/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: `step=${step}`
        }).then(response => {
            if (response.ok) {
                if (redirectUrl) {
                    window.location.href = redirectUrl;
                } else {
                    window.location.reload();
                }
            }
        });
    }

    const steps = {
        1: {
            title: 'Crea le tue Categorie',
            text: 'Questo passaggio si trova nella sezione di menu <b>Categorie di spesa</b>. Il primo passo è creare le categorie di spesa (es. Spesa, Affitto, Trasporti) con una breve descrizione.',
            targetUrl: '/categories/',
            hint: 'Clicca qui per creare la tua prima categoria!',
            selector: '.btn-primary[href*="create"]'
        },
        2: {
            title: 'Carica i tuoi Dati',
            text: 'Questo passaggio si trova nella sezione di menu <b>Caricamento dati</b>. Ora carica il file CSV delle tue transazioni bancarie per iniziare a categorizzarle.',
            targetUrl: '/transactions/upload/',
            hint: 'Trascina qui il tuo file CSV o clicca per selezionarlo.',
            selector: '.upload-area'
        },
        3: {
            title: 'Usa i Filtri',
            text: 'Questo passaggio si trova nella sezione di menu <b>Spese</b>. Ottimo! Ora puoi usare i filtri per analizzare le tue spese per periodo, categoria o esercente.',
            targetUrl: '/transactions/',
            hint: 'Usa questi filtri per trovare esattamente quello che cerchi.',
            selector: '#main-filter-form'
        },
        4: {
            title: 'Personalizza le tue Spese',
            text: 'Questo passaggio si trova nella sezione di menu <b>Spese</b>. Puoi cambiare la categoria di una spesa cliccando sulla "pillola" colorata, oppure cliccare sulla riga per vedere i dettagli e gestire le regole.',
            targetUrl: '/transactions/',
            hint: 'Clicca qui per cambiare categoria o sulla riga per i dettagli.',
            selector: '.data-list-item'
        }
    };

    const replayBtn = document.getElementById('replay-onboarding');
    const replayModal = document.getElementById('replay-modal');
    const replayConfirmBtn = document.getElementById('replay-confirm');
    const replayCancelBtn = document.getElementById('replay-cancel');

    if (replayBtn && replayModal) {
        replayBtn.addEventListener('click', function(e) {
            e.preventDefault();
            replayModal.style.display = 'flex';
        });

        replayConfirmBtn.addEventListener('click', function() {
            updateStep(1, steps[1].targetUrl);
        });

        replayCancelBtn.addEventListener('click', function() {
            replayModal.style.display = 'none';
        });

        // Close modal when clicking outside
        replayModal.addEventListener('click', function(e) {
            if (e.target === replayModal) {
                replayModal.style.display = 'none';
            }
        });
    }

    const onboardingContainer = document.getElementById('onboarding-container');
    if (!onboardingContainer) return;

    const currentStep = parseInt(onboardingContainer.dataset.step);
    if (currentStep <= 4) {
        document.body.classList.add('onboarding-active');
        document.body.classList.add('onboarding-step-' + currentStep);
    }
    const overlay = document.getElementById('onboarding-overlay');
    const title = document.getElementById('onboarding-title');
    const text = document.getElementById('onboarding-text');
    const nextBtn = document.getElementById('onboarding-next');
    const skipBtn = document.getElementById('onboarding-skip');
    const hint = document.getElementById('onboarding-hint');
    const hintText = document.getElementById('onboarding-hint-text');

    function showStepExplanation(step) {
        const config = steps[step];
        if (!config) return;

        title.textContent = config.title;
        text.innerHTML = config.text;
        overlay.style.display = 'flex';
        
        // Add step-specific class for positioning
        overlay.className = 'onboarding-overlay step-' + step;

        nextBtn.onclick = () => {
            if (isOnTargetPage(window.location.pathname, config.targetUrl)) {
                const nextStep = step + 1;
                const nextConfig = steps[nextStep];
                if (nextConfig) {
                    updateStep(nextStep, nextConfig.targetUrl);
                } else {
                    updateStep(5);
                }
            } else {
                window.location.href = config.targetUrl;
            }
        };
    }

    function showHint(step) {
        const config = steps[step];
        if (!config) return;

        if (!isOnTargetPage(window.location.pathname, config.targetUrl)) return;

        let targets = document.querySelectorAll(config.selector);
        // Try to find a visible target first
        let target = Array.from(targets).find(t => t.offsetWidth > 0 && t.offsetHeight > 0);

        // If no visible target, but we have hidden ones, try to show the first one
        if (!target && targets.length > 0) {
            const candidate = targets[0];
            const details = candidate.closest('details');
            if (details) {
                details.open = true;
                target = candidate;
            }
        }

        // If it's the final step and no transaction is present, show a fake one
        if (!target && step === 4) {
            const container = document.querySelector('.data-list') || document.querySelector('.empty-state');
            if (container) {
                const fakeItem = document.createElement('div');
                fakeItem.className = 'data-list-item fake-item-onboarding';
                fakeItem.style.border = '2px dashed var(--primary-color)';
                fakeItem.style.opacity = '0.8';
                fakeItem.innerHTML = `
                    <div class="list-item-info">
                        <div class="transaction-date">📅 21/01/2026</div>
                        <div class="transaction-merchant">Esempio Esercente</div>
                    </div>
                    <div class="list-item-stats">
                        <div style="display: inline-block;">
                            <span class="transaction-category" style="background-color: var(--primary-color); color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: 500;">
                                Esempio Categoria
                            </span>
                        </div>
                        <div class="list-amount">€10.00</div>
                    </div>
                `;

                if (container.classList.contains('empty-state')) {
                    container.parentNode.insertBefore(fakeItem, container);
                } else {
                    container.appendChild(fakeItem);
                }
                target = fakeItem;
            }
        }

        if (target) {
            target.classList.add('highlight-onboarding');
            hintText.textContent = config.hint;
            hint.style.display = 'flex';
            
            // Scroll target into view
            const isMobile = window.innerWidth < 768;
            const scrollBlock = (isMobile && step === 3) ? 'start' : 'center';
            target.scrollIntoView({ behavior: 'auto', block: scrollBlock });
            
            const rect = target.getBoundingClientRect();
            let left = rect.left + rect.width / 2 - hint.offsetWidth / 2;
            
            // Boundary checks for horizontal positioning
            const margin = 10;
            const minLeft = margin;
            const maxLeft = window.innerWidth - hint.offsetWidth - margin;
            
            left = Math.max(minLeft, Math.min(maxLeft, left));
            hint.style.left = `${left}px`;
            
            // Adjust arrow position to point to the target
            const targetCenter = rect.left + rect.width / 2;
            const arrowLeft = targetCenter - left;
            const arrowMargin = 15;
            const minArrowLeft = arrowMargin;
            const maxArrowLeft = hint.offsetWidth - arrowMargin;
            const constrainedArrowLeft = Math.max(minArrowLeft, Math.min(maxArrowLeft, arrowLeft));
            hint.style.setProperty('--arrow-left', `${constrainedArrowLeft}px`);
            
            // Vertical positioning
            const verticalOffset = window.innerWidth >= 768 ? 30 : 15;
            if (rect.top > 150) {
                hint.style.top = `${rect.top - hint.offsetHeight - verticalOffset}px`;
                hint.classList.add('top');
                hint.classList.remove('bottom');
            } else {
                hint.style.top = `${rect.bottom + verticalOffset}px`;
                hint.classList.add('bottom');
                hint.classList.remove('top');
            }
        }
    }

    skipBtn.onclick = () => updateStep(5);

    // Initial logic
    if (currentStep <= 4) {
        showStepExplanation(currentStep);
        showHint(currentStep);
    }
});
