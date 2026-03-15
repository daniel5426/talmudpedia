import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { bootstrapTheme } from "./components/theme-provider";
import "./styles.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Missing #root element");
}
bootstrapTheme();
createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
