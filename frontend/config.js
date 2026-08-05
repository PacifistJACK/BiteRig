/**
 * BiteRig Frontend Configuration
 *
 * Automatically detects whether you are running locally (localhost / 127.0.0.1)
 * or in production on Azure, pointing to the appropriate backend API URL.
 */

const IS_LOCAL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.protocol === 'file:';

// Azure App Service backend URL:
const PRODUCTION_API_URL = 'https://biterig-api-a6e5fdbbdbf2dxha.centralindia-01.azurewebsites.net';


const API_BASE_URL = IS_LOCAL ? 'http://localhost:8000' : PRODUCTION_API_URL;

