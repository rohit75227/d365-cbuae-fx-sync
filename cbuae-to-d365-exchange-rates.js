/**
 * CBUAE -> D365 Finance & Operations exchange rate sync
 * -------------------------------------------------------
 * STATUS: starter script, needs verification against your tenant before
 * scheduling it live. Two things you MUST confirm before this is safe to run:
 *
 *   1. The D365 OData entity name for currency exchange rates.
 *      Go to Data management > Entities in your D365 environment and search
 *      "exchange rate". Replace ENTITY_NAME below with the exact name.
 *
 *   2. Your CBUAE rate source. CBUAE does not publish an official public API.
 *      Options, in order of reliability:
 *        a) OANDA Central Banks provider (native D365 feature, 10.0.41+) --
 *           confirm with OANDA directly whether CBUAE is one of their
 *           25 supported central banks. If yes, use D365's native import
 *           instead of this script entirely.
 *        b) A paid aggregator (e.g. Fluentax) that republishes CBUAE rates.
 *        c) Scraping centralbank.ae/en/fx-rates directly -- fragile, breaks
 *           silently if CBUAE changes their page structure. Not recommended
 *           for a production finance process without monitoring/alerting.
 *
 * This script assumes option (b) via a generic REST source. Swap
 * fetchCbuaeRates() for whatever source you land on.
 */

const AXIOS = require('axios'); // npm install axios

// ---------- CONFIG (move to env vars / Key Vault before production) ----------
const CONFIG = {
  d365: {
    tenantId: process.env.D365_TENANT_ID,
    clientId: process.env.D365_CLIENT_ID,
    clientSecret: process.env.D365_CLIENT_SECRET,
    resource: process.env.D365_RESOURCE_URL, // e.g. https://hudabeauty.operations.dynamics.com
    // TODO: verify exact entity name in Data management > Entities
    entityPath: '/data/ENTITY_NAME_TO_CONFIRM',
    exchangeRateType: 'CBUAE Daily', // create this Exchange rate type in D365 first
  },
  cbuaeSource: {
    // TODO: replace with your chosen source (Fluentax, etc.)
    apiUrl: process.env.CBUAE_SOURCE_URL,
    apiKey: process.env.CBUAE_SOURCE_API_KEY,
  },
  currencyPairs: [
    // fromCurrency, toCurrency -- adjust to the pairs you actually need
    { from: 'USD', to: 'AED' },
    { from: 'EUR', to: 'AED' },
    { from: 'GBP', to: 'AED' },
  ],
};

// ---------- STEP 1: Get D365 OAuth token (client credentials / M2M) ----------
async function getD365Token() {
  const tokenUrl = `https://login.microsoftonline.com/${CONFIG.d365.tenantId}/oauth2/v2.0/token`;
  const params = new URLSearchParams({
    grant_type: 'client_credentials',
    client_id: CONFIG.d365.clientId,
    client_secret: CONFIG.d365.clientSecret,
    scope: `${CONFIG.d365.resource}/.default`,
  });

  const response = await AXIOS.post(tokenUrl, params);
  return response.data.access_token;
}

// ---------- STEP 2: Fetch CBUAE rates from your chosen source ----------
async function fetchCbuaeRates() {
  // Placeholder implementation -- replace with your actual source call.
  const response = await AXIOS.get(CONFIG.cbuaeSource.apiUrl, {
    headers: { Authorization: `Bearer ${CONFIG.cbuaeSource.apiKey}` },
  });

  // Expected shape after mapping: [{ from: 'USD', to: 'AED', rate: 3.6725, date: '2026-08-08' }, ...]
  return response.data;
}

// ---------- STEP 3: Push a rate into D365 via OData ----------
async function pushRateToD365(token, ratePayload) {
  const url = `${CONFIG.d365.resource}${CONFIG.d365.entityPath}`;

  const body = {
    // TODO: field names below are illustrative -- confirm exact field names
    // via GET on the entity's $metadata once the entity name is confirmed.
    ExchangeRateType: CONFIG.d365.exchangeRateType,
    FromCurrency: ratePayload.from,
    ToCurrency: ratePayload.to,
    ExchangeRate: ratePayload.rate,
    StartDate: ratePayload.date,
  };

  const response = await AXIOS.post(url, body, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
  });

  return response.data;
}

// ---------- ORCHESTRATION ----------
async function syncCbuaeRatesToD365() {
  console.log(`[${new Date().toISOString()}] Starting CBUAE -> D365 exchange rate sync`);

  const token = await getD365Token();
  const rates = await fetchCbuaeRates();

  const results = [];
  for (const rate of rates) {
    try {
      const result = await pushRateToD365(token, rate);
      results.push({ pair: `${rate.from}/${rate.to}`, status: 'success' });
    } catch (err) {
      results.push({
        pair: `${rate.from}/${rate.to}`,
        status: 'failed',
        error: err.response?.data || err.message,
      });
    }
  }

  console.table(results);
  return results;
}

// Run directly (for testing via Claude Code / node cbuae-to-d365-exchange-rates.js)
if (require.main === module) {
  syncCbuaeRatesToD365()
    .then(() => console.log('Sync complete.'))
    .catch((err) => {
      console.error('Sync failed:', err.message);
      process.exit(1);
    });
}

module.exports = { syncCbuaeRatesToD365, getD365Token, fetchCbuaeRates, pushRateToD365 };
