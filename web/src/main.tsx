import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
import "./dashboard-mode.css";
import "./status.css";
import "./layout-fixes.css";
import "./risk-feed.css";

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
