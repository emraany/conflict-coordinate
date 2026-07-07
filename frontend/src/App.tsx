import { useEffect, useState } from "react";

import { AboutPage } from "./pages/AboutPage";
import { ActivityPage } from "./pages/ActivityPage";
import { AdminConflictsPage } from "./pages/AdminConflictsPage";
import { AdminPage } from "./pages/AdminPage";
import { ConflictsPage } from "./pages/ConflictsPage";
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

  if (path.startsWith("/admin/conflicts")) return <AdminConflictsPage />;
  if (path.startsWith("/admin")) return <AdminPage />;
  if (path.startsWith("/conflicts")) return <ConflictsPage />;
  if (path.startsWith("/activity")) return <ActivityPage />;
  if (path.startsWith("/about")) return <AboutPage />;
  return <MapPage />;
}
