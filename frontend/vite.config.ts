import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  // 加载项目根目录的 .env 文件
  const env = loadEnv(mode, "../", "");
  const backendPort = env.VITE_BACKEND_PORT || "8018";
  const frontendPort = env.VITE_FRONTEND_PORT || "8088";

  return {
    plugins: [react()],
    server: {
      port: parseInt(frontendPort),
      host: "0.0.0.0",
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
    },
  };
});