/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_APP_MODE: string;
  readonly VITE_APP_NAME: string;
  // Добавьте другие переменные при необходимости
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}