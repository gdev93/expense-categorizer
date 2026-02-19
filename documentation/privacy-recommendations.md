# Report Privacy e Protezione dei Dati - Expense Categorizer 🛡️

## Indice
1. [Analisi dello Stato Attuale](#1-analisi-dello-stato-attuale)
2. [Criticità Identificate](#2-criticità-identificate)
3. [Soluzioni Proposte (Roadmap Privacy)](#3-soluzioni-proposte-roadmap-privacy)
4. [Analisi di Sicurezza per Componente](#4-analisi-di-sicurezza-per-componente)
5. [Conclusioni e Prossimi Passi](#5-conclusioni-e-prossimi-passi)

---

## 1. Analisi dello Stato Attuale
Il progetto gestisce dati finanziari e personali altamente sensibili (PII - Personally Identifiable Information).

### Dati Gestiti:
- **Descrizioni Bancarie:** Spesso contengono nomi di beneficiari, IBAN parziali, ID transazioni e talvolta indirizzi fisici.
- **Importi e Date:** Forniscono un profilo dettagliato delle abitudini di vita e spesa dell'utente.
- **Dati Grezzi (Raw Data):** Durante l'upload, l'intera riga del CSV viene memorizzata temporaneamente.

### Meccanismi Esistenti:
- **Isolamento:** Uso rigoroso di `user=request.user` in tutte le query.
- **Retention:** Cancellazione a cascata (`CASCADE`) per transazioni e file alla rimozione dell'account utente.
- **Pulizia Post-Processing:** Il campo `raw_data` e `embedding` in `Transaction` vengono svuotati al termine dell'elaborazione per ridurre la superficie di attacco.

---

## 2. Criticità Identificate

### 2.1 Esposizione verso Terze Parti (IA Cloud)
Le descrizioni bancarie complete vengono inviate a Google Gemini per la categorizzazione. Sebbene le API Enterprise abbiano termini di privacy più stringenti, l'invio di dati in chiaro a un cloud provider esterno rappresenta un rischio residuo.

### 2.2 Dati in chiaro nel Database
Campi come `description`, `original_amount` e `notes` sono salvati come testo semplice. In caso di accesso non autorizzato al database, tutti i dati sarebbero immediatamente leggibili.

### 2.3 Persistenza dei Merchant
Il modello `Merchant` usa `on_delete=models.SET_NULL`. Se un utente viene eliminato, i nomi dei merchant da lui creati rimangono nel database. Sebbene non direttamente associati all'utente, il nome di un merchant potrebbe contenere informazioni specifiche (es. "Affitto Mario Rossi").

### 2.4 Embeddings e Vettori
Gli embeddings sono rappresentazioni matematiche delle descrizioni. Sebbene non siano testo leggibile, possono essere utilizzati per inferire similarità tra transazioni sensibili o per attacchi di ricostruzione se il modello di embedding è noto.

---

## 3. Soluzioni Proposte (Roadmap Privacy)

### ✅ Livello 1: Semplici (Quick Wins)
*   **Anonimizzazione Pre-IA:** Implementare una pipeline di pulizia che rimuova IBAN, nomi propri e numeri di serie dalle descrizioni prima di inviarle all'IA.
*   **Gestione Merchant:** Modificare `on_delete` di `Merchant.user` in `CASCADE` per una cancellazione totale dei dati utente.
*   **Sicurezza Sessioni:** Configurare `SESSION_COOKIE_SECURE = True` e `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`.

### 🚧 Livello 2: Medie (Miglioramento Infrastrutturale)
*   **Crittografia a Riposo (Encryption at Rest):** Utilizzare campi crittografati nel DB per i dati sensibili (es. `django-cryptography`).
*   **Retention Policy Automatica:** Funzionalità per la cancellazione automatica dei dati più vecchi di un periodo definito dall'utente.
*   **Logging Selettivo:** Mascheramento dei dati sensibili nei log applicativi (Sentry/Logfile).

### 🚀 Livello 3: Avanzate (Privacy by Design)
*   **Local LLM (Ollama/vLLM):** Eseguire un modello locale per la categorizzazione, eliminando l'invio di dati a terze parti.
*   **Zero-Knowledge Encryption:** Crittografia lato server con chiave derivata dalla password dell'utente, rendendo i dati illeggibili anche agli amministratori.
*   **Differential Privacy:** Aggiungere rumore agli embeddings per preservare la privacy pur mantenendo l'utilità analitica.

---

## 4. Analisi di Sicurezza per Componente

| Componente | Rischio | Soluzione Consigliata |
| :--- | :--- | :--- |
| **API / Views** | Accesso non autorizzato | Implementare 2FA per l'accesso account. |
| **Export CSV** | Dati in chiaro su disco utente | Avvisare l'utente dei rischi prima del download. |
| **Embeddings** | Reverse engineering | Rotazione periodica delle chiavi di embedding. |
| **Celery Tasks** | Persistenza dati in Redis | Crittografare i payload dei task. |

---

## 5. Conclusioni e Prossimi Passi

Il progetto ha già una buona base di sicurezza ("clean raw data"), ma per un utilizzo professionale o multi-utente è consigliabile procedere con:
1. **Anonimizzazione pre-invio all'IA** (Priorità Alta).
2. **Passaggio a un modello locale** (Strategia a lungo termine).
3. **Crittografia dei campi sensibili nel DB** (Standard di settore).

---
*Generato automaticamente come proposta di miglioramento privacy il 19 Febbraio 2026.*
