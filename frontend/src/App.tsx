import { useEffect, useState } from "react";

import { AdminPage } from "./pages/AdminPage";
import { MapPage } from "./pages/MapPage";

function currentPath(): string {
  return typeof window !== "undefined" ? window.location.pathname : "/";
}

export default function App() {
  const [path, setPath] = useState(currentPath());

  useEffect(() => {
    const onPop = () => setPath(currentPath());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  if (path.startsWith("/admin")) return <AdminPage />;
  return <MapPage />;
}
