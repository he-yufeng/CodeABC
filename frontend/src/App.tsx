import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import PrView from "./pages/PrView";
import CompareView from "./pages/CompareView";
import Overview from "./pages/Overview";
import FileView from "./pages/FileView";
import { I18nProvider } from "./lib/i18n";

function App() {
  return (
    <I18nProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/pr" element={<PrView />} />
          <Route path="/compare" element={<CompareView />} />
          <Route path="/project/:projectId" element={<Overview />} />
          <Route path="/project/:projectId/file/*" element={<FileView />} />
        </Routes>
      </BrowserRouter>
    </I18nProvider>
  );
}

export default App;
