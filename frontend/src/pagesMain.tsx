import React from "react";
import ReactDOM from "react-dom/client";
import "../pages/base.css";
import SiteHome from "./views/SiteHome";

const noop = () => {};

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <SiteHome
      variant="open-source"
      isAuthenticated={false}
      onOpenAuth={noop}
      onEnterWorkspace={noop}
      onGoToSite={noop}
      onStartPath={noop}
    />
  </React.StrictMode>,
);
