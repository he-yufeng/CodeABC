import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import Overview from "./pages/Overview";
import FileView from "./pages/FileView";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/project/:projectId" element={<Overview />} />
        <Route path="/project/:projectId/file/*" element={<FileView />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
