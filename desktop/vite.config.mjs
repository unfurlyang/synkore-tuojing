import { defineConfig } from 'vite';
export default defineConfig({root:'frontend',base:'/',build:{outDir:'../web',emptyOutDir:true},server:{port:5173,proxy:{'/v1':'http://127.0.0.1:8765'}}});
