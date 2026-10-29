import { Routes, Route } from "react-router-dom";
import "./App.css";

import Home from "./pages/Home";
import LostItem from "./pages/LostItem";
import FoundItem from "./pages/FoundItem";
import Claims from "./pages/Claims";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Messages from "./pages/MessagesInbox";

import ProtectedRoute from "./components/ProtectedRoute";
import SiteHeader from "./components/SiteHeader";
import ItemListing from "./components/ItemListing";

function App() {
  return (
    <>
      <SiteHeader />
      <Routes>
      {/* Public pages */}
      <Route path="/" element={<Home />} />

      <Route path="/login" element={<Login />} />

      <Route path="/register" element={<Register />} />

      <Route path="/lost-items" element={<ItemListing type="lost" />} />

      <Route path="/found-items" element={<ItemListing type="found" />} />

      {/* Protected pages */}
      <Route
        path="/report/lost"
        element={
          <ProtectedRoute>
            <LostItem />
          </ProtectedRoute>
        }
      />

      <Route
        path="/report/found"
        element={
          <ProtectedRoute>
            <FoundItem />
          </ProtectedRoute>
        }
      />

      <Route
        path="/claims"
        element={
          <ProtectedRoute>
            <Claims />
          </ProtectedRoute>
        }
      />

      <Route path="/messages" element={<ProtectedRoute><Messages /></ProtectedRoute>} />
      </Routes>
    </>
  );
}

export default App;
