/**
 * BiteRig Frontend Configuration
 *
 * Automatically detects whether you are running locally (localhost / 127.0.0.1)
 * or in production on Azure, pointing to the appropriate backend API URL.
 */

const IS_LOCAL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.protocol === 'file:';

// Set your Azure Container App URL here once deployed:
const PRODUCTION_API_URL = 'REPLACE_WITH_AZURE_CONTAINER_APP_URL';

const API_BASE_URL = IS_LOCAL ? 'http://localhost:8000' : PRODUCTION_API_URL;

