import axios from "axios";

const defaultBase =
  typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000/api`
    : "http://localhost:8000/api";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || defaultBase,
  headers: {
    "Content-Type": "application/json",
  },
});
