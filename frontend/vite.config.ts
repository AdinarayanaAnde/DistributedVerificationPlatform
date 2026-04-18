import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import fs from "fs";

const certsDir = path.resolve(__dirname, "..", "certs");
const httpsConfig =
  fs.existsSync(path.join(certsDir, "key.pem")) &&
  fs.existsSync(path.join(certsDir, "cert.pem"))
    ? {
        key: fs.readFileSync(path.join(certsDir, "key.pem")),
        cert: fs.readFileSync(path.join(certsDir, "cert.pem")),
      }
    : undefined;

export default defineConfig({
  root: path.resolve(__dirname),
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    https: httpsConfig,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
