import axios from 'axios'

// Get base URL and API key from environment variables (with development defaults)
const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const API_KEY = import.meta.env.VITE_API_KEY || 'DRM_DEFAULT_DEV_KEY'

const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY,
  },
})

export default apiClient
