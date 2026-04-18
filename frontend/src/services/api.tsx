import axios from "axios";

const defaultBase =
  typeof window !== "undefined"
    ? `http://${window.location.hostname}:8000/api`
    : "http://localhost:8000/api";


export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || defaultBase,
  headers: {
    "Content-Type": "application/json",
  },
});

// Global error handler for backend unavailability
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // If the backend is unreachable (network error or 5xx/4xx with no response)
    if (!error.response) {
      // Optionally, you can use a global event or a shared state manager
      window.dispatchEvent(
        new CustomEvent("api-unavailable", {
          detail: { message: "Backend server is unavailable. Please check your connection and try again." },
        })
      );
    }
    return Promise.reject(error);
  }
);
